"""The declared entry-evidence comparisons, measured on the calls that have outcomes.

``GET /state/research/entry-evidence-comparison``

The frozen source comparison reads one thing: the Hyperliquid book-history sample
kept beside each managed paper entry. Everything else an entry freezes -- resting
liquidity, liquidations received, open-interest change, funding, the timeframe
measurement -- was captured and never measured against what happened next.

This measures them, under the family declared in
``tradesync_core.entry_evidence_family`` before any of it was run. There are no
managed paper positions yet, so the population is the recorded opportunities
whose evidence can be reconstructed as of their own entry
(``app/entry_evidence_rows``), and the response says exactly which readings that
leaves available and which it does not.

Served from the statistics cache: the block bootstrap over every cell is pure
Python and runs in a worker thread, so no request waits on it. Read-only, shadow
only: three SELECTs, no write path, no weight, no promotion.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, HTTPException, Response

from app import entry_evidence_rows as rows_source
from app import heavy_query, learning_job, statistics_cache
from app.skill_gate import COSTS
from app.statistics_cache import StatisticsCache
from tradesync_core.ablation_evidence import SCHEMA_VERSION, Case, assess_family
from tradesync_core.outcomes import DEFAULT_HORIZONS_MINUTES

router = APIRouter(tags=["research"])

# The bootstrap is seeded, so the same sample always reports the same error.
DRAWS = 400
SEED = 0


def build_response(outcome_rows: Sequence[Mapping[str, Any]], context_rows: Sequence[Mapping[str, Any]],
                   history: Mapping[str, Any], positions: int, *, days: int) -> dict[str, Any]:
    """CPU-bound and free of I/O; runs in a worker thread."""
    sides = {str(row["opportunity_id"]): rows_source.SIDES[row["direction"]] for row in outcome_rows
             if row["direction"] in rows_source.SIDES}
    readings = rows_source.readings(context_rows, sides)
    cases = [
        Case(
            key=f"{row['opportunity_id']}:{row['horizon_minutes']}",
            symbol=str(row["symbol"]),
            opened_at_s=int(row["opened_at"].timestamp()),
            horizon_minutes=int(row["horizon_minutes"]),
            signed_return_pct=float(row["signed_return_pct"]),
            context=readings.get(str(row["opportunity_id"]), {}),
        )
        for row in outcome_rows
        if row["direction"] in rows_source.SIDES
    ]
    report = assess_family(cases, costs=COSTS, horizons=DEFAULT_HORIZONS_MINUTES, draws=DRAWS, seed=SEED)
    return {
        **report,
        "population_source": {
            "population": "recorded opportunity outcomes, not managed paper positions",
            "why": (
                "No managed paper position has been opened, so no frozen entry-evidence document exists to read. "
                "These are the calls the scorer recorded, with the evidence reconstructed as of each one's own entry "
                "time from the history TradeSync had already recorded."
            ),
            "window_days": days,
            "opportunities": len(context_rows),
            "recorded_history_begins": {key: None if value is None else value.isoformat()
                                        for key, value in dict(history).items()},
            "coverage": rows_source.coverage(context_rows),
        },
        "managed_paper": {
            "positions": positions,
            "note": (
                "With positions open or closed, the same declared family reads their frozen documents directly "
                "(tradesync_core.entry_evidence_context.from_document), including the timeframe measurement, which "
                "cannot be reconstructed for a past opportunity."
            ),
        },
        "reads": heavy_query.status(),
    }


async def compute_entry_evidence_comparison(pool, _symbol: str | None = None) -> dict[str, Any]:
    days = learning_job.WINDOW_DAYS
    async with pool.acquire() as conn:
        history = await heavy_query.fetch(conn, "entry_evidence:history", rows_source.HISTORY_START_SQL)
        start = history[0]["books"] if history else None
        if start is None:
            return {
                "schema_version": SCHEMA_VERSION,
                "cells": [],
                "authority": "research_only",
                "promotion_allowed": False,
                "note": ("No market history has been recorded, so no opportunity has evidence to read as of its "
                         "entry. Nothing was measured; this is not a result."),
            }
        outcome_rows = await heavy_query.fetch(conn, "entry_evidence:outcomes", rows_source.OUTCOMES_SQL, start, days)
        context_rows = await heavy_query.fetch(conn, "entry_evidence:context", rows_source.CONTEXT_SQL, start, days)
        positions = await heavy_query.fetchval(conn, "entry_evidence:positions",
                                               "SELECT count(*) FROM managed_paper_positions")
    return await asyncio.to_thread(build_response, outcome_rows, context_rows, dict(history[0]),
                                   int(positions or 0), days=days)


CACHE = StatisticsCache(
    "entry_evidence_comparison",
    "The entry-evidence comparison",
    compute_entry_evidence_comparison,
    SCHEMA_VERSION,
)


def register(app, state) -> None:
    statistics_cache.register(CACHE, state)

    @router.get("/state/research/entry-evidence-comparison")
    async def entry_evidence_comparison(response: Response):
        """Served from the statistics cache: 200 with computed_at, or 202 while first measured."""
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        return CACHE.respond(state.pool, None, response)

    app.include_router(router)
