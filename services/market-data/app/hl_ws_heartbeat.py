"""The application heartbeat every Hyperliquid websocket in this service sends.

Hyperliquid closes a connection that has not sent it a message for 60 seconds
(API docs, "Timeouts and heartbeats"). A subscription counts only once, so a
socket that subscribes and then only listens is closed a minute later unless it
keeps talking. The venue asks for ``{"method": "ping"}`` and answers
``{"channel": "pong"}``; websocket protocol ping frames are not what it counts.

The ping is sent from the receive loop itself rather than from a separate task:
``receive`` waits for the next frame no longer than the time until the next
ping is due, sends the ping when it is, and gives up once nothing at all has
arrived for ``silence_s``. A pong is a frame, so a live connection is never
mistaken for a silent one, and a dead one is noticed within ``silence_s``.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable

PING = json.dumps({"method": "ping"})
# Well inside the venue's 60-second limit, so one delayed ping cannot end the connection.
PING_INTERVAL_S = float(os.getenv("HYPERLIQUID_WS_PING_INTERVAL_S", "20"))


def is_pong(message: Any) -> bool:
    return isinstance(message, dict) and message.get("channel") == "pong"


class PingSchedule:
    """When the next ping is due on one connection, and how many were sent."""

    def __init__(self, interval_s: float = PING_INTERVAL_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.interval_s = interval_s
        self._clock = clock
        self._last = clock()
        self.sent = 0

    def due_in(self) -> float:
        return max(0.0, self.interval_s - (self._clock() - self._last))

    async def ping_if_due(self, ws: Any) -> bool:
        if self.due_in() > 0:
            return False
        await ws.send(PING)
        self._last = self._clock()
        self.sent += 1
        return True


async def receive(ws: Any, pings: PingSchedule, silence_s: float, clock: Callable[[], float] = time.monotonic) -> Any:
    """The next frame, sending the heartbeat whenever it falls due.

    Raises ``TimeoutError`` when nothing has arrived for ``silence_s``: with a
    ping every ``pings.interval_s`` a live venue always answers well inside that.
    """
    started = clock()
    while True:
        await pings.ping_if_due(ws)
        remaining = silence_s - (clock() - started)
        if remaining <= 0:
            raise TimeoutError(f"nothing received from Hyperliquid for {silence_s:.0f}s")
        wait = min(pings.due_in() or pings.interval_s, remaining)
        try:
            return await asyncio.wait_for(ws.recv(), timeout=max(wait, 0.001))
        except asyncio.TimeoutError:
            continue
