"""The scoring book and asset contexts come from the stream while it is fresh, and from REST only when it is not."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app import pollers
from app.market_stream_state import MarketStreamState
from app.processors import MarketNormalizer
from app.providers.hyperliquid_context import context_entry
from app.stream_readings import contexts_for, orderbook_for
from tradesync_core.feed_heartbeat import Heartbeat

from tests.fake_hyperliquid_ws import book_message, ctx_message

NOW = 1_789_380_000_000
FRESH_MS = 5_000


class Stop(BaseException):
    pass


def heartbeat() -> Heartbeat:
    return Heartbeat("hyperliquid_market_stream", label="stream", kind="websocket", service="market-data",
                     authority="authoritative_market", influence="test", counts=("book_fallbacks", "context_fallbacks"))


class Venue:
    venue = "hyperliquid"
    enabled = True

    def __init__(self) -> None:
        self.context_requests: list[list[str]] = []
        self.book_requests: list[str] = []

    def denormalize_symbol(self, symbol: str) -> str:
        return symbol.replace("-PERP", "")

    async def fetch_context(self, symbols):
        self.context_requests.append(list(symbols))
        return {s: context_entry("hyperliquid", s, s.replace("-PERP", ""), ctx_message(s.replace("-PERP", ""), mark="1.0")["data"]["ctx"],
                                 NOW, {"name": s}) for s in symbols}

    async def fetch_orderbook(self, symbol):
        self.book_requests.append(symbol)
        return {"venue": "hyperliquid", "symbol": symbol, "poll_ts": NOW, "source": "l2Book", "best_bid": 1.0, "best_ask": 2.0}


def test_a_fresh_stream_book_is_the_scoring_book_and_costs_no_request() -> None:
    state = MarketStreamState(["BTC"], [])
    state.ingest(book_message("BTC"), NOW - 1_000)
    venue, beat = Venue(), heartbeat()
    book = asyncio.run(orderbook_for(venue, "BTC-PERP", state, NOW, FRESH_MS, beat))
    assert venue.book_requests == [] and beat.snapshot()["counts_1h"]["book_fallbacks"] == 0
    assert book["source"] == "ws:l2Book" and book["poll_ts"] == NOW - 1_000
    assert (book["best_bid"], book["best_ask"], book["mid_price"]) == (99999.0, 100001.0, 100000.0)


@pytest.mark.parametrize("received_ms", [NOW - FRESH_MS - 1, None])
def test_a_stale_or_missing_stream_book_falls_back_to_rest_and_is_counted(received_ms) -> None:
    state = MarketStreamState(["BTC"], [])
    if received_ms is not None:
        state.ingest(book_message("BTC"), received_ms)
    venue, beat = Venue(), heartbeat()
    book = asyncio.run(orderbook_for(venue, "BTC-PERP", state, NOW, FRESH_MS, beat))
    assert venue.book_requests == ["BTC-PERP"] and book["source"] == "l2Book"
    assert beat.snapshot()["counts_1h"]["book_fallbacks"] == 1


def test_contexts_come_from_the_stream_and_rest_answers_only_for_stale_markets() -> None:
    state = MarketStreamState(["BTC", "ETH", "SOL"], [])
    state.ingest(ctx_message("BTC"), NOW - 500)
    state.ingest(ctx_message("SOL"), NOW - 20_000)
    venue, beat = Venue(), heartbeat()
    entries = asyncio.run(contexts_for(venue, ["BTC-PERP", "ETH-PERP", "SOL-PERP"], state, NOW, FRESH_MS, beat))
    assert venue.context_requests == [["ETH-PERP", "SOL-PERP"]]
    assert beat.snapshot()["counts_1h"]["context_fallbacks"] == 2
    assert entries["BTC-PERP"]["funding"]["source"] == "ws:activeAssetCtx" and entries["BTC-PERP"]["poll_ts"] == NOW - 500
    assert entries["ETH-PERP"]["funding"]["source"] == "metaAndAssetCtxs"


def test_with_the_stream_switched_off_every_read_is_rest_and_nothing_counts_as_a_fallback() -> None:
    venue, beat = Venue(), heartbeat()
    asyncio.run(contexts_for(venue, ["BTC-PERP"], None, NOW, FRESH_MS, beat))
    asyncio.run(orderbook_for(venue, "BTC-PERP", None, NOW, FRESH_MS, beat))
    assert venue.context_requests == [["BTC-PERP"]] and venue.book_requests == ["BTC-PERP"]
    assert beat.snapshot()["counts_1h"] == {"book_fallbacks": 0, "context_fallbacks": 0}


def test_a_stream_context_normalizes_to_the_same_values_as_the_same_context_polled() -> None:
    ctx = ctx_message("BTC")["data"]["ctx"]
    rest = context_entry("hyperliquid", "BTC-PERP", "BTC", ctx, NOW, {"name": "BTC"})
    state = MarketStreamState(["BTC"], [])
    state.ingest({"channel": "activeAssetCtx", "data": {"coin": "BTC", "ctx": ctx}}, NOW)
    stream = asyncio.run(contexts_for(Venue(), ["BTC-PERP"], state, NOW, FRESH_MS, heartbeat()))
    normalizer = MarketNormalizer()
    polled = {e.metric_type: e.value for e in normalizer.normalize_context("hyperliquid", {"BTC-PERP": rest})}
    streamed = {e.metric_type: e.value for e in normalizer.normalize_context("hyperliquid", stream)}
    strip = lambda values: {k: {f: v for f, v in fields.items() if f != "raw"} for k, fields in values.items()}
    assert strip(streamed) == strip(polled)


def test_the_orderbook_loop_builds_its_snapshot_from_the_stream_book() -> None:
    now = int(time.time() * 1000)
    state = MarketStreamState(["BTC"], [])
    state.ingest(book_message("BTC"), now)
    venue = Venue()
    pushed: list[dict] = []

    async def push(event):
        pushed.append(event)

    async def sleep(_seconds):
        raise Stop

    with patch.object(pollers, "providers", [venue]), patch.object(pollers, "SYMBOLS", ["BTC-PERP"]), \
            patch.object(pollers, "market_stream", state), patch.object(pollers, "MARKET_STREAM_ENABLED", True), \
            patch.object(pollers, "STREAM_HEARTBEAT", heartbeat()), \
            patch.object(pollers.redis_client, "push_normalized", push), \
            patch.object(pollers.book_history, "capture", AsyncMock()), \
            patch.object(pollers, "store_snapshot_and_features", AsyncMock()) as stored, \
            patch.object(pollers.asyncio, "sleep", sleep):
        with pytest.raises(Stop):
            asyncio.run(pollers.poll_orderbook_loop())
    assert venue.book_requests == []
    assert pushed and pushed[0]["source"]["endpoint"] == "ws:l2Book" and pushed[0]["value"]["best_bid"] == 99999.0
    snapshot = stored.await_args.args[0]
    assert snapshot.orderbook.best_ask == 100001.0
