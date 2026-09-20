"""TradeSync's side of the agent harness kill switch: no call to Hermes while it is stopped.

Every TradeSync caller of Hermes asks ``refusal(pool)`` first and reports the answer instead of calling:
the timeframe readings and their daily schedule, the thesis briefing, fleet directives and the live job
overlay that go to the gateway's jobs API, and core-scorer's claim reading (through
``GET /state/agents/harness/gate``). ``AskGate`` refuses ``POST /state/agents/harness/ask`` as well, so an
ask that skipped its caller's check still never reaches Hermes.

The switch is read from the database on every check, never cached, so a stop applies to the next call.
A switch that cannot be read (database unavailable, migration 034 not applied) is a refusal.

The heartbeat on ``/health`` keeps running while stopped: it is how the Cockpit tells a stopped gateway
from one that still answers.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app import harness_control_rules as rules
from app import harness_control_store as store

ASK_PATH = "/state/agents/harness/ask"
# 423 Locked: the request is well formed, but the operator has locked Hermes out.
STOPPED_STATUS = 423


async def read(pool) -> tuple[dict[str, Any] | None, str | None]:
    """The control row and the refusal it implies; a row that cannot be read is a refusal."""
    try:
        row = await store.current(pool)
        return row, rules.refusal_text(row)
    except Exception as exc:  # whatever keeps the switch from being read keeps Hermes uncalled
        return None, rules.unreadable_text(type(exc).__name__)


async def refusal(pool) -> str | None:
    """Why TradeSync must not call Hermes now, or None while the harness is running."""
    return (await read(pool))[1]


class AskGate:
    """ASGI middleware: ``POST /state/agents/harness/ask`` answers 423 with the reason while the harness is stopped."""

    def __init__(self, app: ASGIApp, *, refusal: Callable[[], Awaitable[str | None]]) -> None:
        self.app = app
        self._refusal = refusal

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"].upper() == "POST" and scope.get("path") == ASK_PATH:
            reason = await self._refusal()
            if reason:
                body = {"detail": reason, "harness": "stopped", "authority": "none"}
                await JSONResponse(body, status_code=STOPPED_STATUS)(scope, receive, send)
                return
        await self.app(scope, receive, send)
