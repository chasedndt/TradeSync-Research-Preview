"""Thesis adherence, regime fit and paper-position economics, served from stored records.

All three are computed in ``tradesync_core`` and none re-reads a market.
This module supplies them with stored rows and nothing else:

- adherence reads each managed paper position's immutable ``initial_plan`` and
  its latest lifecycle state, so a plan cannot be judged against a rule it was
  never opened under;
- regime fit reads the entry-time regime already frozen per opportunity, and
  the rulebook carrying the digest frozen on that call. A rulebook under any
  other digest is refused by the library, so a rulebook edited later cannot
  restate an earlier verdict;
- paper economics reads each managed paper position's lifecycle state over a
  window: excursions, fees, funding, modelled slippage and realised P&L per
  position, and expectancy across the closed ones (``paper_economics``).

Every read covers a table over a window or a cap and goes through ``heavy_query``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app import heavy_query
from app.json_util import as_json
from tradesync_core import paper_economics, regime_fit, thesis_adherence

router = APIRouter(tags=["outcomes"])

DEFAULT_POSITION_LIMIT = 100
DEFAULT_WINDOW_HOURS = 168
MAX_WINDOW_HOURS = 720
# Paper economics follows the audit export's day windows, so the Outcomes tab reads both over one window.
DEFAULT_ECONOMICS_DAYS = 7
MAX_ECONOMICS_DAYS = 31
MAX_ECONOMICS_POSITIONS = 500

# Positions opened, observed, closed or settled within the window: a close or a late funding settlement
# writes the row, so a position closed inside the window is in it wherever it was opened. One past the cap.
ECONOMICS_SQL = """
SELECT id::text AS id, opportunity_id::text AS opportunity_id, symbol, created_at, updated_at, position_state
FROM managed_paper_positions
WHERE updated_at > now() - make_interval(days => $1)
ORDER BY created_at DESC
LIMIT $2
"""

POSITIONS_SQL = """
SELECT id::text AS id, symbol, created_at, updated_at, initial_plan, position_state
FROM managed_paper_positions
ORDER BY created_at DESC
LIMIT $1
"""

CALLS_SQL = """
SELECT o.id::text AS id, o.symbol, o.dir AS direction,
       extract(epoch FROM o.snapshot_ts)::float8 AS opened_at_s,
       o.snapshot_ts,
       r.regime AS entry_regime,
       o.confluence->'evidence'->>'rulebook_digest' AS rulebook_digest
FROM opportunities o
LEFT JOIN opportunity_entry_regimes r ON r.opportunity_id = o.id
WHERE o.snapshot_ts > now() - make_interval(hours => $1)
  AND o.dir IN ('LONG', 'SHORT')
ORDER BY o.snapshot_ts DESC
LIMIT $2
"""

RULEBOOKS_SQL = """
SELECT config_digest, config
FROM regime_rulebooks
WHERE config_digest = ANY($1::text[])
"""


def register(app, state) -> None:
    """Attach the thesis-adherence and regime-fit readings."""

    def pool():
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return state.pool

    @router.get("/state/outcomes/thesis-adherence")
    async def thesis_adherence_reading(
        limit: int = Query(DEFAULT_POSITION_LIMIT, ge=1, le=500),
    ):
        """Did each paper position follow the plan it was opened under?

        Scored from the stored plan and the lifecycle's own record. A check
        whose input was never recorded is absent and counted, never a zero, so
        a position that cannot be judged does not drag the mean down.
        """
        taken_at = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            rows = await heavy_query.fetch(conn, "metrics:thesis-adherence", POSITIONS_SQL, limit)

        positions: list[dict[str, Any]] = []
        for record in rows:
            row = dict(record)
            result = thesis_adherence.score(as_json(row["initial_plan"]) or {}, as_json(row["position_state"]) or {})
            positions.append({
                "position_id": row["id"],
                "symbol": row["symbol"],
                "opened_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
                **result,
            })

        return {
            "generated_at": taken_at.isoformat(),
            "positions_considered": len(positions),
            "limit": limit,
            "positions": positions,
            "summary": thesis_adherence.summarise(positions),
            "authority": "read_only",
        }

    @router.get("/state/outcomes/regime-fit")
    async def regime_fit_reading(
        hours: int = Query(DEFAULT_WINDOW_HOURS, ge=1, le=MAX_WINDOW_HOURS),
        limit: int = Query(500, ge=1, le=5000),
    ):
        """Did each call fire into the regime its own rulebook expected?

        The regime is the entry-time label from candles closed before the call.
        The expectation is read from the rulebook carrying the digest frozen on
        that call, so a later rulebook change cannot rewrite an earlier verdict.
        """
        taken_at = datetime.now(timezone.utc)
        window_from = taken_at - timedelta(hours=hours)

        async with pool().acquire() as conn:
            rows = await heavy_query.fetch(conn, "metrics:regime-fit", CALLS_SQL, hours, limit)
            digests = sorted({row["rulebook_digest"] for row in rows if row["rulebook_digest"]})
            books = await heavy_query.fetch(conn, "metrics:rulebooks", RULEBOOKS_SQL, digests) if digests else []

        stored = {
            book["config_digest"]: {"config": as_json(book["config"]), "config_digest": book["config_digest"]}
            for book in books
        }

        calls = []
        for record in rows:
            row = dict(record)
            verdict = regime_fit.judge(row, stored.get(row["rulebook_digest"]))
            calls.append({
                "opportunity_id": row["id"],
                "symbol": row["symbol"],
                "opened_at": row["snapshot_ts"].isoformat() if row.get("snapshot_ts") else None,
                **verdict,
            })

        return {
            "generated_at": taken_at.isoformat(),
            "window": {"hours": hours, "from": window_from.isoformat(), "to": taken_at.isoformat()},
            "calls_considered": len(calls),
            "rulebooks_held": len(stored),
            "calls": calls,
            "summary": regime_fit.summarise(calls),
            "authority": "read_only",
        }

    @router.get("/state/outcomes/paper-economics")
    async def paper_economics_reading(
        days: int = Query(DEFAULT_ECONOMICS_DAYS, ge=1, le=MAX_ECONOMICS_DAYS),
        limit: int = Query(DEFAULT_POSITION_LIMIT, ge=1, le=MAX_ECONOMICS_POSITIONS),
    ):
        """What each managed paper position cost and earned, and the expectancy of the closed ones.

        Read from each position's lifecycle state as stored. Expectancy is over the closed positions
        this reading holds, with its sample size, and is absent rather than zero when none closed.
        """
        taken_at = datetime.now(timezone.utc)
        async with pool().acquire() as conn:
            rows = await heavy_query.fetch(conn, "metrics:paper-economics", ECONOMICS_SQL, days, limit + 1)

        positions = []
        for record in rows[:limit]:
            row = dict(record)
            positions.append(paper_economics.position(
                row["id"], row["symbol"], as_json(row["position_state"]) or {}, opportunity_id=row["opportunity_id"],
                opened_at=row["created_at"].isoformat() if row.get("created_at") else None,
                updated_at=row["updated_at"].isoformat() if row.get("updated_at") else None,
            ))
        return {
            "schema_version": paper_economics.SCHEMA_VERSION,
            "generated_at": taken_at.isoformat(),
            "window": {"days": days, "from": (taken_at - timedelta(days=days)).isoformat(), "to": taken_at.isoformat()},
            "positions": positions,
            "row_count": len(positions),
            "row_cap": limit,
            "truncated": len(rows) > limit,
            "expectancy": paper_economics.expectancy(positions),
            "authority": "read_only",
            "note": paper_economics.NOTE,
        }

    app.include_router(router)
