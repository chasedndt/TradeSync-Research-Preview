"""Stream first, REST only when stale: the asset contexts and the scoring book the poll loops read.

The market stream keeps Hyperliquid's newest asset context and full-precision
book per market. A poll loop takes those while they are younger than the
freshness bound and asks the REST endpoint only for markets whose stream reading
is stale or missing, so a healthy stream costs no REST request and a broken one
costs exactly the polling the service always did. Every fallback is counted on
the stream's heartbeat, which is how the pipeline page shows how often the
stream was not enough.

Both paths produce the same shapes: the context entry comes from
``providers/hyperliquid_context.py`` and the book from
``providers/hyperliquid_book.py``, with ``source`` naming the endpoint each
reading actually came from.
"""

from __future__ import annotations

from typing import Any, Iterable

from .market_stream_state import WEBSOCKET, MarketStreamState
from .providers.hyperliquid_book import parse_l2_book
from .providers.hyperliquid_context import REST_SOURCE, STREAM_SOURCE, context_entry

BOOK_STREAM_SOURCE = "ws:l2Book"
BOOK_REST_SOURCE = "l2Book"


def _stream_applies(provider: Any, state: MarketStreamState | None) -> bool:
    return state is not None and getattr(provider, "venue", None) == "hyperliquid"


async def contexts_for(
    provider: Any,
    symbols: Iterable[str],
    state: MarketStreamState | None,
    now_ms: int,
    fresh_ms: int,
    heartbeat: Any,
) -> dict[str, Any]:
    """Context entries for every symbol: fresh stream readings, and one REST request for the rest."""
    symbols = list(symbols)
    if not _stream_applies(provider, state):
        return await provider.fetch_context(symbols)
    entries: dict[str, Any] = {}
    stale: list[str] = []
    for symbol in symbols:
        coin = provider.denormalize_symbol(symbol)
        reading = state.context(coin, now_ms, fresh_ms)
        if reading is None:
            stale.append(symbol)
            continue
        source = STREAM_SOURCE if reading.source == WEBSOCKET else REST_SOURCE
        entries[symbol] = context_entry(provider.venue, symbol, coin, dict(reading.data), reading.received_ms, None, source)
    if stale:
        heartbeat.count("context_fallbacks", len(stale))
        entries.update(await provider.fetch_context(stale))
    return entries


async def orderbook_for(
    provider: Any,
    symbol: str,
    state: MarketStreamState | None,
    now_ms: int,
    fresh_ms: int,
    heartbeat: Any,
) -> dict[str, Any] | None:
    """The scoring book for one symbol: the stream's while fresh, otherwise one REST request."""
    if _stream_applies(provider, state):
        reading = state.book(provider.denormalize_symbol(symbol), now_ms, fresh_ms)
        if reading is not None:
            book = parse_l2_book(provider.venue, symbol, dict(reading.data), reading.received_ms)
            book["source"] = BOOK_STREAM_SOURCE if reading.source == WEBSOCKET else BOOK_REST_SOURCE
            return book
        heartbeat.count("book_fallbacks")
    return await provider.fetch_orderbook(symbol)
