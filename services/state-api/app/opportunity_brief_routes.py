"""Opportunity briefs: what an operator needs to judge a paper opportunity, read from stored records.

- ``GET /state/opportunity-briefs``: compact briefs for one status (live by
  default), newest first, for the list.
- ``GET /state/opportunity-briefs/{opportunity_id}``: one full brief, with its
  entry conditions, plan, evidence and provenance.

The assembly is ``tradesync_core.opportunity_brief``; this module only reads the
rows it needs. Read-only throughout: SELECTs, and the paper entry pause is read,
never changed. The path sits apart from ``/state/opportunities/...`` so no
parameterised route registered earlier can capture it.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.opportunity_lifecycle import EFFECTIVE_STATUS_SQL, EXPIRES_AT_SQL, status_filter
from app.thesis import execution_enabled
from tradesync_core import normalize_symbol
from tradesync_core.opportunity_brief import build_brief, compact

router = APIRouter(tags=["opportunities"])

# One row per opportunity: the regime label and the paper position are one-to-one
# with it (primary key and unique key), so neither join can repeat a row.
SELECT = f"""
SELECT o.id, o.symbol, o.timeframe, o.dir, o.bias, o.quality, o.snapshot_ts, o.links, o.confluence, o.signal_id,
       {EFFECTIVE_STATUS_SQL} AS status, {EXPIRES_AT_SQL} AS expires_at,
       r.regime, r.trailing_return_pct, r.lookback_minutes, r.reason AS regime_reason, r.computed_at AS regime_computed_at,
       p.id AS position_id, p.created_at AS position_opened_at, p.evidence_sha256, p.initial_plan, p.position_state,
       (SELECT x.entry_price FROM opportunity_outcomes x
         WHERE x.opportunity_id = o.id AND x.entry_price IS NOT NULL
         ORDER BY x.horizon_minutes LIMIT 1) AS entry_reference_price
FROM opportunities o
LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = o.id
LEFT JOIN managed_paper_positions p ON p.opportunity_id = o.id
"""

PAUSE_SQL = "SELECT entries_paused FROM managed_paper_control WHERE singleton"

LIST_NOTE = ("Each brief is read from stored records. Open one for its entry conditions, evidence and provenance; "
             "nothing is recalculated from a live price.")


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else (value or {})


def _epoch(value: Any) -> float | None:
    return value.timestamp() if isinstance(value, datetime) else None


def parts(row: Any) -> dict[str, Any]:
    """The stored records one brief is assembled from, in the shapes the assembler reads."""
    opportunity = {
        "id": str(row["id"]), "symbol": row["symbol"], "timeframe": row["timeframe"], "dir": row["dir"],
        "bias": row["bias"], "quality": row["quality"], "status": row["status"],
        "snapshot_ts_s": _epoch(row["snapshot_ts"]), "expires_at_s": _epoch(row["expires_at"]),
        "links": _json(row["links"]), "confluence": _json(row["confluence"]),
        "signal_id": str(row["signal_id"]) if row["signal_id"] else None,
    }
    regime = None if row["regime"] is None else {
        "regime": row["regime"], "trailing_return_pct": row["trailing_return_pct"],
        "lookback_minutes": row["lookback_minutes"], "reason": row["regime_reason"],
        "computed_at_s": _epoch(row["regime_computed_at"]),
    }
    position = None if row["position_id"] is None else {
        "id": str(row["position_id"]), "opened_at_s": _epoch(row["position_opened_at"]),
        "evidence_sha256": row["evidence_sha256"], "initial_plan": _json(row["initial_plan"]),
        "position_state": _json(row["position_state"]),
    }
    return {"opportunity": opportunity, "regime": regime, "position": position,
            "entry_reference_price": row["entry_reference_price"]}


async def entries_paused(conn) -> bool | None:
    """Whether new paper entries are paused; None when the control cannot be read."""
    try:
        value = await conn.fetchval(PAUSE_SQL)
    except Exception:  # the brief still stands; its paper state says the pause is unknown
        return None
    return value if isinstance(value, bool) else None


def register(app, state) -> None:
    def pool():
        if getattr(state, "pool", None) is None:
            raise HTTPException(status_code=503, detail="Opportunity database unavailable; no brief was read")
        return state.pool

    @router.get("/state/opportunity-briefs")
    async def list_briefs(
        status: str = Query("new", max_length=20),
        symbol: Optional[str] = Query(None, max_length=24),
        limit: int = Query(50, ge=1, le=100),
    ):
        filters: list[str] = []
        params: list[Any] = []
        if symbol:
            params.append(normalize_symbol(symbol))
            filters.append(f"o.symbol = ${len(params)}")
        if status.lower() != "all":
            filters.append(status_filter(status, params))
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        async with pool().acquire() as conn:
            rows = await conn.fetch(f"{SELECT} {where} ORDER BY o.snapshot_ts DESC LIMIT ${len(params)}", *params)
            paused = await entries_paused(conn)
        now_s, enabled = time.time(), execution_enabled()
        return {
            "schema_version": "opportunity_briefs_v1",
            "read_at_s": now_s,
            "status": status,
            "briefs": [compact(build_brief(**parts(row), entries_paused=paused, execution_enabled=enabled, now_s=now_s))
                       for row in rows],
            "authority": "paper_only",
            "note": LIST_NOTE,
        }

    @router.get("/state/opportunity-briefs/{opportunity_id}")
    async def one_brief(opportunity_id: str):
        try:
            key = uuid.UUID(opportunity_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="opportunity_id must be a UUID") from None
        async with pool().acquire() as conn:
            row = await conn.fetchrow(f"{SELECT} WHERE o.id = $1", key)
            paused = await entries_paused(conn) if row is not None else None
        if row is None:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        return build_brief(**parts(row), entries_paused=paused, execution_enabled=execution_enabled(), now_s=time.time())

    app.include_router(router)
