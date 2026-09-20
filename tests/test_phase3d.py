"""
Phase 3D Tests: Shared library + replay engine.

Tests:
- tradesync_core imports
- normalize_symbol correctness

The scorer, the risk guardian and calculate_score are tested in
test_phase3d_scoring.py, and the replay engine against the sample dataset in
test_phase3d_scoring_replay.py.
"""

import sys
from pathlib import Path

# Ensure libs/ is importable for local testing
sys.path.insert(0, str(Path(__file__).parent.parent / "libs" / "tradesync_core"))


class TestTradesyncCoreImports:
    """Verify all public API symbols are importable."""

    def test_import_top_level(self):
        from tradesync_core import (
            EnhancedScorer,
            compute_enhanced_score,
            RiskGuardian,
            ReasonCode,
            RiskVerdict,
            normalize_symbol,
            normalize_venue,
            Event,
            calculate_score,
            ScoreBreakdown,
            ExecutionRisk,
            EnhancedScore,
        )
        # All should be non-None
        assert EnhancedScorer is not None
        assert compute_enhanced_score is not None
        assert RiskGuardian is not None
        assert ReasonCode is not None
        assert RiskVerdict is not None
        assert normalize_symbol is not None
        assert normalize_venue is not None
        assert Event is not None
        assert calculate_score is not None
        assert ScoreBreakdown is not None
        assert ExecutionRisk is not None
        assert EnhancedScore is not None

    def test_version(self):
        import tradesync_core
        assert tradesync_core.__version__ == "0.1.0"

    def test_all_exports(self):
        """Every advertised export must resolve.

        A hard-coded count made this fail whenever the library gained a
        module, which says nothing about whether the exports work.
        """
        import tradesync_core
        assert len(tradesync_core.__all__) == len(set(tradesync_core.__all__))
        for name in tradesync_core.__all__:
            assert hasattr(tradesync_core, name), f"{name} is exported but missing"
        for required in ("EnhancedScorer", "RiskGuardian", "normalize_symbol",
                         "calculate_score", "decide_paper_signal"):
            assert required in tradesync_core.__all__


class TestNormalizeSymbol:
    def test_btcusdt(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("BTCUSDT") == "BTC-PERP"

    def test_btc_usdt_slash(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("BTC/USDT") == "BTC-PERP"

    def test_btc_perp_passthrough(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("BTC-PERP") == "BTC-PERP"

    def test_lowercase(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("btc-perp") == "BTC-PERP"

    def test_bare_symbol(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("ETH") == "ETH-PERP"

    def test_usdc_suffix(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("SOLUSDC") == "SOL-PERP"

    def test_empty_string(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol("") == ""

    def test_none_returns_none(self):
        from tradesync_core import normalize_symbol
        assert normalize_symbol(None) is None


class TestNormalizeVenue:
    def test_hl_to_hyperliquid(self):
        from tradesync_core import normalize_venue
        assert normalize_venue("hl") == "hyperliquid"

    def test_hyperliquid_passthrough(self):
        from tradesync_core import normalize_venue
        assert normalize_venue("hyperliquid") == "hyperliquid"

    def test_empty(self):
        from tradesync_core import normalize_venue
        assert normalize_venue("") == ""
