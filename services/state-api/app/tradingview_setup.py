"""What an operator needs to point a TradingView alert at TradeSync, and what has arrived since.

``GET /state/tradingview/setup?limit=`` answers with:

- the public webhook URL, the alert contract and the message template to paste into TradingView, with the
  placeholder that stands where the secret goes (``tradesync_core.tradingview_webhook``);
- whether ``TRADINGVIEW_WEBHOOK_SECRET`` is configured: a boolean, never the value;
- the newest TradingView receipts held in quarantine: when, accepted or refused and why, indicator, ticker,
  interval and review state. No stored payload is returned, and the receiver never stores the secret.

An alert refused for authentication (a wrong or missing secret, a message that is not JSON, or one without an
indicator and a ticker) is refused before anything is stored, so it never appears among the receipts. The
receiver logs its reason codes on a line containing ``REFUSAL_LOG_MARKER``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Query

from tradesync_core.tradingview_webhook import (
    PUBLIC_WEBHOOK_URL,
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    SECRET_PLACEHOLDER,
    message_template,
)

router = APIRouter(tags=["quarantine"])

SECRET_ENV = "TRADINGVIEW_WEBHOOK_SECRET"
REFUSAL_LOG_MARKER = "tradingview alert refused"
FIELD_LIMIT = 160
DETAIL_LIMIT = 400
RECEIPTS_SQL = (
    "SELECT id, accepted, payload, reasons, received_at, reviewed_at, promoted_to FROM quarantine_intake "
    "WHERE source = 'tradingview' ORDER BY received_at DESC LIMIT $1"
)
NOTE = (
    "An alert lands in Knowledge intake as quarantined evidence awaiting review. It cannot score, approve or execute, "
    "and nothing trades from it. An alert refused for authentication is not stored; the state-api log records why."
)


def secret_configured() -> bool:
    """Whether the receiver has a secret to check alerts against. The value never leaves this function."""
    return bool(os.getenv(SECRET_ENV, "").strip())


def _loads(value: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, (str, bytes)) else value
    except ValueError:
        return None


def _text(value: Any, limit: int = FIELD_LIMIT) -> str:
    return "" if value is None else str(value).strip()[:limit]


def receipt_view(row: Any) -> dict[str, Any]:
    """One receipt as the setup panel lists it: nothing from the payload beyond the names that identify the alert."""
    payload = _loads(row["payload"])
    payload = payload if isinstance(payload, dict) else {}
    reasons = _loads(row["reasons"])
    reasons = reasons if isinstance(reasons, list) else []
    return {
        "id": str(row["id"]),
        "received_at": row["received_at"].isoformat(),
        "accepted": bool(row["accepted"]),
        "indicator": _text(payload.get("indicator")),
        "ticker": _text(payload.get("ticker")),
        "interval": _text(payload.get("interval")),
        "reasons": [{"code": _text(reason.get("code")), "detail": _text(reason.get("detail"), DETAIL_LIMIT)}
                    for reason in reasons if isinstance(reason, dict)],
        "review": "promoted" if row["promoted_to"] else "reviewed" if row["reviewed_at"] else "awaiting review",
    }


async def latest_receipts(pool, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    """The newest receipts, or none and the reason they could not be read."""
    if pool is None:
        return [], "The database is not connected, so receipts cannot be read."
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(RECEIPTS_SQL, limit)
    except Exception as exc:  # the setup facts still answer; only the error's type is named
        return [], f"Receipts could not be read ({type(exc).__name__})."
    return [receipt_view(row) for row in rows], None


def register(app, state) -> None:
    @router.get("/state/tradingview/setup")
    async def tradingview_setup(limit: int = Query(8, ge=1, le=50)):
        receipts, error = await latest_receipts(getattr(state, "pool", None), limit)
        return {
            "schema_version": "tradingview_setup_v1",
            "webhook_url": PUBLIC_WEBHOOK_URL,
            "secret_configured": secret_configured(),
            "contract": SCHEMA_VERSION,
            "required_fields": list(REQUIRED_FIELDS),
            "secret_placeholder": SECRET_PLACEHOLDER,
            "message_template": message_template(),
            "receipts": receipts,
            "receipts_error": error,
            "refusal_log_marker": REFUSAL_LOG_MARKER,
            "authority": "none",
            "note": NOTE,
        }

    app.include_router(router)
