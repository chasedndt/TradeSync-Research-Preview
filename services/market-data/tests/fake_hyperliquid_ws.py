"""A loopback stand-in for Hyperliquid's websocket, for the stream tests. Never the network.

It records every message each connection sends, answers ``{"method": "ping"}``
with ``{"channel": "pong"}`` (unless told not to), acknowledges each
subscription as the venue does, and once a connection has sent the expected
number of subscriptions it plays that connection's scripted messages and, if
asked, closes the connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Iterable

import websockets
from websockets.asyncio.server import serve


class FakeHyperliquidSocket:
    def __init__(
        self,
        *,
        expected_subscriptions: int,
        script: Callable[[int], Iterable[dict[str, Any]]] = lambda index: (),
        close_after_script: Iterable[int] = (),
        answer_pings: bool = True,
    ) -> None:
        self.expected_subscriptions = expected_subscriptions
        self.script = script
        self.close_after_script = set(close_after_script)
        self.answer_pings = answer_pings
        self.connections: list[list[dict[str, Any]]] = []

    async def __aenter__(self) -> "FakeHyperliquidSocket":
        self._server = await serve(self._handle, "127.0.0.1", 0)
        port = list(self._server.sockets)[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._server.close()
        await self._server.wait_closed()

    def subscriptions(self, index: int) -> list[dict[str, Any]]:
        return [m["subscription"] for m in self.connections[index] if m.get("method") == "subscribe"]

    def pings(self, index: int) -> int:
        return sum(1 for m in self.connections[index] if m == {"method": "ping"})

    async def _handle(self, ws: Any) -> None:
        index = len(self.connections)
        received: list[dict[str, Any]] = []
        self.connections.append(received)
        subscribed = 0
        try:
            async for raw in ws:
                message = json.loads(raw)
                received.append(message)
                if message.get("method") == "ping":
                    if self.answer_pings:
                        await ws.send(json.dumps({"channel": "pong"}))
                elif message.get("method") == "subscribe":
                    subscribed += 1
                    await ws.send(json.dumps({"channel": "subscriptionResponse", "data": message}))
                    if subscribed == self.expected_subscriptions:
                        for out in self.script(index):
                            await ws.send(json.dumps(out))
                        if index in self.close_after_script:
                            await ws.close()
                            return
        except websockets.ConnectionClosed:
            return


async def eventually(predicate: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition was not met in time")
        await asyncio.sleep(0.01)


async def stop(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def ctx_message(coin: str, mark: str = "100000.0") -> dict[str, Any]:
    return {"channel": "activeAssetCtx", "data": {"coin": coin, "ctx": {
        "funding": "0.0000125", "openInterest": "1000.5", "prevDayPx": "98000.0", "dayNtlVlm": "2500000000.0",
        "premium": "0.0001", "oraclePx": "99990.0", "markPx": mark, "midPx": "100000.5", "impactPxs": ["99999.0", "100002.0"]}}}


def book_message(coin: str, bid: str = "99999.0", ask: str = "100001.0", venue_time: int = 1_789_380_000_000) -> dict[str, Any]:
    return {"channel": "l2Book", "data": {"coin": coin, "time": venue_time, "levels": [
        [{"px": bid, "sz": "1.5", "n": 3}, {"px": "99990.0", "sz": "4.0", "n": 5}],
        [{"px": ask, "sz": "2.0", "n": 2}, {"px": "100010.0", "sz": "3.0", "n": 4}]]}}


def candle_message(coin: str, open_ms: int, interval: str = "1m", close: str = "100000.0") -> dict[str, Any]:
    step = 60_000 if interval == "1m" else 900_000
    return {"channel": "candle", "data": {"t": open_ms, "T": open_ms + step - 1, "s": coin, "i": interval,
                                          "o": "99950.0", "c": close, "h": "100020.0", "l": "99940.0", "v": "12.5", "n": 42}}
