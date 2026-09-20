"""
Phase 3D Tests: scoring in the shared library.

Tests:
- EnhancedScorer initialization + scoring
- RiskGuardian initialization + basic check
- calculate_score with synthetic events
"""

import os
from datetime import datetime, timezone


class TestEnhancedScorer:
    def test_init(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        assert scorer.max_spread_bps == 50.0
        assert scorer.spread_penalty_weight == 0.5

    def test_basic_score(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        result = scorer.compute_enhanced_score(
            raw_score=5.0,
            signal_confidence=0.5,
            symbol="BTC-PERP",
        )
        assert result.score_breakdown.alpha == 5.0
        assert result.score_breakdown.final_score == 5.0
        assert result.score_breakdown.microstructure_penalty == 0.0
        assert len(result.warnings) == 0

    def test_with_microstructure(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        result = scorer.compute_enhanced_score(
            raw_score=5.0,
            signal_confidence=0.5,
            symbol="BTC-PERP",
            microstructure={
                "spread_bps": 100.0,  # Very wide spread
                "depth_usd": {"25bp": 50000},  # Below optimal
                "impact_est_bps": {"5000": 30.0},  # High impact
                "liquidity_score": 0.2,  # Below threshold
            },
        )
        assert result.score_breakdown.microstructure_penalty < 0
        assert result.score_breakdown.final_score < 5.0
        assert len(result.warnings) > 0
        assert "WIDE_SPREAD" in result.execution_risk.flags

    def test_to_dict(self):
        from tradesync_core import EnhancedScorer
        scorer = EnhancedScorer()
        result = scorer.compute_enhanced_score(
            raw_score=3.0, signal_confidence=0.3, symbol="ETH-PERP"
        )
        d = result.to_dict()
        assert "score_breakdown" in d
        assert "execution_risk" in d
        assert "warnings" in d


class TestRiskGuardian:
    def setup_method(self):
        os.environ["EXECUTION_ENABLED"] = "true"
        os.environ["MIN_QUALITY"] = "50.0"

    def test_init(self):
        from tradesync_core import RiskGuardian
        guardian = RiskGuardian()
        assert guardian.execution_enabled is True
        assert guardian.max_leverage == 5.0

    def test_pass(self):
        from tradesync_core import RiskGuardian, ReasonCode
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="BTC-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 80.0},
        )
        assert verdict.allowed is True
        assert verdict.reason_code == ReasonCode.OK

    def test_dnt_block(self):
        from tradesync_core import RiskGuardian, ReasonCode
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="LUNA-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 80.0},
        )
        assert verdict.allowed is False
        assert verdict.reason_code == ReasonCode.DNT

    def test_quality_block(self):
        from tradesync_core import RiskGuardian, ReasonCode
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="BTC-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 10.0},
        )
        assert verdict.allowed is False
        assert verdict.reason_code == ReasonCode.MIN_QUALITY

    def test_exec_disabled(self):
        from tradesync_core import RiskGuardian, ReasonCode
        os.environ["EXECUTION_ENABLED"] = "false"
        guardian = RiskGuardian()
        verdict = guardian.check(
            symbol="BTC-PERP",
            size_usd=1000.0,
            opportunity={"status": "new", "quality": 80.0},
        )
        assert verdict.allowed is False
        assert verdict.reason_code == ReasonCode.EXEC_DISABLED


class TestCalculateScore:
    def test_empty_events(self):
        from tradesync_core import calculate_score
        assert calculate_score([]) == 0.0

    def test_long_bias(self):
        from tradesync_core import calculate_score, Event
        events = [
            Event(ts=datetime(2025, 1, 1, tzinfo=timezone.utc), source="tradingview", kind="alert", payload={"bias": "LONG"}),
        ]
        score = calculate_score(events)
        assert score == 1.0

    def test_short_bias(self):
        from tradesync_core import calculate_score, Event
        events = [
            Event(ts=datetime(2025, 1, 1, tzinfo=timezone.utc), source="tradingview", kind="alert", payload={"bias": "SHORT"}),
        ]
        score = calculate_score(events)
        assert score == -1.0

    def test_squeeze_logic_long(self):
        """Negative funding + rising OI = short squeeze = LONG bias."""
        from tradesync_core import calculate_score, Event
        events = [
            Event(
                ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": -0.0005, "oi": 1000000},
            ),
            Event(
                ts=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": -0.0005, "oi": 1020000},
            ),
        ]
        score = calculate_score(events)
        # Should be: squeeze +2.0 + base funding +0.5 = 2.5
        assert score == 2.5

    def test_squeeze_logic_short(self):
        """Positive funding + rising OI = long squeeze = SHORT bias."""
        from tradesync_core import calculate_score, Event
        events = [
            Event(
                ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": 0.0005, "oi": 500000},
            ),
            Event(
                ts=datetime(2025, 1, 1, 10, 5, tzinfo=timezone.utc),
                source="metrics", kind="market_snapshot",
                payload={"funding": 0.0005, "oi": 510000},
            ),
        ]
        score = calculate_score(events)
        # Should be: squeeze -2.0 + base funding -0.5 = -2.5
        assert score == -2.5

    def test_clamp(self):
        from tradesync_core import calculate_score, Event
        # Many LONG signals to exceed 10
        events = [
            Event(ts=datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc), source="tradingview", kind="alert", payload={"bias": "LONG"})
            for i in range(15)
        ]
        score = calculate_score(events)
        assert score == 10.0
