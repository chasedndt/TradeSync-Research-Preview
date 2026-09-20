"""Recorded decisions compared with recorded orders.

Moved out of ``app/main.py`` unchanged. The five other reconciliation views are in
``app/reconciliation_routes.py``.
"""

from fastapi import APIRouter, HTTPException, Query

from app.execution_flags import execution_gate_enabled, paper_mode_enabled
from app.json_util import as_json as _as_json
from tradesync_core.reconciliation import reconcile

router = APIRouter()


def register(app, state) -> None:
    """Attach ``/state/execution/reconciliation``."""

    @router.get("/state/execution/reconciliation", tags=["execution"])
    async def get_execution_reconciliation(hours: int = Query(24, ge=1, le=720)):
        """Where the recorded intent and the recorded action disagree.

        Reads two of this system's own tables and reports divergence. It cannot
        place, amend or cancel anything, and it behaves identically in paper mode —
        which is the only mode this system runs in.

        A system that cannot tell you when its own records have drifted apart is
        less safe, and the day that matters is the day something did execute and the
        ledger disagrees. A clean result is reported as a result, not as silence.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        async with state.pool.acquire() as conn:
            decisions = await conn.fetch(
                """
                SELECT id::text AS id, requested
                FROM decisions
                WHERE created_at > now() - make_interval(hours => $1)
                ORDER BY created_at DESC
                """,
                hours,
            )
            orders = await conn.fetch(
                """
                SELECT id::text AS id, decision_id::text AS decision_id, request, dry_run
                FROM exec_orders
                WHERE created_at > now() - make_interval(hours => $1)
                ORDER BY created_at DESC
                """,
                hours,
            )

        result = reconcile(
            [{"id": r["id"], "requested": _as_json(r["requested"])} for r in decisions],
            [
                {
                    "id": r["id"],
                    "decision_id": r["decision_id"],
                    "request": _as_json(r["request"]),
                }
                for r in orders
            ],
        )

        return {
            "window_hours": hours,
            **result,
            "paper_mode": paper_mode_enabled(),
            "execution_gate_open": execution_gate_enabled(),
            "note": (
                "Read-only comparison of recorded decisions against recorded orders. "
                "Nothing here can place, amend or cancel an order."
            ),
        }

    app.include_router(router)
