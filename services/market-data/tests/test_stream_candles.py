"""``/candles`` answers from the market stream only when it holds the whole answer, and from REST otherwise."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app import stream_candles
from app.market_stream_state import MarketStreamState
from app.stream_candles import held_candles

from tests.fake_hyperliquid_ws import candle_message

MIN = 60_000
NOW = 1_789_380_030_000  # thirty seconds into a minute
CURRENT = NOW // MIN * MIN


def holding(minutes: list[int], last_message_ms: int = NOW - 1_000) -> MarketStreamState:
    state = MarketStreamState(["BTC"], ["1m"])
    for back in minutes:
        state.ingest(candle_message("BTC", CURRENT - back * MIN), NOW - 2_000)
    state.last_message_ms = last_message_ms
    return state


def test_the_newest_candles_are_served_when_every_one_is_held_up_to_the_open_candle() -> None:
    held = held_candles(holding([0, 1, 2, 3]), "BTC", "1m", 3, NOW)
    assert [c["t"] for c in held] == [CURRENT - 2 * MIN, CURRENT - MIN, CURRENT]


def test_a_gap_a_missing_open_candle_or_a_silent_stream_sends_the_request_to_rest() -> None:
    assert held_candles(holding([0, 2]), "BTC", "1m", 3, NOW) is None, "a gap"
    assert held_candles(holding([1, 2, 3]), "BTC", "1m", 3, NOW) is None, "the open candle is not held"
    assert held_candles(holding([0, 1, 2], last_message_ms=NOW - 60_000), "BTC", "1m", 3, NOW) is None, "silent stream"
    assert held_candles(holding([0, 1, 2]), "BTC", "15m", 3, NOW) is None, "not a subscribed interval"
    assert held_candles(None, "BTC", "1m", 3, NOW) is None, "stream switched off"


class Venue:
    venue = "hyperliquid"

    def __init__(self) -> None:
        self.requests: list[tuple] = []

    def denormalize_symbol(self, symbol: str) -> str:
        return symbol.replace("-PERP", "")

    async def fetch_candles(self, symbol, interval, start_ms, end_ms):
        self.requests.append((interval, start_ms, end_ms))
        first = (start_ms // MIN + 1) * MIN
        return [candle_message("BTC", t)["data"] for t in range(first, end_ms + 1, MIN)]


def test_a_rest_answer_is_filed_so_the_next_request_is_served_from_the_stream() -> None:
    state = MarketStreamState(["BTC"], ["1m"])
    state.last_message_ms = NOW
    venue = Venue()
    with patch.object(stream_candles, "market_stream", state), patch.object(stream_candles, "MARKET_STREAM_ENABLED", True), \
            patch.object(stream_candles.time, "time", lambda: NOW / 1000):
        first, first_source = asyncio.run(stream_candles.candles_for(venue, "BTC-PERP", "1m", 5, NOW - 5 * MIN, NOW,
                                                                     explicit_range=False))
        second, second_source = asyncio.run(stream_candles.candles_for(venue, "BTC-PERP", "1m", 5, NOW - 5 * MIN, NOW,
                                                                       explicit_range=False))
        ranged, ranged_source = asyncio.run(stream_candles.candles_for(venue, "BTC-PERP", "1m", 5, NOW - 5 * MIN, NOW,
                                                                       explicit_range=True))
    assert first_source == "hyperliquid candleSnapshot" and len(venue.requests) == 2
    assert second_source == "hyperliquid websocket candles" and [c["t"] for c in second] == [c["t"] for c in first]
    assert ranged_source == "hyperliquid candleSnapshot", "an explicit range always goes to the venue's REST history"
