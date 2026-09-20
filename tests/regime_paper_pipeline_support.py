"""Service modules and fixed evidence for the regime-backed paper path tests.

Moved out of test_regime_paper_pipeline.py unchanged.

Every service package in this repository is named ``app``, so importing one by
that name would shadow the others for the rest of the test session. Each is
loaded here under a private name instead: ``paper_producer`` by file path, and
the fusion worker through a package alias so its relative imports still
resolve.
"""

import importlib
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))

from tradesync_core.paper_signal import decide_paper_signal  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


producer = _load_module(
    "core_scorer_paper_producer",
    ROOT / "services" / "core-scorer" / "app" / "paper_producer.py",
)

FUSION_PACKAGE = "fusion_engine_app"


def _load_fusion_worker():
    """Import the fusion worker without claiming the global ``app`` name."""
    package = types.ModuleType(FUSION_PACKAGE)
    package.__path__ = [str(ROOT / "services" / "fusion-engine" / "app")]
    sys.modules.setdefault(FUSION_PACKAGE, package)
    return importlib.import_module(f"{FUSION_PACKAGE}.worker")

NOW_MS = 1_767_297_600_000
CATALOG = {
    "catalog_id": "tradesync-hyperliquid-market-features",
    "version": "1.2.0",
    "digest": "catalogdigest",
}


def _decision(score=0.42, coverage=0.55, risk=0.5, allowed=True):
    evaluation = {
        "rulebook_id": "tradesync-intraday-regime",
        "rulebook_version": "1.0.0",
        "config_digest": "rulebookdigest",
        "weighted_score": score,
        "data_coverage": coverage,
        "paper_risk_multiplier": risk,
        "contributions": {},
        "missing_blocks": [],
        "risk_caps_applied": [],
        "calculation": "sum(weight * quality * score) / sum(weight * quality)",
    }
    features = [
        {
            "feature_id": "hl_return_1h_pct",
            "block": "price_volatility",
            "provenance": "derived",
            "observed_at_ms": NOW_MS - 1_000,
            "scoring_allowed": allowed,
            "score": score,
            "data_quality": 0.9,
            "history_count": 168,
        }
    ]
    return decide_paper_signal(
        symbol="BTC-PERP",
        evaluation=evaluation,
        feature_results=features,
        catalog_summary=CATALOG,
        evaluated_at_ms=NOW_MS,
        directional={
            "score": score,
            "coverage": 1.0,
            "contributors": [
                {"feature_id": "hl_return_1h_pct", "score": score, "quality": 1.0}
            ],
            "admitted_feature_ids": ["hl_return_1h_pct"],
            "ready_feature_ids": ["hl_return_1h_pct"],
        },
    )


class RecordingRedis:
    def __init__(self):
        self.published = []

    async def xadd(self, stream, fields):
        self.published.append((stream, fields))
