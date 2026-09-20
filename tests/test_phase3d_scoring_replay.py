"""
Phase 3D Tests: the replay engine against the sample dataset (in-process, no Docker).
"""

import os
import sys
import json
from pathlib import Path

# Loaded under a private alias rather than by inserting the service directory:
# every service packages its code as "app", so only one could own that name.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _service_import import load_service_package  # noqa: E402

load_service_package("backtest_runner_app", "backtest-runner")


class TestReplayEngine:
    """Test replay engine against sample dataset (in-process, no Docker)."""

    def setup_method(self):
        os.environ["EXECUTION_ENABLED"] = "true"
        os.environ["MIN_QUALITY"] = "1.0"  # Low threshold for sample data

    def test_sample_dataset(self):
        from backtest_runner_app.replay import ReplayEngine

        dataset_path = Path(__file__).parent.parent / "data" / "replay" / "sample"
        engine = ReplayEngine(dataset_path=dataset_path)
        results = engine.run()

        # Should have processed events
        assert results.events_processed == 7

        # Should have 2 symbols
        assert len(results.symbols_processed) == 2
        assert "BTC-PERP" in results.symbols_processed
        assert "ETH-PERP" in results.symbols_processed

        # Should have signals for each symbol
        assert len(results.signals) == 2

        # BTC should be LONG (tradingview LONG + negative funding squeeze)
        btc_signal = next(s for s in results.signals if s.symbol == "BTC-PERP")
        assert btc_signal.direction == "LONG"
        assert btc_signal.score > 0

        # ETH should be SHORT (tradingview SHORT + positive funding squeeze)
        eth_signal = next(s for s in results.signals if s.symbol == "ETH-PERP")
        assert eth_signal.direction == "SHORT"
        assert eth_signal.score < 0

        # Should have risk verdicts
        assert len(results.risk_verdicts) == 2

    def test_empty_dataset(self, tmp_path):
        from backtest_runner_app.replay import ReplayEngine

        # Create empty events file
        events_file = tmp_path / "events.jsonl"
        events_file.write_text("")

        engine = ReplayEngine(dataset_path=tmp_path)
        results = engine.run()

        assert results.events_processed == 0
        assert len(results.signals) == 0

    def test_evaluator(self, tmp_path):
        from backtest_runner_app.replay import ReplayEngine
        from backtest_runner_app.evaluator import generate_report

        dataset_path = Path(__file__).parent.parent / "data" / "replay" / "sample"
        engine = ReplayEngine(dataset_path=dataset_path)
        results = engine.run()

        output_dir = tmp_path / "reports"
        output_dir.mkdir()

        generate_report(results, {"name": "test"}, output_dir)

        assert (output_dir / "report.json").exists()
        assert (output_dir / "report.md").exists()

        # Validate JSON report structure
        with open(output_dir / "report.json") as f:
            report = json.load(f)

        assert "summary" in report
        assert "results" in report
        assert report["summary"]["events_processed"] == 7
        assert report["summary"]["signals"]["total"] == 2

        # Validate Markdown report
        md_content = (output_dir / "report.md").read_text()
        assert "TradeSync Backtest Report" in md_content
        assert "Signal Distribution" in md_content
        assert "Risk Verdict Breakdown" in md_content
