"""Opportunities that can open a managed paper position now: every tracked symbol, directional, fresh.

The universe is what market-data reports it tracks (``editions.tracked_symbols``);
the rule is ``tradesync_core.paper_eligibility``, the same one entry admission
applies. An unreadable universe offers nothing.
"""

from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import HTTPException, Query

from app import editions
from app.opportunity_lifecycle import EFFECTIVE_STATUS_SQL, EXPIRES_AT_SQL
from tradesync_core import paper_eligibility as eligibility
from tradesync_core.paper_lifecycle_rules import COMMON
from tradesync_core.paper_lifecycle_rules import RULES
from tradesync_core.paper_style_alignment import STYLE_HORIZONS, assess_style_alignment

LIMIT = 200


async def style_alignment(state_api_url: str, symbol: str, style: str, direction: str, now: float) -> dict:
    try:
        async with httpx.AsyncClient(timeout=25, trust_env=False) as client:
            response = await client.get(f"{state_api_url}/state/market/horizons/decision",
                                        params={"symbol": symbol, "horizon": STYLE_HORIZONS[style]})
            response.raise_for_status()
            page = response.json()
    except Exception as exc:
        return {
            "policy": "paper-style-alignment-v1", "style": style, "horizon": None,
            "direction": direction, "eligible": False,
            "reasons": [f"timeframe measurement unavailable: {type(exc).__name__}"],
            "checks": [], "meaning": "Style/horizon admission gate; not a forecast or proof of edge.",
        }
    return assess_style_alignment(page, style=style, direction=direction,
                                  minimum_move_pct=RULES[style].min_target_pct, now_s=now)


def register(app, pool, *, market_data_url: str, state_api_url: str) -> None:
    @app.get("/state/paper-positions/candidates")
    async def candidates(style: str = Query("intraday", pattern="^(scalp|intraday|swing)$")):
        universe = await editions.tracked_symbols(market_data_url)
        if not universe:
            raise HTTPException(503, "Tracked symbol universe unavailable; no paper entry can be offered")
        async with pool().acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT o.id, o.symbol, o.timeframe, o.dir, o.bias, o.quality, o.snapshot_ts, {EXPIRES_AT_SQL} AS expires_at,
                           p.id AS position_id
                    FROM opportunities o LEFT JOIN managed_paper_positions p ON p.opportunity_id = o.id
                    WHERE o.snapshot_ts >= now() - make_interval(secs => $1) AND o.snapshot_ts <= now()
                      AND ({EFFECTIVE_STATUS_SQL}) = 'new'
                    ORDER BY o.snapshot_ts DESC LIMIT $2""",
                COMMON.max_opportunity_age_s, LIMIT)
        now = time.time()
        basic = [
            {"id": str(r["id"]), "symbol": r["symbol"], "timeframe": r["timeframe"], "dir": r["dir"],
             "direction": eligibility.direction(r), "bias": r["bias"], "quality": r["quality"],
             "snapshot_ts": r["snapshot_ts"].isoformat(), "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
             "age_s": eligibility.age_s(r, now), "position_id": str(r["position_id"]) if r["position_id"] else None}
            for r in rows
            if eligibility.opportunity_refusal(r, now) is None and eligibility.universe_refusal(r["symbol"], universe) is None
        ]
        alignments = await asyncio.gather(*[
            style_alignment(state_api_url, row["symbol"], style, row["direction"], now) for row in basic
        ])
        assessed = [{**row, "style_alignment": alignment} for row, alignment in zip(basic, alignments)]
        offered = [row for row in assessed if row["style_alignment"]["eligible"]]
        rejected = [{"id": row["id"], "symbol": row["symbol"], "dir": row["dir"],
                     "style_alignment": row["style_alignment"]} for row in assessed if not row["style_alignment"]["eligible"]]
        covered = {c["symbol"] for c in offered}
        return {"universe": universe, "max_age_s": COMMON.max_opportunity_age_s, "checked_at": now, "candidates": offered,
                "symbols_without_candidate": [s for s in universe if s not in covered], "rejected_candidates": rejected,
                "style": style, "style_policy": "paper-style-alignment-v1", "authority": "paper_only"}
