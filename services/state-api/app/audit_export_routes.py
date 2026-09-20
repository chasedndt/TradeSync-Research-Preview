"""The audit export: decisions, approvals, orders, outcomes and paper activity over a chosen window.

Two renderings of one bounded read. ``GET /state/audit/export`` answers JSON
with every section; ``GET /state/audit/export.csv`` answers one named section as
CSV, because a single CSV cannot hold seven different row shapes without
inventing a column that means nothing. The paper sections (rehearsals, managed
paper positions and their lifecycle transitions) are read by
``app.audit_export_paper_queries``.

The bounds are stated in the answer itself, and a section that reached its cap
says so. No secret, token or key reaches either rendering: the sections declare
their columns and every free-form payload is scrubbed by key
(``tradesync_core.audit_export``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response

from app import audit_export_queries as queries
from tradesync_core import audit_export

router = APIRouter(tags=["audit"])

DEFAULT_WINDOW_DAYS = 7


def _window(days: int) -> tuple[datetime, datetime]:
    taken_at = datetime.now(timezone.utc)
    return taken_at - timedelta(days=days), taken_at


def register(app, state) -> None:
    """Attach the audit export routes."""

    def pool():
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return state.pool

    @router.get("/state/audit/export")
    async def audit_export_json(
        days: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=audit_export.MAX_WINDOW_DAYS),
        rows: int = Query(audit_export.MAX_ROWS_PER_SECTION, ge=1, le=audit_export.MAX_ROWS_PER_SECTION),
    ):
        """Every section over the window, with the digests the rows already store.

        ``content_digest`` is over the sections only, so the same rows produce
        the same digest whenever the export was taken and an export can be
        checked against the rows it came from.
        """
        window_from, taken_at = _window(days)
        async with pool().acquire() as conn:
            sections = await queries.collect(conn, days, rows)
        return audit_export.build(
            sections,
            window_days=float(days),
            window_from=window_from.isoformat(),
            window_to=taken_at.isoformat(),
            generated_at=taken_at.isoformat(),
            cap=rows,
        )

    @router.get("/state/audit/export.csv")
    async def audit_export_csv(
        section: str = Query(..., description="decisions, approvals, orders, outcomes, paper_rehearsals, paper_positions "
                                                     "or paper_position_events"),
        days: int = Query(DEFAULT_WINDOW_DAYS, ge=1, le=audit_export.MAX_WINDOW_DAYS),
        rows: int = Query(audit_export.MAX_ROWS_PER_SECTION, ge=1, le=audit_export.MAX_ROWS_PER_SECTION),
    ):
        """One section as CSV, with the section's declared columns as its header.

        The bounds that applied travel in the response headers, so a spreadsheet
        that cannot show them is not the only copy of that fact.
        """
        if section not in audit_export.SECTIONS:
            raise HTTPException(
                status_code=422,
                detail=f"{section!r} is not an exportable section; expected one of "
                       f"{', '.join(sorted(audit_export.SECTIONS))}",
            )
        window_from, taken_at = _window(days)
        async with pool().acquire() as conn:
            fetched = await queries.fetch_section(conn, section, days, rows)
        built = audit_export.section(section, fetched, cap=rows)
        text = audit_export.to_csv(section, built["rows"])
        return Response(
            content=text,
            media_type="text/csv; charset=utf-8",
            headers={
                "X-Export-Generated-At": taken_at.isoformat(),
                "X-Export-Window-From": window_from.isoformat(),
                "X-Export-Window-To": taken_at.isoformat(),
                "X-Export-Row-Count": str(built["row_count"]),
                "X-Export-Row-Cap": str(built["row_cap"]),
                "X-Export-Truncated": "true" if built["truncated"] else "false",
                "X-Export-Content-Digest": built["content_digest"],
                "X-Export-Redacted-Fields": str(built["redacted_fields"]),
                "Content-Disposition": f'attachment; filename="tradesync-{section}-{days}d.csv"',
            },
        )

    app.include_router(router)
