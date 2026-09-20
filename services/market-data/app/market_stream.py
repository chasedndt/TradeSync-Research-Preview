"""The Hyperliquid market stream: asset contexts, full-precision books and candles on one websocket.

One connection subscribes to ``activeAssetCtx``, ``l2Book`` and ``candle`` for
every tracked coin and files what arrives in ``MarketStreamState``. It sends the
venue's heartbeat (``hl_ws_heartbeat``), and after every connect it resubscribes
and resyncs from one REST snapshot, so a reconnect never leaves the state older
than the outage.

A dropped connection is retried with backoff and never takes the service down.
While the stream is stale the poll loops ask REST instead (``stream_readings``),
so the worst case is exactly the polling the service did before the stream.
The backoff is reset only once data flows again, so a venue that accepts and
immediately drops connections is not reconnected to in a tight loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Iterable

import websockets

from tradesync_core.feed_heartbeat import describe_error, iso

from .feed_status import feed
from .hl_ws_heartbeat import PING_INTERVAL_S, PingSchedule, receive
from .market_stream_state import DATA_CHANNELS, MarketStreamState
from .trade_flow import HYPERLIQUID_WS_URL

logger = logging.getLogger(__name__)

RECONNECT_MIN_SECONDS = 2.0
RECONNECT_MAX_SECONDS = 60.0
SILENCE_SECONDS = 45.0

HEARTBEAT = feed(
    "hyperliquid_market_stream",
    label="Hyperliquid market stream: asset contexts, l2Book and candles",
    kind="websocket",
    authority="authoritative_market",
    scoring_influence=True,
    influence="The venue's own data: the scoring book and the asset contexts (funding, open interest, volume, mark and "
              "oracle) for every tracked market come from this stream while it is fresh. A market whose stream reading "
              "is stale is read from the REST endpoint instead, and each such fallback is counted here.",
    counts=("messages", "pongs", "resyncs", "book_fallbacks", "context_fallbacks"),
)

Resync = Callable[[], Awaitable[Any]]


def subscriptions(coins: Iterable[str], candle_intervals: Iterable[str]) -> list[dict[str, str]]:
    """Every subscription the stream sends on connect, per coin: asset context, full-precision book, candles."""
    subs: list[dict[str, str]] = []
    intervals = list(candle_intervals)
    for coin in coins:
        subs.append({"type": "activeAssetCtx", "coin": coin})
        subs.append({"type": "l2Book", "coin": coin})
        subs.extend({"type": "candle", "coin": coin, "interval": interval} for interval in intervals)
    return subs


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _resync(resync: Resync) -> None:
    try:
        result = await resync()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # the stream itself still delivers; the next connect resyncs again
        HEARTBEAT.error(f"resync: {describe_error(exc)}")
        logger.warning(f"Market stream resync failed ({type(exc).__name__})")
    else:
        HEARTBEAT.count("resyncs")
        HEARTBEAT.detail["last_resync_at"] = iso(time.time())
        failures = result.get("failures") if isinstance(result, dict) else None
        if failures:
            HEARTBEAT.error(f"resync incomplete: {', '.join(failures)}"[:200])


def _cancel(task: asyncio.Task | None) -> None:
    if task is not None and not task.done():
        task.cancel()


async def run_market_stream(
    state: MarketStreamState,
    resync: Resync,
    *,
    url: str = HYPERLIQUID_WS_URL,
    ping_interval_s: float = PING_INTERVAL_S,
    silence_s: float = SILENCE_SECONDS,
    reconnect_min_s: float = RECONNECT_MIN_SECONDS,
    reconnect_max_s: float = RECONNECT_MAX_SECONDS,
    now_ms: Callable[[], int] = _now_ms,
) -> None:
    """Keep the stream connected and the state current until cancelled."""
    subs = subscriptions(state.coins, state.candle_intervals)
    HEARTBEAT.detail.update(markets=len(state.coins), subscriptions=len(subs), candle_intervals=list(state.candle_intervals))
    delay = reconnect_min_s
    while True:
        resync_task: asyncio.Task | None = None
        try:
            HEARTBEAT.connecting()
            async with websockets.connect(url, ping_interval=20, max_size=2**22) as ws:
                for sub in subs:
                    await ws.send(json.dumps({"method": "subscribe", "subscription": sub}))
                HEARTBEAT.connected()
                logger.info(f"Market stream subscribed: {len(subs)} subscriptions over {len(state.coins)} markets")
                resync_task = asyncio.create_task(_resync(resync))
                pings = PingSchedule(ping_interval_s)
                while True:
                    raw = await receive(ws, pings, silence_s)
                    try:
                        message = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    channel = state.ingest(message, now_ms())
                    if channel in DATA_CHANNELS:
                        HEARTBEAT.message()
                        delay = reconnect_min_s
                    elif channel == "pong":
                        HEARTBEAT.count("pongs")
                    elif channel == "error":
                        HEARTBEAT.error(f"venue error: {str(message.get('data'))[:160]}")
        except asyncio.CancelledError:
            _cancel(resync_task)
            raise
        except Exception as exc:
            _cancel(resync_task)
            HEARTBEAT.failed(exc, state="disconnected")
            logger.warning(f"Market stream disconnected ({type(exc).__name__}); retrying in {delay:g}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, reconnect_max_s)
