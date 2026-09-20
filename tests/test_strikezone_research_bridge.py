from __future__ import annotations

import json
import os

from tools import strikezone_quant_bridge as bridge


def test_latest_research_evidence_selects_latest_complete_run_and_preserves_gates(tmp_path, monkeypatch):
    older = tmp_path / "older"
    latest = tmp_path / "2026-09-19-tradesync-v2-completion"
    incomplete = tmp_path / "newer-but-incomplete"
    for path in (older, latest, incomplete):
        path.mkdir()

    manifest = {
        "run_date": "2026-09-19",
        "public_ready": True,
        "required_assets": ["BTC", "ETH", "SOL"],
        "required_chart_timeframes": ["D", "8H", "4H", "1H", "15M"],
        "required_source_classes": ["x_social", "perplexity_digest", "grok_digest"],
        "asset_gates": {
            asset: {"chart_paths": {frame: f"{asset}_{frame}.png" for frame in ("D", "8H", "4H", "1H", "15M")}}
            for asset in ("BTC", "ETH", "SOL")
        },
        "reviewer_gate": {
            "status": "public_ready_degraded_sources",
            "missing_required_sources": ["x_social", "perplexity_digest"],
            "source_tolerance": {"allowed_missing_count": 2, "missing_count": 2, "degraded": True, "over_limit": False},
            "operator_approval_required": True,
            "trade_execution_allowed": False,
        },
        "evidence_items": [
            {"source_class": "grok_digest"},
            {"source_class": "youtube_transcript"},
            {"source_class": "youtube_transcript"},
        ],
    }
    validation = {
        "run_slug": latest.name,
        "ok": False,
        "missing": ["perplexity_latest_markdown_detail_gate", "draft_files"],
        "external_delivery_performed": False,
    }
    (latest / "evidence_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (latest / "pipeline_validation_report.json").write_text(json.dumps(validation), encoding="utf-8")
    (older / "evidence_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (older / "pipeline_validation_report.json").write_text(json.dumps({**validation, "run_slug": "older"}), encoding="utf-8")
    (incomplete / "evidence_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name in ("evidence_manifest.json", "pipeline_validation_report.json"):
        os.utime(older / name, (1, 1))
        os.utime(latest / name, (2, 2))
    os.utime(incomplete / "evidence_manifest.json", (3, 3))

    monkeypatch.setattr(bridge, "CHASEOS_STRIKEZONE_RUNS_ROOT", tmp_path)
    result = bridge.latest_research_evidence()

    assert result is not None
    payload, _ = result
    assert payload["run_slug"] == latest.name
    assert payload["evidence_item_count"] == 3
    assert payload["charts_captured"] == payload["charts_expected"] == 15
    assert payload["source_counts"] == {"grok_digest": 1, "youtube_transcript": 2}
    assert payload["missing_source_classes"] == ["x_social", "perplexity_digest"]
    assert payload["validation_ok"] is False
    assert payload["trade_execution_allowed"] is False
