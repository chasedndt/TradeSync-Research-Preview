"""Every Hyperliquid socket sends the venue's heartbeat: the market stream, the trade stream and both depth streams.

Hyperliquid closes a connection that has sent it nothing for 60 seconds. The
trade and depth streams only listen after subscribing, so before this they
depended on the venue treating protocol-level ping frames as messages.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from app import depth_stream, trade_stream
from app.depth_books import DepthBooks
from app.hl_ws_heartbeat import PING, PingSchedule, is_pong, receive
from app.trade_flow import TradeFlowTracker

from tests.fake_hyperliquid_ws import FakeHyperliquidSocket, eventually, stop


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class QuietSocket:
    """Delivers queued frames; otherwise waits, as an idle venue connection does."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.frames: asyncio.Queue = asyncio.Queue()

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return await self.frames.get()


def test_the_ping_is_the_venues_own_message_and_the_pong_is_recognised() -> None:
    assert json.loads(PING) == {"method": "ping"}
    assert is_pong({"channel": "pong"}) and not is_pong({"channel": "l2Book"}) and not is_pong("pong")


def test_a_ping_falls_due_once_per_interval() -> None:
    clock = Clock()
    schedule = PingSchedule(20.0, clock=clock)
    socket = QuietSocket()
    assert asyncio.run(schedule.ping_if_due(socket)) is False
    clock.now = 19.9
    assert schedule.due_in() == pytest.approx(0.1)
    clock.now = 20.0
    assert asyncio.run(schedule.ping_if_due(socket)) is True
    assert asyncio.run(schedule.ping_if_due(socket)) is False
    assert socket.sent == [PING] and schedule.sent == 1


def test_receive_pings_while_waiting_and_gives_up_only_after_silence() -> None:
    async def scenario():
        socket = QuietSocket()
        pings = PingSchedule(0.05)
        with pytest.raises(TimeoutError):
            await receive(socket, pings, silence_s=0.3)
        return socket

    socket = asyncio.run(scenario())
    assert socket.sent.count(PING) >= 4, "a silent wait still sends the heartbeat on schedule"


def test_receive_returns_a_frame_as_soon_as_one_arrives() -> None:
    async def scenario():
        socket = QuietSocket()
        await socket.frames.put('{"channel":"pong"}')
        return await receive(socket, PingSchedule(20.0), silence_s=5), socket.sent

    frame, sent = asyncio.run(scenario())
    assert frame == '{"channel":"pong"}' and sent == []


def test_the_trade_stream_sends_the_heartbeat() -> None:
    async def scenario() -> FakeHyperliquidSocket:
        async with FakeHyperliquidSocket(expected_subscriptions=2) as venue:
            task = asyncio.create_task(trade_stream.run_trade_stream(TradeFlowTracker(["BTC", "ETH"]), ["BTC", "ETH"],
                                                                     url=venue.url, ping_interval_s=0.05))
            try:
                await eventually(lambda: bool(venue.connections) and venue.pings(0) >= 3)
            finally:
                await stop(task)
            return venue

    venue = asyncio.run(scenario())
    assert venue.subscriptions(0) == [{"type": "trades", "coin": "BTC"}, {"type": "trades", "coin": "ETH"}]
    assert len(venue.connections) == 1, "answered pings keep the connection; no reconnect"


@pytest.mark.parametrize("n_sig_figs", [2, 3])
def test_each_depth_stream_sends_the_heartbeat(n_sig_figs: int) -> None:
    declared = depth_stream.HEARTBEATS[n_sig_figs]

    async def scenario() -> FakeHyperliquidSocket:
        async with FakeHyperliquidSocket(expected_subscriptions=1) as venue:
            task = asyncio.create_task(depth_stream.run_depth_stream(DepthBooks(), ["BTC"], n_sig_figs, url=venue.url,
                                                                     ping_interval_s=0.05))
            try:
                await eventually(lambda: bool(venue.connections) and venue.pings(0) >= 3)
            finally:
                await stop(task)
            return venue

    with patch.dict(depth_stream.HEARTBEATS, {n_sig_figs: declared}):
        venue = asyncio.run(scenario())
    assert venue.subscriptions(0) == [{"type": "l2Book", "coin": "BTC", "nSigFigs": n_sig_figs}]
    assert len(venue.connections) == 1
