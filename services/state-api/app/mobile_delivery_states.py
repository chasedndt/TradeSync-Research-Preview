"""Alert delivery states, each read from one fact the outbox stores: nothing is inferred, nothing is invented.

The roadmap names six states for an alert. Each is a stored column or a stored status, and a row shows the
exact time the store holds for it, or nothing:

=================  ==============================================  =============================================
State              Stored fact                                     Time shown
=================  ==============================================  =============================================
``triggered``      the outbox row exists                           ``created_at``
``routed``         ``attempts > 0``: handed to a transport         ``attempted_at``, the latest attempt, with the
                   (ntfy or Web Push)                              transport and the attempt count
``delivered``      ``accepted_at`` is set: the provider or push    ``accepted_at``. Acceptance is not proof that a
                   service accepted it                             phone showed it
``acknowledged``   ``acknowledged_at`` is set                      ``acknowledged_at``, with who: the operator, or a
                                                                   tap proven by its single-use token
``expired``        ``status = 'expired'``                          ``expires_at``, the end of its window: the sweep
                                                                   that expires a row stores no time of its own
``dead_lettered``  ``status = 'dead_letter'``                      ``dead_lettered_at``, with the stored reason
=================  ==============================================  =============================================

The stored status travels beside the states verbatim. A row written before dead letters were recorded keeps
``failed``; it is not called dead-lettered, because no dead letter was stored for it.

What a row carries is declared here (``COLUMNS``), so a column added to the outbox later cannot reach this
read by merely existing. None of them is a device secret: no ntfy topic, push endpoint, token digest,
provider message id or device label. That is why this reading needs no mobile control key, while the
keyed ledger (``GET /state/mobile-alerts/ledger``) keeps the key it has.

Pure: rows in, plain data out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "mobile_delivery_states_v1"

STATES = ("triggered", "routed", "delivered", "acknowledged", "expired", "dead_lettered")

DEFINITIONS = {
    "triggered": "The alert was queued in the outbox.",
    "routed": "It was handed to a transport (ntfy or Web Push) at least once; the time is the latest attempt.",
    "delivered": "The provider or push service accepted it. Acceptance is not proof that a phone showed it.",
    "acknowledged": "It was marked seen, by the operator or by a tap on the notification proven by its single-use token.",
    "expired": ("Its window ended before a provider accepted it; the time is the end of that window, because "
                "expiring a row stores no time of its own."),
    "dead_lettered": "It was given up on, with the reason stored at the time.",
}

# Every column that may leave this reading. The query names the same columns; a column not named here is dropped.
COLUMNS = (
    "id", "device_id", "platform", "kind", "status", "transport", "attempts", "created_at", "next_attempt_at",
    "attempted_at", "accepted_at", "acknowledged_at", "acknowledged_by", "dead_lettered_at", "dead_letter_reason",
    "last_error", "expires_at",
)

NOTE = (
    "Each state is a stored fact about one notification, shown with the exact time the outbox holds for it. "
    "Provider acceptance is not phone receipt. The stored status is shown as stored. No device secret is read: "
    "no topic, push endpoint, token or device label."
)


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def row_view(row: Mapping[str, Any]) -> dict[str, Any]:
    """One outbox row cut to its declared columns, with the states it reached."""
    kept = {column: _plain(row.get(column)) for column in COLUMNS}
    return {**kept, "states": states(kept)}


def states(row: Mapping[str, Any]) -> dict[str, dict[str, Any] | None]:
    """Each of the six states: the stored fact with its time, or None when the store holds no such fact."""
    attempts = row.get("attempts") or 0
    status = row.get("status")
    return {
        "triggered": {"at": row.get("created_at"), "kind": row.get("kind")},
        "routed": ({"at": row.get("attempted_at"), "transport": row.get("transport"), "attempts": attempts}
                   if attempts > 0 else None),
        "delivered": {"at": row.get("accepted_at"), "transport": row.get("transport")} if row.get("accepted_at") else None,
        "acknowledged": ({"at": row.get("acknowledged_at"), "by": row.get("acknowledged_by")}
                         if row.get("acknowledged_at") else None),
        "expired": {"at": row.get("expires_at"), "basis": "end of window"} if status == "expired" else None,
        "dead_lettered": ({"at": row.get("dead_lettered_at"), "reason": row.get("dead_letter_reason")}
                          if status == "dead_letter" else None),
    }


def counts(views: Iterable[Mapping[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    """How many of the rows reached each state, and how many carry each stored status."""
    reached = {name: 0 for name in STATES}
    stored: dict[str, int] = {}
    for view in views:
        for name, fact in (view.get("states") or {}).items():
            if fact is not None and name in reached:
                reached[name] += 1
        key = str(view.get("status"))
        stored[key] = stored.get(key, 0) + 1
    return reached, stored


def reading(rows: Iterable[Mapping[str, Any]], *, cap: int, days: int, window_from: str, window_to: str,
            generated_at: str, max_attempts: int, expiry_seconds: int) -> dict[str, Any]:
    """The windowed reading: rows newest first, bounded, with the counts over the rows shown."""
    fetched = list(rows)
    views = [row_view(row) for row in fetched[:cap]]
    reached, stored = counts(views)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "window": {"days": days, "from": window_from, "to": window_to},
        "states": list(STATES),
        "definitions": DEFINITIONS,
        "rows": views,
        "row_count": len(views),
        "row_cap": cap,
        "truncated": len(fetched) > cap,
        "counts": reached,
        "stored_statuses": stored,
        "counts_basis": "the rows shown; a truncated window holds more",
        "max_attempts": max_attempts,
        "expiry_seconds": expiry_seconds,
        "authority": "read_only",
        "note": NOTE,
    }
