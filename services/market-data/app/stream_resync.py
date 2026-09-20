"""After the market stream (re)connects: one REST snapshot, so the state is never older than the outage.

The venue does not replay what a subscriber missed while it was disconnected, so
each connect is followed by one pass over the REST endpoints: every asset
context in one ``metaAndAssetCtxs`` request, one ``l2Book`` per market, and the
candles since the newest one already held (or the most recent ``candle_keep``
on first connect). Every request goes through the provider's rate limiter and
its one pooled client, and every reading is filed with the time its request
started, so a stream message that arrived meanwhile is never overwritten.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Iterable

from .candles import SUPPORTED_INTERVALS
from .market_stream_state import MarketStreamState

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


async def resync_from_rest(
    provider: Any,
    state: MarketStreamState,
    symbols: Iterable[str],
    now_ms: Callable[[], int] = _now_ms,
) -> dict[str, Any]:
    """Seed the stream state from REST; returns what was seeded and what failed."""
    symbols = list(symbols)
    seeded = {"contexts": 0, "books": 0, "candles": 0}
    failures: list[str] = []

    requested = now_ms()
    try:
        contexts = await provider.fetch_asset_contexts(symbols)
    except Exception as exc:  # one failed endpoint must not stop the others
        failures.append(f"metaAndAssetCtxs: {type(exc).__name__}")
        contexts = {}
    for _canonical, (venue_symbol, ctx, _info) in contexts.items():
        seeded["contexts"] += int(state.seed_context(venue_symbol, ctx, requested))

    for symbol in symbols:
        coin = provider.denormalize_symbol(symbol)
        requested = now_ms()
        book = await provider.fetch_l2_book(symbol)
        if book is None:
            failures.append(f"l2Book {coin}")
        else:
            seeded["books"] += int(state.seed_book(coin, book, requested))
        for interval in state.candle_intervals:
            requested = now_ms()
            newest = state.newest_candle_open_ms(coin, interval)
            start = newest if newest is not None else requested - SUPPORTED_INTERVALS[interval] * state.candle_keep
            rows = await provider.fetch_candles(symbol, interval, start, requested)
            seeded["candles"] += state.seed_candles(coin, interval, rows, requested)

    if failures:
        logger.warning(f"Market stream resync incomplete: {', '.join(failures)}")
    return {"seeded": seeded, "failures": failures}
