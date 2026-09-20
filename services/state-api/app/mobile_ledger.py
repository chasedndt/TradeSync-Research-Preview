"""The delivery ledger and acknowledgement routes.

- ``GET /state/mobile-alerts/ledger`` — the newest outbox rows with every delivery fact on them: status,
  attempts, the last error, when the last attempt was made, when the provider accepted it, whether it was
  acknowledged and by whom, and whether it was dead-lettered and why. Times are returned as they are stored,
  so the Cockpit can show an exact time rather than "recently".
- ``GET /state/mobile-alerts/delivery-states?days=&rows=`` — the same facts over a window of 1 to 31 days, as
  the six delivery states (app/mobile_delivery_states.py), for Activity & Evidence. It carries no device
  secret and no device label, so it needs no control key; the keyed ledger above keeps its key.
- ``POST /state/mobile-alerts/events/{event_id}/acknowledge`` — the operator records that an alert was seen. It
  needs the mobile control key, like every other mobile control route, and records the operator only: a phone
  acknowledges by tapping the notification, with the single-use token that notification carried
  (app/mobile_tap_ack.py), so ``device`` in the ledger always means a tap that was proven.

Neither route sends anything, and neither can create, approve or change a trade.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from app import mobile_delivery, mobile_delivery_states
from app.mobile_alerts import authorize

LEDGER_LIMIT = 50
MAX_LEDGER_LIMIT = 200
# The delivery-state window follows the audit export's bounds, so the Activity page offers one set of windows.
DELIVERY_DEFAULT_DAYS = 7
DELIVERY_MAX_DAYS = 31
DELIVERY_DEFAULT_ROWS = 200
DELIVERY_MAX_ROWS = 1000

NOTE = (
    "Provider acceptance is not phone receipt, and receipt is not proof anyone saw it. An acknowledgement is the "
    "operator saying so, or a tap on a Web Push notification proven by the single-use token it carried; nothing "
    "is recorded merely because a notification was shown. A dead letter keeps the reason it was given up on."
)
OPERATOR_ONLY = ("This route records the operator. A phone acknowledges by tapping the notification, with the "
                 "single-use token that notification carried.")


class Acknowledgement(BaseModel):
    by: str = "operator"


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    """One outbox row as the Cockpit reads it: ids as text, times as ISO, nothing invented."""
    return {key: (str(value) if isinstance(value, uuid.UUID) else _iso(value)) for key, value in row.items()}


def register(app, state) -> None:
    def pool():
        if getattr(state, "pool", None) is None:
            raise HTTPException(503, "Notification database unavailable")
        return state.pool

    @app.get("/state/mobile-alerts/ledger")
    async def delivery_ledger(request: Request, limit: int = Query(LEDGER_LIMIT, ge=1, le=MAX_LEDGER_LIMIT)):
        authorize(request)
        async with pool().acquire() as conn:
            rows = await mobile_delivery.ledger(conn, limit)
        return {
            "schema_version": "mobile_delivery_ledger_v1",
            "events": [ledger_row(row) for row in rows],
            "max_attempts": mobile_delivery.MAX_ATTEMPTS,
            "retry_seconds": [mobile_delivery.backoff_seconds(attempt)
                              for attempt in range(1, mobile_delivery.MAX_ATTEMPTS)],
            "expiry_seconds": mobile_delivery.EXPIRY_SECONDS,
            "note": NOTE,
        }

    @app.get("/state/mobile-alerts/delivery-states")
    async def delivery_states(
        days: int = Query(DELIVERY_DEFAULT_DAYS, ge=1, le=DELIVERY_MAX_DAYS),
        rows: int = Query(DELIVERY_DEFAULT_ROWS, ge=1, le=DELIVERY_MAX_ROWS),
    ):
        """Every notification queued in the window with the delivery states its stored facts establish.

        Read-only and keyless by construction: the rows carry no topic, push endpoint, token, provider id or
        device label. A database that cannot be read answers an error, never an empty window.
        """
        taken_at = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            fetched = await mobile_delivery.ledger_window(conn, days, rows)
        return mobile_delivery_states.reading(
            fetched, cap=rows, days=days, window_from=(taken_at - timedelta(days=days)).isoformat(),
            window_to=taken_at.isoformat(), generated_at=taken_at.isoformat(),
            max_attempts=mobile_delivery.MAX_ATTEMPTS, expiry_seconds=mobile_delivery.EXPIRY_SECONDS,
        )

    @app.post("/state/mobile-alerts/events/{event_id}/acknowledge")
    async def acknowledge(event_id: uuid.UUID, body: Acknowledgement, request: Request):
        authorize(request)
        if body.by != "operator":
            raise HTTPException(422, OPERATOR_ONLY)
        async with pool().acquire() as conn:
            try:
                result = await mobile_delivery.acknowledge(conn, event_id, body.by)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
        if result["outcome"] == "not_found":
            raise HTTPException(404, "No such notification")
        if result["outcome"] == "never_attempted":
            raise HTTPException(409, "That notification has not been attempted yet, so nothing could have been seen")
        return {**{key: _iso(value) for key, value in result.items()},
                "evidence": "An attestation that the alert was seen, not device telemetry"}
