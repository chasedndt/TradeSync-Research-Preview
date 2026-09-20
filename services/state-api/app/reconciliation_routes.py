"""The five reconciliation views, served read-only beside the existing execution reconciliation.

``GET /state/execution/reconciliation`` already compares recorded decisions
against recorded orders. This serves the other five the roadmap names, from the
same kind of comparison: orphaned events, duplicate candidates, stale approvals,
partial orders and missing outcomes.

Every answer states the exact window it covered and the exact instant it was
taken, so a reading can be quoted later without ambiguity about what "the last
day" meant when it was produced. Nothing here writes, and nothing here can
place, amend, cancel or consume anything.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from app import reconciliation_queries as queries
from tradesync_core import reconciliation_views as views
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

router = APIRouter(tags=["reconciliation"])


def register(app, state) -> None:
    """Attach the reconciliation views."""

    @router.get("/state/reconciliation/views")
    async def reconciliation_views(
        hours: int = Query(queries.DEFAULT_WINDOW_HOURS, ge=1, le=queries.MAX_WINDOW_HOURS),
    ):
        """Where this system's own records disagree with each other.

        Five comparisons, each saying what it compared and over what window. A
        clean view is a result and is reported as one; a view that compared no
        record says that instead, which is not the same thing.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        taken_at = datetime.now(timezone.utc)
        window_from = taken_at - timedelta(hours=hours)
        window = f"{window_from.isoformat()} to {taken_at.isoformat()} ({hours}h)"
        now_s = taken_at.timestamp()

        async with state.pool.acquire() as conn:
            collected = await queries.collect(conn, hours)

        combined = views.combine([
            views.orphaned_events(collected["events"], collected["signals"], window=window),
            views.duplicate_candidates(collected["opportunities"], window=window),
            views.stale_approvals(collected["envelopes"], now_s, window=window),
            views.partial_orders(collected["orders"], now_s, window=window),
            views.missing_outcomes(collected["outcome_rows"], now_s, DEFAULT_HORIZONS_MINUTES, window=window),
        ])

        return {
            **combined,
            "generated_at": taken_at.isoformat(),
            "window": {
                "hours": hours,
                "from": window_from.isoformat(),
                "to": taken_at.isoformat(),
            },
            "row_cap_per_read": queries.ROW_CAP,
            "horizons_minutes": list(DEFAULT_HORIZONS_MINUTES),
            "authority": "read_only",
            "beside": (
                "GET /state/execution/reconciliation compares recorded decisions against recorded orders; "
                "these are the other five views."
            ),
        }

    app.include_router(router)
