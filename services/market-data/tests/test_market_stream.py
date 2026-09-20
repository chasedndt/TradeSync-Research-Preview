"""The Hyperliquid market stream against a loopback websocket: subscribe, heartbeat, reconnect, resync, silence."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from app import market_stream
from app.market_stream import run_market_stream, subscriptions
from app.market_stream_state import MarketStreamState
from tradesync_core.feed_heartbeat import Heartbeat

from tests.fake_hyperliquid_ws import (
    FakeHyperliquidSocket,
    book_message,
    candle_message,
    ctx_message,
    eventually,
    stop,
)


def fresh_heartbeat() -> Heartbeat:
    declared = market_stream.HEARTBEAT
    return Heartbeat(declared.id, label=declared.label, kind=declared.kind, service=declared.service,
                     authority=declared.authority, influence=declared.influence,
                     scoring_influence=declared.scoring_influence, counts=tuple(declared.snapshot()["counts_1h"]))


def now_ms() -> int:
    return int(time.time() * 1000)


class Resyncs:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> dict:
        self.calls += 1
        return {"seeded": {}, "failures": []}


def test_subscriptions_cover_every_channel_for_every_market() -> None:
    assert subscriptions(["BTC", "ETH"], ["1m", "15m"]) == [
        {"type": "activeAssetCtx", "coin": "BTC"}, {"type": "l2Book", "coin": "BTC"},
        {"type": "candle", "coin": "BTC", "interval": "1m"}, {"type": "candle", "coin": "BTC", "interval": "15m"},
        {"type": "activeAssetCtx", "coin": "ETH"}, {"type": "l2Book", "coin": "ETH"},
        {"type": "candle", "coin": "ETH", "interval": "1m"}, {"type": "candle", "coin": "ETH", "interval": "15m"},
    ]


def test_the_stream_subscribes_every_market_files_what_arrives_and_resyncs_once_connected() -> None:
    state = MarketStreamState(["BTC", "ETH"], ["1m"])
    resyncs = Resyncs()
    heartbeat = fresh_heartbeat()
    minute = now_ms() // 60_000 * 60_000
    script = lambda index: [ctx_message("BTC"), book_message("BTC"), candle_message("BTC", minute)]

    async def scenario() -> FakeHyperliquidSocket:
        async with FakeHyperliquidSocket(expected_subscriptions=6, script=script) as venue:
            task = asyncio.create_task(run_market_stream(state, resyncs, url=venue.url, ping_interval_s=30, silence_s=10))
            try:
                await eventually(lambda: bool(state.candles("BTC", "1m")) and resyncs.calls == 1)
            finally:
                await stop(task)
            return venue

    with patch.object(market_stream, "HEARTBEAT", heartbeat):
        venue = asyncio.run(scenario())
    assert venue.subscriptions(0) == subscriptions(["BTC", "ETH"], ["1m"])
    assert state.context("BTC", now_ms(), 5_000) is not None and state.book("BTC", now_ms(), 5_000) is not None
    assert state.context("ETH", now_ms(), 5_000) is None
    snap = heartbeat.snapshot()
    assert snap["counts_1h"]["messages"] == 3 and snap["counts_1h"]["resyncs"] == 1
    assert snap["authority"] == "authoritative_market" and snap["scoring_influence"] is True


def test_the_stream_sends_the_venue_heartbeat_and_counts_the_pongs() -> None:
    state = MarketStreamState(["BTC"], [])
    heartbeat = fresh_heartbeat()

    async def scenario() -> FakeHyperliquidSocket:
        async with FakeHyperliquidSocket(expected_subscriptions=2) as venue:
            task = asyncio.create_task(run_market_stream(state, Resyncs(), url=venue.url, ping_interval_s=0.05, silence_s=5))
            try:
                await eventually(lambda: bool(venue.connections) and venue.pings(0) >= 3
                                 and heartbeat.snapshot()["counts_1h"].get("pongs", 0) >= 2)
            finally:
                await stop(task)
            return venue

    with patch.object(market_stream, "HEARTBEAT", heartbeat):
        venue = asyncio.run(scenario())
    assert venue.pings(0) >= 3
    assert heartbeat.snapshot()["reconnects"] == 0


def test_after_a_disconnect_the_stream_resubscribes_and_resyncs_from_rest_again() -> None:
    state = MarketStreamState(["BTC", "ETH"], ["1m"])
    resyncs = Resyncs()
    heartbeat = fresh_heartbeat()

    async def scenario() -> FakeHyperliquidSocket:
        async with FakeHyperliquidSocket(expected_subscriptions=6, script=lambda index: [book_message("BTC")],
                                         close_after_script={0}) as venue:
            task = asyncio.create_task(run_market_stream(state, resyncs, url=venue.url, ping_interval_s=30, silence_s=10,
                                                         reconnect_min_s=0.01))
            try:
                await eventually(lambda: len(venue.connections) == 2 and len(venue.subscriptions(1)) == 6
                                 and resyncs.calls == 2)
            finally:
                await stop(task)
            return venue

    with patch.object(market_stream, "HEARTBEAT", heartbeat):
        venue = asyncio.run(scenario())
    assert venue.subscriptions(1) == venue.subscriptions(0) == subscriptions(["BTC", "ETH"], ["1m"])
    snap = heartbeat.snapshot()
    assert snap["attempts"] == 2 and snap["reconnects"] == 1 and snap["counts_1h"]["resyncs"] == 2


def test_a_venue_that_goes_silent_is_treated_as_disconnected_and_reconnected() -> None:
    state = MarketStreamState(["BTC"], [])
    heartbeat = fresh_heartbeat()

    async def scenario() -> FakeHyperliquidSocket:
        async with FakeHyperliquidSocket(expected_subscriptions=2, answer_pings=False) as venue:
            task = asyncio.create_task(run_market_stream(state, Resyncs(), url=venue.url, ping_interval_s=0.05,
                                                         silence_s=0.3, reconnect_min_s=0.01))
            try:
                await eventually(lambda: len(venue.connections) >= 2)
            finally:
                await stop(task)
            return venue

    with patch.object(market_stream, "HEARTBEAT", heartbeat):
        venue = asyncio.run(scenario())
    assert venue.pings(0) >= 1, "the unanswered heartbeat was still sent"
    snap = heartbeat.snapshot()
    assert snap["reconnects"] >= 1 and snap["last_error"] == "TimeoutError"


def test_a_failed_resync_is_recorded_without_dropping_the_connection() -> None:
    state = MarketStreamState(["BTC"], [])
    heartbeat = fresh_heartbeat()

    async def failing_resync() -> dict:
        raise ConnectionError("venue REST unavailable")

    async def scenario() -> None:
        async with FakeHyperliquidSocket(expected_subscriptions=2, script=lambda index: [book_message("BTC")]) as venue:
            task = asyncio.create_task(run_market_stream(state, failing_resync, url=venue.url, ping_interval_s=30, silence_s=10))
            try:
                await eventually(lambda: heartbeat.snapshot()["last_error"] is not None and state.book("BTC", now_ms(), 5_000))
            finally:
                await stop(task)

    with patch.object(market_stream, "HEARTBEAT", heartbeat):
        asyncio.run(scenario())
    snap = heartbeat.snapshot()
    assert snap["last_error"] == "resync: ConnectionError" and snap["state"] == "connected" and snap["reconnects"] == 0
