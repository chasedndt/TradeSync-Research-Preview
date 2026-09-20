"""When a queued notification is tried again, when it is given up on, and when it counts as seen.

The policy is pure and the statements that write its outcomes live beside it, so there is one place that
decides what happens to an outbox row and one place that writes it. ``app/mobile_alerts.py`` owns the
provider call; this module never sends anything and never builds a message.

**Retry.** A claimed row is attempted once. A failure waits ``backoff_seconds(attempts)`` — fifteen seconds,
doubling, capped at two minutes — before the next attempt, and ``MAX_ATTEMPTS`` attempts is the end of it.
The whole ladder (15 + 30 + 60 + 120 = 225 seconds) fits inside the ten-minute expiry an outbox row is
enqueued with, so a row that keeps failing reaches its dead letter rather than quietly expiring first;
``test_mobile_delivery.py`` asserts that the two numbers stay consistent.

**Dead letter.** A row is given up on for one of two reasons, and the reason is kept on the row: the provider
refused in a way that will not change (a 4xx other than 429), or the attempt limit ran out. The reason text is
built here from an exception's class name and an HTTP status code only — never from a provider body, a topic,
a URL or a message — because the ledger is displayed.

**Acknowledgement.** Provider acceptance is not receipt, and receipt is not "seen". An acknowledgement is a
column, not a status: a row can be accepted, retried twice and then acknowledged, and folding that into one
status would lose the history. ``operator`` is a person attesting they saw it, through the control-key route;
``device`` is a tap on a Web Push notification, proven by the single-use token that notification carried
(app/mobile_ack_token.py, app/mobile_tap_ack.py). Nothing is recorded merely because a notification was shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import heavy_query, mobile_ack_token

MAX_ATTEMPTS = 5
FIRST_RETRY_SECONDS = 15
MAX_RETRY_SECONDS = 120
LEASE_SECONDS = 60
# The window app/mobile_alerts.enqueue gives a row. Kept here so the retry ladder can be checked against it.
EXPIRY_SECONDS = 600

ACKNOWLEDGED_BY = ("operator", "device")
RETRY = "retry"
DEAD_LETTER = "dead_letter"

EXHAUSTED_SWEEP_REASON = (
    f"No delivery within {MAX_ATTEMPTS} attempts; the row was still waiting or its lease had lapsed when the "
    "attempts ran out."
)


@dataclass(frozen=True)
class Outcome:
    """What one failed attempt means: try again after ``retry_in_seconds``, or stop with ``reason``."""

    status: str
    retry_in_seconds: int
    last_error: str
    reason: str | None = None


def backoff_seconds(attempts: int) -> int:
    """Seconds to wait before attempt ``attempts + 1``: fifteen, doubling, capped at two minutes."""
    if attempts < 1:
        raise ValueError("attempts counts the attempts already made, so it starts at one")
    return min(FIRST_RETRY_SECONDS * 2 ** (attempts - 1), MAX_RETRY_SECONDS)


def total_backoff_seconds(max_attempts: int = MAX_ATTEMPTS) -> int:
    """How long the whole retry ladder takes, so it can be compared with the expiry window."""
    return sum(backoff_seconds(attempt) for attempt in range(1, max_attempts))


def permanent(status_code: int | None) -> bool:
    """A refusal that will not change on a retry: a 4xx that is not rate limiting."""
    return status_code is not None and 400 <= status_code < 500 and status_code != 429


def failure(exc: BaseException) -> tuple[str, int | None]:
    """The two facts the ledger keeps about a failed attempt: a short name, and an HTTP status when there was one.

    A transport that knows better than its exception's class name says so in ``error_name`` (the Web Push sender
    does); a status comes from ``status_code`` or from an HTTP error's ``response``.
    """
    name = getattr(exc, "error_name", None) or type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return str(name)[:80], status if isinstance(status, int) else None


def outcome(attempts: int, error_name: str, status_code: int | None = None) -> Outcome:
    """What to do after a failed attempt. ``attempts`` counts the attempts made, including this one."""
    if permanent(status_code):
        return Outcome(DEAD_LETTER, 0, error_name,
                       f"The provider refused with HTTP {status_code}; only 429 and 5xx are tried again. "
                       f"Last error {error_name}.")
    if attempts >= MAX_ATTEMPTS:
        return Outcome(DEAD_LETTER, 0, error_name,
                       f"No delivery after {MAX_ATTEMPTS} attempts. Last error {error_name}"
                       + (f" (HTTP {status_code})." if status_code is not None else "."))
    return Outcome(RETRY, backoff_seconds(attempts), error_name)


SWEEP_EXPIRED_SQL = (
    "UPDATE mobile_alert_outbox SET status='expired', lease_until=NULL "
    "WHERE status IN ('queued','retry','sending') AND expires_at <= now()"
)

# A row that can never be claimed again becomes a dead letter with its reason, rather than sitting in 'retry'
# until it expires. A 'sending' row whose lease is still live is mid-attempt and is left alone.
SWEEP_EXHAUSTED_SQL = (
    "UPDATE mobile_alert_outbox SET status='dead_letter', dead_lettered_at=now(), "
    "dead_letter_reason=coalesce(dead_letter_reason, $2), lease_until=NULL "
    "WHERE attempts >= $1 AND status IN ('queued','retry','sending') "
    "AND (status <> 'sending' OR lease_until IS NULL OR lease_until < now())"
)

CLAIM_SQL = f"""WITH candidate AS (
  SELECT o.id FROM mobile_alert_outbox o JOIN mobile_alert_devices d ON d.id=o.device_id
  WHERE d.enabled AND o.expires_at>now() AND o.attempts<$1
  AND ((o.status IN ('queued','retry') AND o.next_attempt_at<=now())
       OR (o.status='sending' AND o.lease_until<now()))
  ORDER BY o.created_at FOR UPDATE OF o SKIP LOCKED LIMIT 1
) UPDATE mobile_alert_outbox o SET status='sending', attempts=attempts+1, attempted_at=now(),
  lease_until=now()+interval '{LEASE_SECONDS} seconds' FROM candidate c
  WHERE o.id=c.id RETURNING o.*"""

FAILURE_SQL = (
    "UPDATE mobile_alert_outbox SET status=$2, last_error=$3, lease_until=NULL, attempted_at=now(), "
    "next_attempt_at=now()+make_interval(secs => $4::double precision), "
    "dead_lettered_at=CASE WHEN $2='dead_letter' THEN now() ELSE dead_lettered_at END, "
    "dead_letter_reason=CASE WHEN $2='dead_letter' THEN $5 ELSE dead_letter_reason END WHERE id=$1"
)

ACKNOWLEDGE_SQL = (
    "UPDATE mobile_alert_outbox SET acknowledged_at=now(), acknowledged_by=$2 "
    "WHERE id=$1 AND acknowledged_at IS NULL RETURNING id, status, attempts, acknowledged_at, acknowledged_by"
)

LEDGER_SQL = (
    "SELECT o.id, o.device_id, d.label AS device_label, d.platform, o.kind, o.status, o.transport, o.attempts, "
    "o.created_at, o.next_attempt_at, o.attempted_at, o.accepted_at, o.confirmed_at, o.acknowledged_at, "
    "o.acknowledged_by, o.dead_lettered_at, o.dead_letter_reason, o.last_error, o.expires_at "
    "FROM mobile_alert_outbox o JOIN mobile_alert_devices d ON d.id=o.device_id "
    "ORDER BY o.created_at DESC LIMIT $1"
)

# The same delivery facts over a window, for the read that needs no control key: no device label, no confirmation
# attestation time, and nothing that addresses a phone (app/mobile_delivery_states.py declares the columns).
DELIVERY_STATES_SQL = (
    "SELECT o.id, o.device_id, d.platform, o.kind, o.status, o.transport, o.attempts, o.created_at, o.next_attempt_at, "
    "o.attempted_at, o.accepted_at, o.acknowledged_at, o.acknowledged_by, o.dead_lettered_at, o.dead_letter_reason, "
    "o.last_error, o.expires_at "
    "FROM mobile_alert_outbox o JOIN mobile_alert_devices d ON d.id=o.device_id "
    "WHERE o.created_at > now() - make_interval(days => $1) ORDER BY o.created_at DESC LIMIT $2"
)

READ_SQL = (
    "SELECT id, status, attempts, acknowledged_at, acknowledged_by FROM mobile_alert_outbox WHERE id=$1 FOR UPDATE"
)


async def sweep(conn) -> None:
    """Expire rows past their window, dead-letter rows that can never be attempted again, drop spent tap tokens."""
    await conn.execute(SWEEP_EXPIRED_SQL)
    await conn.execute(SWEEP_EXHAUSTED_SQL, MAX_ATTEMPTS, EXHAUSTED_SWEEP_REASON)
    await conn.execute(mobile_ack_token.CLEAR_EXPIRED_SQL)


async def record_failure(conn, event_id, result: Outcome) -> None:
    """Write one failed attempt: the next attempt time, or the dead letter and why."""
    await conn.execute(FAILURE_SQL, event_id, result.status, result.last_error,
                       float(result.retry_in_seconds), result.reason)


async def acknowledge(conn, event_id, by: str) -> dict[str, Any]:
    """Record that an alert was seen. Idempotent: the first acknowledgement is the one kept.

    Returns ``{"outcome": ...}`` where the outcome is ``acknowledged``, ``already_acknowledged``,
    ``not_found`` or ``never_attempted``.
    """
    if by not in ACKNOWLEDGED_BY:
        raise ValueError(f"An acknowledgement comes from {' or '.join(ACKNOWLEDGED_BY)}")
    async with conn.transaction():
        row = await conn.fetchrow(READ_SQL, event_id)
        if row is None:
            return {"outcome": "not_found"}
        if row["acknowledged_at"] is not None:
            return {"outcome": "already_acknowledged", "acknowledged_at": row["acknowledged_at"],
                    "acknowledged_by": row["acknowledged_by"]}
        if not row["attempts"]:
            # Nothing has been attempted, so nothing could have been seen.
            return {"outcome": "never_attempted", "status": row["status"]}
        written = await conn.fetchrow(ACKNOWLEDGE_SQL, event_id, by)
        return {"outcome": "acknowledged", "acknowledged_at": written["acknowledged_at"],
                "acknowledged_by": written["acknowledged_by"], "status": written["status"],
                "attempts": written["attempts"]}


async def ledger(conn, limit: int) -> list[dict[str, Any]]:
    """The newest outbox rows with every delivery fact on them, for the Cockpit's delivery ledger."""
    return [dict(row) for row in await conn.fetch(LEDGER_SQL, limit)]


async def ledger_window(conn, days: int, cap: int) -> list[dict[str, Any]]:
    """Outbox rows queued within the last ``days``, newest first, one past ``cap`` so truncation can be told."""
    rows = await heavy_query.fetch(conn, "mobile:delivery-states", DELIVERY_STATES_SQL, days, cap + 1)
    return [dict(row) for row in rows]
