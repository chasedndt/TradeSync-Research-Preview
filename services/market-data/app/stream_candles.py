"""Candles for ``/candles``: from the market stream when it holds the whole answer, otherwise from REST.

A chart polling one-minute candles cost a ``candleSnapshot`` request every
fifteen seconds for each open chart. The market stream holds the most recent
candles for each interval it subscribes to (seeded from REST, kept current by
the stream), so a request for the latest ``limit`` candles is answered from
memory when, and only when:

- the interval is one the stream subscribes to, and the stream has delivered
  anything (a pong counts) within ``LIVE_WITHIN_MS``;
- the held series includes the candle that is open now; and
- every one of the ``limit`` candles up to it is held, with no gap.

Everything else goes to REST exactly as before, including every explicit
``start_ms``/``end_ms`` range, and a REST answer for the latest candles is filed
so the next request can be served from memory. The venue is the only source
either way: nothing is synthesised, and a gap sends the request to REST.
"""

from __future__ import annotations

import time
from typing import Any, Mapping

from .candles import SUPPORTED_INTERVALS
from .market_stream import SILENCE_SECONDS
from .market_stream_state import MarketStreamState
from .runtime import MARKET_STREAM_ENABLED, market_stream

LIVE_WITHIN_MS = int(SILENCE_SECONDS * 1000)
STREAM_SOURCE = "hyperliquid websocket candles"
REST_SOURCE = "hyperliquid candleSnapshot"


def held_candles(
    state: MarketStreamState | None, coin: str, interval: str, limit: int, now_ms: int, live_within_ms: int = LIVE_WITHIN_MS
) -> list[Mapping[str, Any]] | None:
    """The newest ``limit`` candles, ending with the one open now, if every one is held; otherwise None."""
    if state is None or interval not in state.candle_intervals or limit <= 0:
        return None
    if state.last_message_ms is None or now_ms - state.last_message_ms > live_within_ms:
        return None
    step = SUPPORTED_INTERVALS[interval]
    current_open = now_ms // step * step
    series = {int(candle["t"]): candle for candle in state.candles(coin, interval)}
    wanted = [current_open - step * back for back in range(limit - 1, -1, -1)]
    if any(open_ms not in series for open_ms in wanted):
        return None
    return [series[open_ms] for open_ms in wanted]


async def candles_for(
    provider: Any, symbol: str, interval: str, limit: int, start_ms: int, end_ms: int, *, explicit_range: bool
) -> tuple[list[Mapping[str, Any]], str]:
    """Raw venue candles for the route, and which source answered."""
    state = market_stream if MARKET_STREAM_ENABLED else None
    coin = provider.denormalize_symbol(symbol)
    requested_ms = int(time.time() * 1000)
    if not explicit_range:
        held = held_candles(state, coin, interval, limit, requested_ms)
        if held is not None:
            return held, STREAM_SOURCE
    raw = await provider.fetch_candles(symbol, interval, start_ms, end_ms)
    if state is not None and not explicit_range:
        state.seed_candles(coin, interval, raw, requested_ms)
    return raw, REST_SOURCE
