"""Where the agent harness kill switch is kept: ``ops/migrations/034``, or memory without a database (tests, tooling).

One control row holds what the operator asked for (``running`` or ``stopped``, who, why, when), the
command the host control process should apply, the command it claimed, and the last result it
reported. Every request, claim and result is also an audit row, which the database refuses to update
or delete. A request, a claim and a report each take the control row's lock, so they never interleave,
and each command has at most one request, one claim and one result.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

COLUMNS = ("desired_state, operator, reason, requested_at, command_id, claimed_command_id, claimed_at, result_command_id, "
           "result_status, result_command, result_exit_status, result_is_active, result_detail, result_at")
EVENT_COLUMNS = ("id, created_at, kind, command_id, desired_state, previous_state, operator, reason, command, exit_status, "
                 "is_active, detail")

CURRENT_SQL = f"SELECT {COLUMNS} FROM agent_harness_control WHERE singleton"
LOCK_SQL = f"{CURRENT_SQL} FOR UPDATE"
REQUEST_SQL = ("UPDATE agent_harness_control SET desired_state = $1, operator = $2, reason = $3, requested_at = clock_timestamp(), "
               f"command_id = $4 WHERE singleton RETURNING {COLUMNS}")
CLAIM_SQL = "UPDATE agent_harness_control SET claimed_command_id = $1, claimed_at = clock_timestamp() WHERE singleton"
RESULT_SQL = ("UPDATE agent_harness_control SET result_command_id = $1, result_status = $2, result_command = $3, "
              "result_exit_status = $4, result_is_active = $5, result_detail = $6, result_at = clock_timestamp() WHERE singleton")
EVENT_SQL = ("INSERT INTO agent_harness_control_events (id, kind, command_id, desired_state, previous_state, operator, reason, "
             "command, exit_status, is_active, detail) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)")
COMMAND_EVENTS_SQL = "SELECT kind, desired_state FROM agent_harness_control_events WHERE command_id = $1"
HISTORY_SQL = f"SELECT {EVENT_COLUMNS} FROM agent_harness_control_events ORDER BY created_at DESC, id DESC LIMIT $1"

SEED_OPERATOR = "migration 034"
SEED_REASON = "Agent harness kill switch installed; the gateway is left as it was"
RESULTS = frozenset({"applied", "failed"})
MISSING = "agent harness control row missing"


class ControlMissing(LookupError):
    """No control row: migration 034 is not applied, or the row was removed."""


_memory: dict[str, Any] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def reset_memory() -> None:
    """The state a fresh migration leaves: running, no command, no history."""
    _memory.clear()
    _memory["row"] = {
        "desired_state": "running", "operator": SEED_OPERATOR, "reason": SEED_REASON, "requested_at": _now(),
        "command_id": None, "claimed_command_id": None, "claimed_at": None, "result_command_id": None, "result_status": None,
        "result_command": None, "result_exit_status": None, "result_is_active": None, "result_detail": None, "result_at": None,
    }
    _memory["events"] = []


reset_memory()


def claim_verdict(row: dict[str, Any], command_id: uuid.UUID, kinds: set[str]) -> str:
    """'claimed' only for the current command, requested and neither claimed nor reported yet."""
    if "requested" not in kinds:
        return "unknown"
    if kinds & RESULTS:
        return "reported"
    if row["command_id"] != command_id:
        return "superseded"
    return "already_claimed" if "applying" in kinds else "claimed"


def report_verdict(kinds: set[str]) -> str:
    if "requested" not in kinds:
        return "unknown"
    return "duplicate" if kinds & RESULTS else "recorded"


def keeps_current_result(row: dict[str, Any], command_id: uuid.UUID) -> bool:
    """A late result for an older command is audited, but does not replace the current command's result."""
    return command_id != row["command_id"] and row["result_command_id"] is not None and row["result_command_id"] == row["command_id"]


def _memory_row() -> dict[str, Any]:
    row = _memory.get("row")
    if row is None:
        raise ControlMissing(MISSING)
    return row


def _memory_events(command_id: uuid.UUID) -> list[dict[str, Any]]:
    return [event for event in _memory["events"] if event["command_id"] == command_id]


