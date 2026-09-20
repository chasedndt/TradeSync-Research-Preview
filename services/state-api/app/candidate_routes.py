"""A quarantined Strike Zone or Pine alert turned into a proposed, review-only trade candidate.

Moved out of ``app/main.py`` unchanged. ``register`` returns the handler, which the
ChaseOS Gate route calls to re-extract a candidate rather than trust one it is given.
"""

import json
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query

from tradesync_core import normalize_symbol
from tradesync_core.strike_zone import (
    ReceiptError,
    to_trade_candidate,
    validate_receipt,
)

router = APIRouter()


def register(app, state):
    """Attach the candidate extraction route and return its handler."""

    @router.post("/state/quarantine/{item_id}/extract-candidate", tags=["quarantine"])
    async def extract_trade_candidate(item_id: str, validity_hours: int = Query(4, ge=1, le=72)):
        """Turn a quarantined Strike Zone / Pine alert into a proposed candidate.

        This is the **extraction** step of quarantine -> extraction -> proposed
        delta -> approved promotion. It reads stored material and returns a
        `trade_candidate_v1` proposal. Nothing is promoted here and no authority is
        granted: the candidate is `review_only` at `level_0_observation_only` with
        execution disabled, and those fields are written by the adapter rather than
        read from the alert.

        A receipt that tried to set its own authority is refused with the field
        named. A Pine script is a text file on a third party's server and anyone
        holding the alert URL can aim it here; if it could set
        `live_execution_allowed` this endpoint would be a remote execution
        primitive.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        async with state.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, source, accepted, payload, received_at, observed_at
                FROM quarantine_intake WHERE id = $1::uuid
                """,
                item_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="quarantine item not found")
        if row["source"] not in {"tradingview", "strike_zone"}:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"source {row['source']!r} does not carry Pine receipts; "
                    "candidates are extracted from tradingview or strike_zone items"
                ),
            )
        if not row["accepted"]:
            # A refused submission is stored so the operator can see what was tried.
            # Building a candidate from one would launder it into research material.
            raise HTTPException(
                status_code=409,
                detail="this item was refused at intake; a candidate cannot be built from it",
            )

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        # The webhook stores the alert body under "alert"; a direct submission may
        # carry the receipt at the top level.
        receipt_body = payload.get("alert") if isinstance(payload.get("alert"), dict) else payload

        try:
            receipt = validate_receipt(receipt_body)
            candidate = to_trade_candidate(
                receipt,
                canonical_symbol=normalize_symbol(receipt["ticker"]),
                asset=receipt["ticker"].split("USD")[0] or receipt["ticker"],
                observed_at=(row["observed_at"] or row["received_at"]),
                validity=timedelta(hours=validity_hours),
                source_item_id=str(row["id"]),
            )
        except ReceiptError as exc:
            raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}")

        return {
            "quarantine_id": str(row["id"]),
            "candidate": candidate,
            "status": "proposed",
            "authority": "none",
            "note": (
                "A proposal, not a promotion. The candidate is review_only at "
                "level_0_observation_only with execution disabled; the paper ledger "
                "re-checks those invariants independently before evaluating it."
            ),
        }

    app.include_router(router)
    return extract_trade_candidate
