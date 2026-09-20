"""What happened after each recorded call: outcomes by regime, the evidence timeline, the summary, and refusals.

Moved out of ``app/main.py`` unchanged. Everything here describes a sample that
was observed, never a probability about the next call, and no order was ever
placed. Two measurement rules are load-bearing and stay with the code that
applies them: regimes are scored separately because pooling them is misleading,
and the error is adjusted for overlap because a verdict a minute over a
240-minute horizon is very nearly the same trade counted many times.
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.evidence_timeline_routes import register as register_timeline
from tradesync_core import normalize_symbol

router = APIRouter()


def register(app, state) -> None:
    """Attach the outcome, evidence-timeline and refusal-history routes."""

    @router.get("/state/outcomes/by-regime", tags=["outcomes"])
    async def get_outcomes_by_regime(horizon_minutes: int = 60, symbol: Optional[str] = None):
        """Skill measured separately in rising and falling markets.

        Pooling regimes is actively misleading. A caller with a fixed directional
        bias, measured across windows with very different base rates, shows an
        apparent effect that vanishes once each regime is scored against its own
        baseline. On 2026-09-08 the pooled figure read -10.2 points (-2.4 SE) while
        the same data split by regime read -2.9 and -5.6 points, both inside one
        standard error.

        Regime is assigned from the hour's own aggregate move, not from the
        individual outcome being scored.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if symbol:
            symbol = normalize_symbol(symbol)

        try:
            async with state.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    WITH hourly AS (
                      SELECT date_trunc('hour', opened_at) hr, avg(forward_return_pct) hr_move
                      FROM opportunity_outcomes
                      WHERE status = 'measured' AND horizon_minutes = $1
                        AND ($2::text IS NULL OR symbol = $2)
                      GROUP BY 1
                    ),
                    tagged AS (
                      SELECT o.*, CASE WHEN h.hr_move > 0 THEN 'rising' ELSE 'falling' END regime
                      FROM opportunity_outcomes o
                      JOIN hourly h ON h.hr = date_trunc('hour', o.opened_at)
                      WHERE o.status = 'measured' AND o.horizon_minutes = $1
                        AND ($2::text IS NULL OR o.symbol = $2)
                    )
                    SELECT regime, count(*) n,
                           count(*) FILTER (WHERE signed_return_pct > 0) wins,
                           count(*) FILTER (WHERE forward_return_pct > 0) ups,
                           count(*) FILTER (WHERE direction = 'LONG') longs,
                           avg(signed_return_pct) mean_signed,
                           count(DISTINCT symbol) symbols,
                           EXTRACT(EPOCH FROM (max(opened_at) - min(opened_at)))/60 span_minutes
                    FROM tagged GROUP BY regime ORDER BY regime
                    """,
                    horizon_minutes,
                    symbol,
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        regimes = []
        for r in rows:
            n = r["n"]
            if not n:
                continue
            hit = r["wins"] / n
            up = r["ups"] / n
            long_share = r["longs"] / n
            baseline = long_share * up + (1 - long_share) * (1 - up)
            skill = hit - baseline

            # Independent windows, not observations.
            #
            # A verdict is recorded every 60 seconds and a 240-minute horizon covers
            # 240 minutes of price. Two observations four minutes apart share 98% of
            # their window: they are very nearly the same trade counted twice.
            # Treating them as independent understates the error by the square root
            # of the overcounting, and that is exactly how a 74-observation sample
            # spanning 5.6 hours reported a "significant" result off roughly four
            # genuinely independent windows.
            #
            # The effective sample is how many non-overlapping windows of this
            # horizon fit in the span, times the number of symbols. Symbols are
            # counted as independent, which is generous — BTC, ETH and SOL move
            # together — so this remains a floor on the uncertainty rather than an
            # estimate of it.
            span_minutes = float(r["span_minutes"] or 0)
            symbols = int(r["symbols"] or 1)
            windows = span_minutes / horizon_minutes if horizon_minutes else 0
            effective_n = max(min(n, symbols * windows), 1.0)

            se = math.sqrt(0.25 / effective_n)
            naive_se = math.sqrt(0.25 / n)

            regimes.append({
                "regime": r["regime"],
                "measured": n,
                # What the sample is actually worth.
                "effective_observations": round(effective_n, 1),
                "independent_windows_per_symbol": round(windows, 1),
                "symbols": symbols,
                "span_minutes": round(span_minutes),
                "hit_rate": round(hit, 4),
                "market_up_rate": round(up, 4),
                "long_share": round(long_share, 4),
                "expected_hit_rate": round(baseline, 4),
                "skill_vs_baseline": round(skill, 4),
                "standard_error": round(se, 4),
                "naive_standard_error": round(naive_se, 4),
                "overlap_inflation": round(se / naive_se, 1) if naive_se else None,
                "skill_in_standard_errors": round(skill / se, 2) if se else None,
                # Judged against the overlap-adjusted error. The old flag said True
                # for a result its own note disclaimed in prose.
                "significant": abs(skill) > 2 * se,
                "mean_signed_return_pct": round(r["mean_signed"], 6) if r["mean_signed"] is not None else None,
            })

        return {
            "schema_version": "opportunity_outcome_v1",
            "horizon_minutes": horizon_minutes,
            "symbol": symbol,
            "regimes": regimes,
            "note": (
                "Regimes are scored separately because pooling them is misleading: "
                "a fixed directional bias across windows with different base rates "
                "produces an apparent effect that is an artefact of aggregation. "
                "standard_error is adjusted for overlap: a verdict every 60 "
                "seconds over a 240-minute horizon produces observations that are "
                "very nearly the same trade counted many times, so the sample is "
                "worth effective_observations, not measured. Symbols are treated "
                "as independent, which is generous, so this is still a floor on "
                "the uncertainty rather than an estimate of it."
            ),
        }

    @router.get("/state/outcomes/summary", tags=["outcomes"])
    async def get_outcome_summary(symbol: Optional[str] = None):
        """Measured track record of recorded paper opportunities.

        Describes what the market did after each call. It is a record of this
        sample, not a probability that the next call wins, and no order was ever
        placed.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")
        if symbol:
            symbol = normalize_symbol(symbol)

        try:
            async with state.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT horizon_minutes,
                           count(*) FILTER (WHERE status = 'measured') AS measured,
                           count(*) FILTER (WHERE status = 'pending') AS pending,
                           count(*) FILTER (WHERE status = 'insufficient_candles') AS unmeasurable,
                           avg(signed_return_pct) FILTER (WHERE status = 'measured') AS mean_signed,
                           avg(max_favourable_pct) FILTER (WHERE status = 'measured') AS mean_favourable,
                           avg(max_adverse_pct) FILTER (WHERE status = 'measured') AS mean_adverse,
                           count(*) FILTER (WHERE status = 'measured' AND signed_return_pct > 0) AS wins,
                           -- The market's own behaviour over exactly these windows.
                           count(*) FILTER (WHERE status = 'measured' AND forward_return_pct > 0) AS market_up,
                           count(*) FILTER (WHERE status = 'measured' AND direction = 'LONG') AS longs,
                           avg(forward_return_pct) FILTER (WHERE status = 'measured') AS mean_market_move
                    FROM opportunity_outcomes
                    WHERE ($1::text IS NULL OR symbol = $1)
                    GROUP BY horizon_minutes
                    ORDER BY horizon_minutes
                    """,
                    symbol,
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        horizons = []
        for r in rows:
            measured = r["measured"] or 0
            hit_rate = r["wins"] / measured if measured else None
            up_rate = r["market_up"] / measured if measured else None
            long_share = r["longs"] / measured if measured else None
            # What this direction mix scores by luck alone, given how the market
            # actually moved. Without it, a one-regime sample reports the trend as
            # if it were ability.
            baseline = (
                long_share * up_rate + (1 - long_share) * (1 - up_rate)
                if measured
                else None
            )
            horizons.append({
                "horizon_minutes": r["horizon_minutes"],
                "measured": measured,
                "pending": r["pending"] or 0,
                "unmeasurable": r["unmeasurable"] or 0,
                # None rather than 0 when nothing is measured: an empty sample has
                # no hit rate, and 0% would read as "always wrong".
                "hit_rate": round(hit_rate, 4) if measured else None,
                "market_up_rate": round(up_rate, 4) if measured else None,
                "long_share": round(long_share, 4) if measured else None,
                "expected_hit_rate": round(baseline, 4) if measured else None,
                "skill_vs_baseline": round(hit_rate - baseline, 4) if measured else None,
                "mean_signed_return_pct": round(r["mean_signed"], 6) if r["mean_signed"] is not None else None,
                "mean_market_move_pct": round(r["mean_market_move"], 6) if r["mean_market_move"] is not None else None,
                "mean_favourable_pct": round(r["mean_favourable"], 6) if r["mean_favourable"] is not None else None,
                "mean_adverse_pct": round(r["mean_adverse"], 6) if r["mean_adverse"] is not None else None,
            })

        return {
            "schema_version": "opportunity_outcome_v1",
            "symbol": symbol,
            "horizons": horizons,
            "note": (
                "hit_rate is not interpretable alone: compare it with "
                "expected_hit_rate, what this direction mix scores by luck given "
                "how the market moved. A single-regime sample cannot demonstrate "
                "skill. No order was placed."
            ),
        }

    app.include_router(router)

    # The evidence timeline and refusal history, registered from here so main.py is unchanged.
    register_timeline(app, state)
