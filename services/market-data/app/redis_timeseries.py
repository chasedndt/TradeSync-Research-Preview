"""Rolling and cadence-governed series in Redis.

Moved out of ``redis_client.py`` unchanged. Two different stores live here and
they are not interchangeable:

- ``append_timeseries`` / ``get_timeseries`` keep a rolling 24 hours of a plain
  metric, every point as it arrived;
- ``append_feature_timeseries`` / ``get_feature_timeseries`` keep **one** latest
  observation per declared sampling bucket for 8 days, which is what makes a
  feature history comparable across symbols rather than a record of how often a
  poller happened to run.

Each takes the Redis client it should use, so the caller owns the connection.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


async def append_timeseries(
    client,
    venue: str,
    symbol: str,
    metric: str,
    value: float,
    ts: int,
):
    """
    Append to rolling timeseries.
    Uses sorted set with timestamp as score.
    Key: market:ts:{venue}:{symbol}:{metric}
    """
    key = f"market:ts:{venue}:{symbol}:{metric}"
    await client.zadd(key, {f"{ts}:{value}": ts})
    # Keep last 24 hours (86400 seconds * 1000 ms)
    cutoff = ts - (86400 * 1000)
    await client.zremrangebyscore(key, 0, cutoff)
    # TTL of 25 hours
    await client.expire(key, 90000)


async def get_timeseries(
    client,
    venue: str,
    symbol: str,
    metric: str,
    window_ms: int = 3600000,  # 1 hour default
) -> List[Dict[str, Any]]:
    """Get timeseries data for metric."""
    key = f"market:ts:{venue}:{symbol}:{metric}"
    now = int(time.time() * 1000)
    start = now - window_ms

    entries = await client.zrangebyscore(key, start, now)
    result = []
    for entry in entries:
        parts = entry.split(":")
        if len(parts) == 2:
            result.append({
                "ts": int(parts[0]),
                "value": float(parts[1])
            })
    return result


async def append_feature_timeseries(
    client,
    venue: str,
    symbol: str,
    feature_id: str,
    value: float,
    ts: int,
    sampling_interval_ms: int,
):
    """Store one latest observation per declared sampling bucket for 8 days."""
    if sampling_interval_ms <= 0:
        return
    key = f"market:feature:{venue}:{symbol}:{feature_id}"
    bucket_start = (ts // sampling_interval_ms) * sampling_interval_ms
    bucket_end = bucket_start + sampling_interval_ms - 1
    await client.zremrangebyscore(key, bucket_start, bucket_end)
    await client.zadd(key, {f"{ts}:{value}": ts})
    cutoff = ts - (7 * 86400 * 1000)
    await client.zremrangebyscore(key, 0, cutoff)
    await client.expire(key, 8 * 86400)


async def get_feature_timeseries(
    client,
    venue: str,
    symbol: str,
    feature_id: str,
    window_ms: int,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return a feature's stored series, oldest first.

    ``limit`` returns only the most recent N points. Normalization needs at
    most ``lookback_points`` (168 today), while a 7-day series holds several
    thousand, so an unbounded read ships tens of thousands of points that
    are then discarded — slow enough to time out the caller.
    """
    key = f"market:feature:{venue}:{symbol}:{feature_id}"
    now = int(time.time() * 1000)
    if limit and limit > 0:
        # Newest-first with a bound, then reversed back to ascending.
        newest = await client.zrevrangebyscore(
            key, now, now - window_ms, start=0, num=limit
        )
        entries = list(reversed(newest))
    else:
        entries = await client.zrangebyscore(key, now - window_ms, now)
    result = []
    for entry in entries:
        ts_text, value_text = entry.split(":", 1)
        result.append({"ts": int(ts_text), "value": float(value_text)})
    return result
