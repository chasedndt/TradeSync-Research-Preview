"""What the market stream holds, how a REST resync seeds it, and that nothing newer is ever overwritten."""

from __future__ import annotations

import asyncio

import pytest

from app.market_stream_state import REST_RESYNC, WEBSOCKET, MarketStreamState
from app.stream_resync import resync_from_rest

from tests.fake_hyperliquid_ws import book_message, candle_message, ctx_message


def test_each_channel_is_filed_per_market_with_its_receive_time() -> None:
    state = MarketStreamState(["BTC", "ETH"], ["1m"])
    assert state.ingest(ctx_message("BTC"), 1_000) == "activeAssetCtx"
    assert state.ingest(book_message("ETH"), 1_100) == "l2Book"
    assert state.ingest(candle_message("BTC", 60_000), 1_200) == "candle"
    assert state.ingest({"channel": "pong"}, 1_300) == "pong"
    assert state.context("BTC", 1_500, 5_000).data["markPx"] == "100000.0"
    assert state.book("ETH", 1_500, 5_000).received_ms == 1_100
    assert [c["t"] for c in state.candles("BTC", "1m")] == [60_000]
    assert state.last_message_ms == 1_300


def test_readings_older_than_the_bound_are_not_handed_out() -> None:
    state = MarketStreamState(["BTC"], [])
    state.ingest(book_message("BTC"), 1_000)
    assert state.book("BTC", 6_000, 5_000) is not None
    assert state.book("BTC", 6_001, 5_000) is None


def test_unusable_or_untracked_messages_are_refused() -> None:
    state = MarketStreamState(["BTC"], ["1m"])
    no_mark = ctx_message("BTC")
    del no_mark["data"]["ctx"]["markPx"]
    assert state.ingest(no_mark, 1) is None
    assert state.ingest(ctx_message("DOGE"), 1) is None
    assert state.ingest({"channel": "l2Book", "data": {"coin": "BTC", "levels": [[]]}}, 1) is None
    assert state.ingest(candle_message("BTC", 60_000, interval="15m"), 1) is None, "not a subscribed interval"
    assert state.ingest("not a message", 1) is None
    assert state.counts["activeAssetCtx_unusable"] == 2 and state.counts["l2Book_unusable"] == 1


def test_numbers_may_arrive_as_numbers_or_as_numeric_strings() -> None:
    state = MarketStreamState(["BTC"], [])
    message = ctx_message("BTC")
    message["data"]["ctx"].update(markPx=100000.0, oraclePx=99990.0)
    assert state.ingest(message, 1) == "activeAssetCtx"


def test_an_unsupported_candle_interval_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="3d"):
        MarketStreamState(["BTC"], ["1m", "3d"])


def test_a_resync_never_overwrites_a_newer_stream_reading() -> None:
    state = MarketStreamState(["BTC"], ["1m"])
    state.ingest(book_message("BTC", bid="100"), 2_000)
    assert state.seed_book("BTC", book_message("BTC", bid="90")["data"], requested_ms=1_000) is False
    assert state.book("BTC", 2_000, 5_000).source == WEBSOCKET
    assert state.seed_book("BTC", book_message("BTC", bid="95")["data"], requested_ms=3_000) is True
    assert state.book("BTC", 3_000, 5_000).source == REST_RESYNC

    state.ingest(candle_message("BTC", 60_000, close="101"), 5_000)
    stale_row = candle_message("BTC", 60_000, close="99")["data"]
    assert state.seed_candles("BTC", "1m", [stale_row], requested_ms=4_000) == 0
    assert state.candles("BTC", "1m")[0]["c"] == "101"


def test_the_candle_series_keeps_only_the_newest_candles() -> None:
    state = MarketStreamState(["BTC"], ["1m"], candle_keep=3)
    for minute in range(5):
        state.ingest(candle_message("BTC", minute * 60_000), 1_000 + minute)
    assert [c["t"] for c in state.candles("BTC", "1m")] == [120_000, 180_000, 240_000]
    assert state.newest_candle_open_ms("BTC", "1m") == 240_000


def test_freshness_names_the_fresh_stale_and_missing_markets_per_channel() -> None:
    state = MarketStreamState(["BTC", "ETH", "SOL"], ["1m"])
    state.ingest(book_message("BTC"), 10_000)
    state.ingest(book_message("ETH"), 1_000)
    state.ingest({"channel": "pong"}, 10_500)
    report = state.freshness(now_ms=11_000, fresh_ms=5_000)
    book = report["channels"]["l2Book"]
    assert (book["fresh"], book["stale"], book["missing"]) == (1, ["ETH"], ["SOL"])
    assert (book["newest_age_ms"], book["oldest_age_ms"]) == (1_000, 10_000)
    assert report["channels"]["activeAssetCtx"]["missing"] == ["BTC", "ETH", "SOL"]
    assert report["channels"]["candle"]["fresh_after_ms"] == 60_000
    assert report["last_message_age_ms"] == 500


class RestVenue:
    venue = "hyperliquid"

    def __init__(self, *, book_fails_for: str | None = None) -> None:
        self.book_fails_for = book_fails_for
        self.candle_requests: list[tuple] = []

    def denormalize_symbol(self, symbol: str) -> str:
        return symbol.replace("-PERP", "")

    async def fetch_asset_contexts(self, symbols):
        return {s: (s.replace("-PERP", ""), ctx_message(s.replace("-PERP", ""))["data"]["ctx"], {"name": s}) for s in symbols}

    async def fetch_l2_book(self, symbol):
        coin = symbol.replace("-PERP", "")
        return None if coin == self.book_fails_for else book_message(coin)["data"]

    async def fetch_candles(self, symbol, interval, start_ms, end_ms):
        self.candle_requests.append((symbol, interval, start_ms, end_ms))
        return [candle_message(symbol.replace("-PERP", ""), start_ms // 60_000 * 60_000)["data"]]


def test_a_resync_seeds_every_context_book_and_the_missing_candles() -> None:
    state = MarketStreamState(["BTC", "ETH"], ["1m"], candle_keep=10)
    state.ingest(candle_message("BTC", 600_000), 1)
    clock = iter(range(1_000_000, 1_000_100))
    venue = RestVenue(book_fails_for="ETH")
    result = asyncio.run(resync_from_rest(venue, state, ["BTC-PERP", "ETH-PERP"], now_ms=lambda: next(clock)))
    assert result["seeded"] == {"contexts": 2, "books": 1, "candles": 2}
    assert result["failures"] == ["l2Book ETH"]
    assert state.book("BTC", 1_000_050, 5_000).source == REST_RESYNC
    btc, eth = venue.candle_requests
    assert btc[2] == 600_000, "BTC resumes from the newest candle it already holds"
    assert eth[3] - eth[2] == 10 * 60_000, "ETH, holding none, asks for the newest candle_keep candles"
