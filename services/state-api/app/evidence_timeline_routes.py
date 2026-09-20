"""The evidence timeline and refusal history: one paper call reconstructed, and the refusals counted.

Moved out of ``app/outcome_routes.py`` unchanged, and registered from its
``register`` so ``app/main.py`` needed no edit. The timeline is the Phase 4 exit
gate in endpoint form: a paper trade reconstructed from the evidence that
produced it through what the market did next, without screenshots or memory.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from tradesync_core import normalize_symbol

router = APIRouter()


def register(app, state) -> None:
    """Attach the evidence-timeline and refusal-history routes."""

    @router.get("/state/evidence/timeline", tags=["evidence"])
    async def evidence_timeline(symbol: str, limit: int = Query(25, le=100)):
        """One row per paper opportunity, from observation through to outcome.

        This is the Phase 4 exit gate in endpoint form: everything needed to
        reconstruct a paper trade without screenshots or memory. Each entry carries
        the evidence that produced it, the configuration digests it was produced
        under, and what the market subsequently did.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        resolved = normalize_symbol(symbol)

        try:
            async with state.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT o.id, o.symbol, o.dir, o.bias, o.quality, o.snapshot_ts,
                           o.links, o.confluence,
                           s.id AS signal_id, s.created_at AS signal_at,
                           coalesce(
                             json_agg(
                               json_build_object(
                                 'horizon_minutes', x.horizon_minutes,
                                 'status', x.status,
                                 'signed_return_pct', x.signed_return_pct,
                                 'forward_return_pct', x.forward_return_pct,
                                 'max_favourable_pct', x.max_favourable_pct,
                                 'max_adverse_pct', x.max_adverse_pct
                               ) ORDER BY x.horizon_minutes
                             ) FILTER (WHERE x.id IS NOT NULL), '[]'
                           ) AS outcomes
                    FROM opportunities o
                    LEFT JOIN signals s ON s.id = o.signal_id
                    LEFT JOIN opportunity_outcomes x ON x.opportunity_id = o.id
                    WHERE o.symbol = $1
                    GROUP BY o.id, s.id
                    ORDER BY o.snapshot_ts DESC
                    LIMIT $2
                    """,
                    resolved,
                    limit,
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        entries = []
        for r in rows:
            confluence = r["confluence"]
            if isinstance(confluence, str):
                confluence = json.loads(confluence)
            confluence = confluence or {}
            links = r["links"]
            if isinstance(links, str):
                links = json.loads(links)
            evidence = confluence.get("evidence") or {}
            outcomes = r["outcomes"]
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)

            entries.append({
                "opportunity_id": str(r["id"]),
                "signal_id": str(r["signal_id"]) if r["signal_id"] else None,
                "symbol": r["symbol"],
                "direction": r["dir"],
                "directional_score": r["bias"],
                "coverage_pct": r["quality"],
                "opened_at": r["snapshot_ts"].isoformat(),
                "signal_at": r["signal_at"].isoformat() if r["signal_at"] else None,
                # The configuration this decision was taken under, so a replay can
                # reproduce it exactly rather than approximately.
                "catalog_version": evidence.get("catalog_version"),
                "catalog_digest": evidence.get("catalog_digest"),
                "rulebook_version": evidence.get("rulebook_version"),
                "rulebook_digest": evidence.get("rulebook_digest"),
                "evidence_digest": (links or {}).get("evidence_digest"),
                "contributing_features": confluence.get("contributing_features") or [],
                "missing_blocks": evidence.get("missing_blocks") or [],
                "paper_risk_multiplier": confluence.get("paper_risk_multiplier"),
                "outcomes": outcomes or [],
            })

        return {
            "schema_version": "evidence_timeline_v1",
            "symbol": resolved,
            "entries": entries,
            "note": (
                "Each entry reconstructs one paper opportunity from the evidence "
                "that produced it to what the market did next. No order was placed "
                "and no position existed."
            ),
        }

    @router.get("/state/signals/refusal-history")
    async def get_refusal_history(
        days: int = Query(30, ge=1, le=365),
        symbol: Optional[str] = None,
    ):
        """Daily refusal counts by reason, from the permanent aggregate.

        Full refusal rows are kept for a recent window only — roughly 4,300 a day of
        evidence JSON is not a store worth growing forever, and nobody reconstructs
        an individual refusal from three weeks ago. What does keep mattering is the
        denominator: "the coverage floor blocked 61% of ETH verdicts last Tuesday"
        is only answerable if the refusals are counted somewhere after the rows are
        gone.

        ``reason`` is the primary code — the first gate the evidence failed — so the
        counts sum to the exact number of refusals. ``reason_codes`` additionally
        tallies every code seen, including secondary ones, and those may sum higher.
        """
        if state.pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        clauses = ["day >= (current_date - $1::int)"]
        args: list = [days]
        if symbol:
            args.append(normalize_symbol(symbol))
            clauses.append(f"symbol = ${len(args)}")

        async with state.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT day, symbol, reason, refusals, reason_codes,
                       scored_rows, covered_rows,
                       mean_score, mean_coverage, min_coverage, max_coverage,
                       first_rolled_at, last_rolled_at
                FROM signal_refusal_daily
                WHERE {' AND '.join(clauses)}
                ORDER BY day DESC, symbol, refusals DESC
                """,
                *args,
            )

        entries = []
        for row in rows:
            entry = dict(row)
            entry["day"] = entry["day"].isoformat()
            codes = entry.get("reason_codes")
            entry["reason_codes"] = json.loads(codes) if isinstance(codes, str) else codes
            entry["first_rolled_at"] = entry["first_rolled_at"].isoformat()
            entry["last_rolled_at"] = entry["last_rolled_at"].isoformat()
            entries.append(entry)

        return {
            "days": days,
            "symbol": symbol,
            "entries": entries,
            "total_refusals": sum(int(e["refusals"]) for e in entries),
            "note": (
                "Summarised from full refusal rows before they were removed. "
                "Recent days may still have their full rows in /state/signals."
            ),
        }

    app.include_router(router)