def _memory_event(kind: str, command_id: uuid.UUID, desired: str, **fields: Any) -> None:
    event = {"id": uuid.uuid4(), "created_at": _now(), "kind": kind, "command_id": command_id, "desired_state": desired,
             "previous_state": None, "operator": None, "reason": None, "command": None, "exit_status": None, "is_active": None,
             "detail": None, **fields}
    _memory["events"].insert(0, event)


async def current(pool) -> dict[str, Any] | None:
    if not pool:
        row = _memory.get("row")
        return dict(row) if row is not None else None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(CURRENT_SQL)
    return dict(row) if row is not None else None


async def request(pool, desired: str, operator: str, reason: str) -> tuple[dict[str, Any], str]:
    """Ask for a state and issue a new command for the host: (the control row after, the state it replaced)."""
    command_id = uuid.uuid4()
    if not pool:
        row = _memory_row()
        previous = row["desired_state"]
        row.update(desired_state=desired, operator=operator, reason=reason, requested_at=_now(), command_id=command_id)
        _memory_event("requested", command_id, desired, previous_state=previous, operator=operator, reason=reason)
        return dict(row), previous
    async with pool.acquire() as conn:
        async with conn.transaction():
            before = await conn.fetchrow(LOCK_SQL)
            if before is None:
                raise ControlMissing(MISSING)
            row = await conn.fetchrow(REQUEST_SQL, desired, operator, reason, command_id)
            await conn.execute(EVENT_SQL, uuid.uuid4(), "requested", command_id, desired, before["desired_state"], operator, reason,
                               None, None, None, None)
    return dict(row), before["desired_state"]


async def claim(pool, command_id: uuid.UUID) -> str:
    """Take the current command before anything runs. Only 'claimed' writes; every other answer means: do not run it."""
    if not pool:
        row = _memory_row()
        verdict = claim_verdict(row, command_id, {event["kind"] for event in _memory_events(command_id)})
        if verdict == "claimed":
            row.update(claimed_command_id=command_id, claimed_at=_now())
            _memory_event("applying", command_id, row["desired_state"])
        return verdict
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(LOCK_SQL)
            if row is None:
                raise ControlMissing(MISSING)
            kinds = {event["kind"] for event in await conn.fetch(COMMAND_EVENTS_SQL, command_id)}
            verdict = claim_verdict(dict(row), command_id, kinds)
            if verdict == "claimed":
                await conn.execute(CLAIM_SQL, command_id)
                await conn.execute(EVENT_SQL, uuid.uuid4(), "applying", command_id, row["desired_state"], None, None, None, None, None,
                                   None, None)
    return verdict


async def report(pool, command_id: uuid.UUID, status: str, command: str, exit_status: int | None, is_active: str,
                 detail: str) -> str:
    """Record what the host ran and what systemd said afterwards, once per command: 'recorded', 'duplicate' or 'unknown'."""
    if not pool:
        row = _memory_row()
        events = _memory_events(command_id)
        verdict = report_verdict({event["kind"] for event in events})
        if verdict == "recorded":
            desired = next(event["desired_state"] for event in events if event["kind"] == "requested")
            if not keeps_current_result(row, command_id):
                row.update(result_command_id=command_id, result_status=status, result_command=command, result_exit_status=exit_status,
                           result_is_active=is_active, result_detail=detail, result_at=_now())
            _memory_event(status, command_id, desired, command=command, exit_status=exit_status, is_active=is_active, detail=detail)
        return verdict
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(LOCK_SQL)
            if row is None:
                raise ControlMissing(MISSING)
            events = await conn.fetch(COMMAND_EVENTS_SQL, command_id)
            verdict = report_verdict({event["kind"] for event in events})
            if verdict == "recorded":
                desired = next(event["desired_state"] for event in events if event["kind"] == "requested")
                if not keeps_current_result(dict(row), command_id):
                    await conn.execute(RESULT_SQL, command_id, status, command, exit_status, is_active, detail)
                await conn.execute(EVENT_SQL, uuid.uuid4(), status, command_id, desired, None, None, None, command, exit_status,
                                   is_active, detail)
    return verdict


async def history(pool, limit: int = 50) -> list[dict[str, Any]]:
    """Every request, claim and result, newest first."""
    if not pool:
        return [dict(event) for event in _memory["events"][:limit]]
    async with pool.acquire() as conn:
        rows = await conn.fetch(HISTORY_SQL, limit)
    return [dict(row) for row in rows]
