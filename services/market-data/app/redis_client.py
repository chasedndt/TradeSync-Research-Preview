"""
Redis client for market data streams.

Streams:
- x:market.raw      - Raw provider payloads
- x:market.norm     - Normalized events
- x:market.snapshot - Latest snapshot per venue/symbol
- x:market.alerts   - Regime changes and extreme values
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from redis import asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Stream names
STREAM_RAW = "x:market.raw"
STREAM_NORM = "x:market.norm"
STREAM_SNAPSHOT = "x:market.snapshot"
STREAM_ALERTS = "x:market.alerts"

# Consumer groups
GROUP_NORMALIZER = "market-normalizer"
GROUP_SNAPSHOTTER = "market-snapshotter"

# Stream retention. These streams are transport, not durable truth: snapshots
# and the feature series are the records that must survive. Without a bound an
# XADD stream grows forever, and on a maxmemory instance with a noeviction
# policy that eventually rejects every write in the service, which looks like a
# dead poller rather than a full database. "~" trims approximately, at the
# radix node boundary, which is much cheaper than an exact trim.
STREAM_MAXLEN_RAW = int(os.getenv("STREAM_MAXLEN_RAW", "20000"))
STREAM_MAXLEN_NORM = int(os.getenv("STREAM_MAXLEN_NORM", "20000"))
STREAM_MAXLEN_ALERTS = int(os.getenv("STREAM_MAXLEN_ALERTS", "5000"))


from . import redis_timeseries as timeseries


class MarketRedisClient:
    """Redis client optimized for market data streams."""

    def __init__(self):
        self.client: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self):
        """Connect to Redis."""
        if self._connected:
            return
        logger.info(f"Connecting to Redis at {REDIS_URL}")
        self.client = aioredis.from_url(REDIS_URL, decode_responses=True)
        self._connected = True
        await self._ensure_streams()

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            self._connected = False
            logger.info("Disconnected from Redis")

    async def _ensure_streams(self):
        """Ensure all streams and consumer groups exist."""
        streams_groups = [
            (STREAM_RAW, GROUP_NORMALIZER),
            (STREAM_NORM, GROUP_SNAPSHOTTER),
        ]

        for stream, group in streams_groups:
            try:
                await self.client.xgroup_create(stream, group, id="0", mkstream=True)
                logger.info(f"Created consumer group '{group}' on stream '{stream}'")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(f"Consumer group '{group}' already exists on '{stream}'")
                else:
                    logger.error(f"Error creating group '{group}': {e}")

    # === Write Operations ===

    async def push_raw(self, event: Dict[str, Any]) -> str:
        """Push raw event to x:market.raw stream."""
        data = {"data": json.dumps(event)}
        msg_id = await self.client.xadd(
            STREAM_RAW, data, maxlen=STREAM_MAXLEN_RAW, approximate=True
        )
        logger.debug(f"Pushed raw event to {STREAM_RAW}: {msg_id}")
        return msg_id

    async def push_normalized(self, event: Dict[str, Any]) -> str:
        """Push normalized event to x:market.norm stream."""
        data = {"data": json.dumps(event)}
        msg_id = await self.client.xadd(
            STREAM_NORM, data, maxlen=STREAM_MAXLEN_NORM, approximate=True
        )
        logger.debug(f"Pushed normalized event to {STREAM_NORM}: {msg_id}")
        return msg_id

    async def push_alert(self, alert: Dict[str, Any]) -> str:
        """Push alert to x:market.alerts stream."""
        data = {"data": json.dumps(alert)}
        msg_id = await self.client.xadd(
            STREAM_ALERTS, data, maxlen=STREAM_MAXLEN_ALERTS, approximate=True
        )
        logger.info(f"Pushed alert to {STREAM_ALERTS}: {msg_id}")
        return msg_id

    async def store_snapshot(self, venue: str, symbol: str, snapshot: Dict[str, Any]):
        """
        Store latest snapshot in Redis hash.
        Key format: market:snapshot:{venue}:{symbol}
        """
        key = f"market:snapshot:{venue}:{symbol}"
        await self.client.hset(key, mapping={
            "data": json.dumps(snapshot),
            "ts": str(snapshot.get("ts", 0)),
            "updated_at": str(int(__import__("time").time() * 1000))
        })
        # TTL of 1 hour - snapshots should be refreshed regularly
        await self.client.expire(key, 3600)
        logger.debug(f"Stored snapshot for {venue}:{symbol}")

    # === Read Operations ===

    async def read_raw_stream(
        self,
        consumer: str,
        count: int = 10,
        block_ms: int = 1000
    ) -> List[Dict[str, Any]]:
        """Read from raw stream as consumer."""
        try:
            messages = await self.client.xreadgroup(
                GROUP_NORMALIZER,
                consumer,
                {STREAM_RAW: ">"},
                count=count,
                block=block_ms
            )
            return self._parse_stream_messages(messages)
        except Exception as e:
            logger.error(f"Error reading raw stream: {e}")
            return []

    async def read_norm_stream(
        self,
        consumer: str,
        count: int = 10,
        block_ms: int = 1000
    ) -> List[Dict[str, Any]]:
        """Read from normalized stream as consumer."""
        try:
            messages = await self.client.xreadgroup(
                GROUP_SNAPSHOTTER,
                consumer,
                {STREAM_NORM: ">"},
                count=count,
                block=block_ms
            )
            return self._parse_stream_messages(messages)
        except Exception as e:
            logger.error(f"Error reading norm stream: {e}")
            return []

    async def ack_raw(self, msg_ids: List[str]):
        """Acknowledge messages in raw stream."""
        if msg_ids:
            await self.client.xack(STREAM_RAW, GROUP_NORMALIZER, *msg_ids)

    async def ack_norm(self, msg_ids: List[str]):
        """Acknowledge messages in norm stream."""
        if msg_ids:
            await self.client.xack(STREAM_NORM, GROUP_SNAPSHOTTER, *msg_ids)

    async def get_snapshot(self, venue: str, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest snapshot for venue/symbol."""
        key = f"market:snapshot:{venue}:{symbol}"
        data = await self.client.hget(key, "data")
        if data:
            return json.loads(data)
        return None

    async def get_all_snapshots(self) -> List[Dict[str, Any]]:
        """Get all current snapshots."""
        keys = await self.client.keys("market:snapshot:*")
        snapshots = []
        for key in keys:
            data = await self.client.hget(key, "data")
            if data:
                snapshots.append(json.loads(data))
        return snapshots

    async def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent alerts from stream.

        A stream that cannot be read raises. Answering an empty list instead
        would say that no alert was raised, which is a different fact from
        Redis not answering, and the Cockpit must be able to tell them apart.
        A stream that was never written reads as empty without raising.
        """
        try:
            # Read last N messages from alerts stream
            messages = await self.client.xrevrange(STREAM_ALERTS, count=limit)
        except Exception as e:
            logger.error(f"Error reading alerts: {e}")
            raise
        alerts = []
        for msg_id, data in messages:
            if "data" in data:
                alert = json.loads(data["data"])
                alert["_msg_id"] = msg_id
                alerts.append(alert)
        return alerts

    # === Timeseries (rolling window) ===
    #
    # The stores themselves are in ``app/redis_timeseries.py``; these keep the
    # client's method surface unchanged for every caller.

    async def append_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        value: float,
        ts: int
    ):
        """Append to the rolling 24-hour series for a plain metric."""
        await timeseries.append_timeseries(self.client, venue, symbol, metric, value, ts)

    async def get_timeseries(
        self,
        venue: str,
        symbol: str,
        metric: str,
        window_ms: int = 3600000  # 1 hour default
    ) -> List[Dict[str, Any]]:
        """Get timeseries data for metric."""
        return await timeseries.get_timeseries(self.client, venue, symbol, metric, window_ms)

    async def append_feature_timeseries(
        self,
        venue: str,
        symbol: str,
        feature_id: str,
        value: float,
        ts: int,
        sampling_interval_ms: int,
    ):
        """Store one latest observation per declared sampling bucket for 8 days."""
        await timeseries.append_feature_timeseries(
            self.client, venue, symbol, feature_id, value, ts, sampling_interval_ms
        )

    async def get_feature_timeseries(
        self,
        venue: str,
        symbol: str,
        feature_id: str,
        window_ms: int,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return a feature's stored series, oldest first, optionally bounded."""
        return await timeseries.get_feature_timeseries(
            self.client, venue, symbol, feature_id, window_ms, limit
        )

    # === Helpers ===

    def _parse_stream_messages(self, messages) -> List[Dict[str, Any]]:
        """Parse stream messages into list of dicts."""
        if not messages:
            return []

        result = []
        for stream_name, stream_messages in messages:
            for msg_id, data in stream_messages:
                if "data" in data:
                    parsed = json.loads(data["data"])
                    parsed["_msg_id"] = msg_id
                    result.append(parsed)
        return result


# Singleton instance
redis_client = MarketRedisClient()
