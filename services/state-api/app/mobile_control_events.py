"""Generic phone notifications for control events: the paper kill switch engaged or cleared.

A phone receives these only after its operator confirmed a received test and opted in to control events
(``Preferences.control_events``). ``mobile_alert_devices.control_events_enabled_at`` (migration 037) keeps events
from before the opt-in from being sent. Each event queues one generic "attention" message: the template names no
symbol, balance, operator, reason or trade. Quiet hours and the rolling 24-hour budget apply exactly as they do to
paper lifecycle messages, through the same functions in ``mobile_alerts``, and a suppressed event is recorded, not
replayed.

``SOURCES`` lists where control events come from. The agent harness has no stop or start record on this branch;
once one exists as an append-only table, it is one more entry here.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from app.mobile_policy import Preferences

KEY_PREFIX = "control:"

# (source, SQL selecting the ids of the source's events on or after $1, from the last ten minutes, not yet queued
# for device $2). Older events are never sent: an outbox entry expires after ten minutes anyway.
SOURCES: tuple[tuple[str, str], ...] = (
    (
        "paper_kill_switch",
        "SELECT e.id FROM paper_kill_switch_events e WHERE e.action IN ('kill', 'resume') AND e.created_at >= $1 "
        "AND e.created_at > now() - interval '10 minutes' AND NOT EXISTS (SELECT 1 FROM mobile_alert_outbox o "
        "WHERE o.device_id = $2 AND o.dedupe_key = 'control:paper_kill_switch:' || e.id::text) "
        "ORDER BY e.created_at, e.id LIMIT 20",
    ),
)

# The lock the paper lifecycle producer takes, so the two never count one phone's budget at the same time.
PRODUCER_LOCK = 240914

QueueOrSuppress = Callable[[Any, Any, str, Preferences, int], Awaitable[int]]
BudgetUsed = Callable[[Any, Any], Awaitable[int]]


def dedupe_key(source: str, event_id: Any) -> str:
    return f"{KEY_PREFIX}{source}:{event_id}"


def _preferences(raw: Any) -> Preferences:
    return Preferences(**(json.loads(raw) if isinstance(raw, str) else raw or {}))


async def produce(pool, queue_or_suppress: QueueOrSuppress, budget_used: BudgetUsed) -> int:
    """Queue, or record as suppressed, each new control event for every opted-in phone; returns how many were handled."""
    handled = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", PRODUCER_LOCK)
            devices = await conn.fetch(
                "SELECT id, notification_preferences, control_events_enabled_at FROM mobile_alert_devices "
                "WHERE enabled AND control_events_enabled_at IS NOT NULL")
            for device in devices:
                preferences = _preferences(device["notification_preferences"])
                if not preferences.control_events:
                    continue
                used = await budget_used(conn, device["id"])
                for source, sql in SOURCES:
                    for event in await conn.fetch(sql, device["control_events_enabled_at"], device["id"]):
                        used = await queue_or_suppress(conn, device["id"], dedupe_key(source, event["id"]), preferences, used)
                        handled += 1
    return handled
