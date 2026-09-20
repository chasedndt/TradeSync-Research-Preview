"""The agent harness kill switch over HTTP: the Cockpit's switch and history, and the host control process's queue.

- ``GET /state/agents/harness/control``: what was asked for, the host's progress and last result, the
  gateway's heartbeat, whether TradeSync calls Hermes, one sentence on whether these agree, and the audit.
- ``POST /state/agents/harness/control``: stop or start, naming the operator and the reason, with
  ``confirm: true``. TradeSync's own callers refuse, or resume, from their next call; the host control
  process applies the command to the gateway.
- ``GET /state/agents/harness/gate``: the short answer core-scorer reads before it asks.
- ``GET /state/agents/harness/control/command``: the host control process's poll, the current command
  while it has no result. When the host last polled is kept in memory only.
- ``POST /state/agents/harness/control/claim`` and ``.../report``: the host takes a command before it runs
  anything (a command is claimed once) and records the command, its exit status and
  ``systemctl --user is-active`` afterwards (once per command).

Every change passes the access guard (``app/asgi.py``). ``AskGate`` is added here so that the ask route in
``app.main`` refuses while the harness is stopped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable

from fastapi import APIRouter, HTTPException, Query

from app import harness_control_rules as rules
from app import harness_control_store as store
from app import harness_gate, hermes_link
from app.harness_control_models import HarnessChange, HostClaim, HostReport

router = APIRouter(tags=["agents"])

CLAIM_REFUSALS = {
    "unknown": (404, "No such agent harness command."),
    "superseded": (409, "A newer stop or start replaced this command; it must not run."),
    "already_claimed": (409, "This command was already claimed; a command is never handed out to run twice."),
    "reported": (409, "This command already has a result."),
}

_host: dict[str, datetime | None] = {"last_poll_at": None}


async def _stored(call: Awaitable[Any]) -> Any:
    """A store call, with a missing or unreadable control row answered as 503 rather than as a server error."""
    try:
        return await call
    except store.ControlMissing:
        raise HTTPException(status_code=503, detail=rules.MISSING_TEXT) from None
    except Exception as exc:  # database unavailable, or migration 034 not applied
        raise HTTPException(status_code=503, detail=rules.unreadable_text(type(exc).__name__)) from None


def register(app, state) -> None:
    def pool():
        return getattr(state, "pool", None)

    async def view(limit: int = 50) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        row = await _stored(store.current(pool()))
        if row is None:
            raise HTTPException(status_code=503, detail=rules.MISSING_TEXT)
        link = hermes_link.status_now()
        host = rules.host_view(row, _host["last_poll_at"], now)
        reason = rules.refusal_text(row)
        return {
            "schema_version": "agent_harness_control_v1",
            "generated_at": rules.iso(now),
            "desired": rules.desired_view(row),
            "host": host,
            "gateway": rules.gateway_view(link),
            "gate": {"open": reason is None, "reason": reason},
            "agreement": rules.agreement(row, link, host, now),
            "history": [rules.event_view(event) for event in await _stored(store.history(pool(), limit))],
            "note": rules.NOTE,
        }

    @router.get("/state/agents/harness/control")
    async def get_control(limit: int = Query(50, ge=1, le=200)):
        return await view(limit)

    @router.post("/state/agents/harness/control")
    async def change_control(change: HarnessChange):
        row, previous = await _stored(store.request(pool(), change.desired_state, change.operator, change.reason))
        requested = {"desired_state": row["desired_state"], "previous_state": previous, "command_id": str(row["command_id"])}
        return {**await view(), "requested": requested}

    @router.get("/state/agents/harness/gate")
    async def get_gate():
        row, reason = await harness_gate.read(pool())
        return {"schema_version": "agent_harness_gate_v1", "open": reason is None, "reason": reason,
                "desired_state": row["desired_state"] if row else None,
                "requested_at": rules.iso(row["requested_at"]) if row else None}

    @router.get("/state/agents/harness/control/command")
    async def host_command():
        _host["last_poll_at"] = datetime.now(timezone.utc)
        row = await _stored(store.current(pool()))
        if row is None:
            raise HTTPException(status_code=503, detail=rules.MISSING_TEXT)
        status = rules.host_status(row)
        command = None
        if status in ("pending", "applying"):
            command = {"id": str(row["command_id"]), "desired_state": row["desired_state"], "status": status,
                       "requested_at": rules.iso(row["requested_at"]), "operator": row["operator"]}
        return {"schema_version": "agent_harness_command_v1", "command": command, "poll_interval_s": rules.POLL_INTERVAL_S}

    @router.post("/state/agents/harness/control/claim")
    async def host_claim(body: HostClaim):
        verdict = await _stored(store.claim(pool(), body.command_id))
        if verdict != "claimed":
            status_code, detail = CLAIM_REFUSALS[verdict]
            raise HTTPException(status_code=status_code, detail=detail)
        return {"claimed": True, "command_id": str(body.command_id)}

    @router.post("/state/agents/harness/control/report")
    async def host_report(body: HostReport):
        verdict = await _stored(store.report(pool(), body.command_id, body.status, body.command, body.exit_status,
                                             body.is_active, body.detail))
        if verdict == "unknown":
            raise HTTPException(status_code=404, detail="No such agent harness command.")
        return {"recorded": verdict == "recorded", "duplicate": verdict == "duplicate", "command_id": str(body.command_id)}

    app.include_router(router)
    app.add_middleware(harness_gate.AskGate, refusal=lambda: harness_gate.refusal(pool()))
