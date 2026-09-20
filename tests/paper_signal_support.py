"""Fixed evidence for the paper signal decision, shared by its tests.

Moved out of test_paper_signal.py unchanged, so the admission, evidence and
hysteresis tests, and the opportunity brief tests, all decide from the same
fixtures.
"""

from tradesync_core.paper_signal import decide_paper_signal

CATALOG = {
    "catalog_id": "tradesync-hyperliquid-market-features",
    "version": "1.2.0",
    "digest": "catalogdigest",
}

NOW_MS = 1_767_297_600_000


def _evaluation(score=0.42, coverage=0.55, risk=0.5, missing=None):
    return {
        "rulebook_id": "tradesync-intraday-regime",
        "rulebook_version": "1.0.0",
        "config_digest": "rulebookdigest",
        "weighted_score": score,
        "data_coverage": coverage,
        "paper_risk_multiplier": risk,
        "contributions": {"liquidity": {"weight": 0.25}},
        "missing_blocks": missing if missing is not None else ["macro_flows"],
        "risk_caps_applied": [{"flag": "low_data_coverage", "cap": 0.5, "known": True}],
        "calculation": "sum(weight * quality * score) / sum(weight * quality)",
    }


def _feature(
    feature_id="hl_return_1h_pct",
    block="price_volatility",
    provenance="derived",
    observed_at_ms=NOW_MS - 1_000,
    scoring_allowed=True,
    score=0.4,
):
    return {
        "feature_id": feature_id,
        "block": block,
        "provenance": provenance,
        "observed_at_ms": observed_at_ms,
        "scoring_allowed": scoring_allowed,
        "score": score,
        "data_quality": 0.9,
        "history_count": 168,
    }


def _directional(score=0.42, coverage=1.0):
    """Directional evidence, as aggregate_directional_evidence returns it."""
    return {
        "score": score,
        "coverage": coverage,
        "contributors": [
            {"feature_id": "hl_return_1h_pct", "score": score, "quality": coverage}
        ],
        "admitted_feature_ids": ["hl_return_1h_pct"],
        "ready_feature_ids": ["hl_return_1h_pct"],
    }


def _decide(evaluation=None, features=None, policy=None, now=NOW_MS, directional=-1,
            previous=None):
    return decide_paper_signal(
        symbol="BTC-PERP",
        evaluation=evaluation or _evaluation(),
        feature_results=features if features is not None else [_feature()],
        catalog_summary=CATALOG,
        evaluated_at_ms=now,
        policy=policy,
        directional=_directional() if directional == -1 else directional,
        previous_direction=previous,
    )
