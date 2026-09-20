from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.integration_pipeline import assemble_pipeline_status
from app.main import app


client = TestClient(app)


def _probes():
    return {
        "market_health": {"ok": True, "data": {"ok": True}, "latency_ms": 8.0},
        "market_ready": {
            "ok": True,
            "data": {
                "ready": True,
                "reason": "",
                "symbols": [{"symbol": "BTC-PERP", "state": "fresh", "age_seconds": 2.0}],
            },
        },
        "market_status": {
            "ok": True,
            "latency_ms": 12.5,
            "data": {"providers": [{"venue": "hyperliquid", "enabled": True}]},
        },
        "market_features": {"ok": True, "data": {"count": 10}},
        "ingest_gateway": {"ok": False, "configured": False},
        "core_scorer": {"ok": False, "configured": False},
        "fusion_engine": {"ok": False, "configured": False},
        "strike_zone": {"ok": False, "configured": False},
        "agent_harness": {"ok": False, "configured": False},
        "chaseos": {"ok": False, "configured": False},
    }


def test_pipeline_keeps_optional_connectors_out_of_tier_a_readiness():
    status = assemble_pipeline_status(
        probes=_probes(),
        postgres={"ok": True, "latest_signal_ts": None, "latest_opportunity_ts": None},
        redis={"ok": True},
        catalog_feature_count=17,
        generated_at="2026-09-02T12:00:00+00:00",
    )

    assert status["tier_a"] == {
        "status": "partial",
        "ready_count": 4,
        "total_count": 7,
        "principle": "Standalone core continues when optional connectors are unavailable.",
    }
    assert status["federated"]["connected_count"] == 0
    nodes = {node["id"]: node for node in status["nodes"]}
    assert nodes["hyperliquid"]["status"] == "live"
    assert nodes["market_data"]["status"] == "live"
    assert nodes["regime_engine"]["status"] == "partial"
    assert nodes["scorer_fusion"]["status"] == "offline"
    assert "not configured in this runtime" in nodes["scorer_fusion"]["evidence"][0]
    assert nodes["scorer_fusion"]["missing"] == [
        "core-scorer endpoint and service",
        "fusion-engine endpoint and service",
    ]
    assert nodes["chaseos"]["status"] == "contract_only"


def test_pipeline_surfaces_degraded_strikezone_research_without_granting_authority():
    probes = _probes()
    probes["strikezone_research"] = {
        "ok": False,
        "configured": True,
        "available": True,
        "fresh": True,
        "age_seconds": 42.0,
        "source_updated_at": "2026-09-19T16:07:15+00:00",
        "snapshot_at": "2026-09-19T16:10:00+00:00",
        "payload": {
            "schema_version": "strikezone_research_evidence_v1",
            "run_slug": "2026-09-19-tradesync-v2-completion",
            "status": "public_ready_degraded_sources",
            "public_ready_evidence": True,
            "validation_ok": False,
            "validation_missing": ["perplexity_latest_markdown_detail_gate", "draft_files"],
            "evidence_item_count": 35,
            "source_counts": {"grok_digest": 1, "youtube_transcript": 5},
            "required_source_classes": ["x_social", "perplexity_digest", "grok_digest"],
            "missing_source_classes": ["x_social", "perplexity_digest"],
            "source_tolerance": {"allowed_missing_count": 2, "missing_count": 2, "degraded": True, "over_limit": False},
            "charts_captured": 15,
            "charts_expected": 15,
            "assets": ["BTC", "ETH", "SOL"],
            "operator_approval_required": True,
            "external_delivery_performed": False,
            "trade_execution_allowed": False,
        },
    }

    status = assemble_pipeline_status(
        probes=probes,
        postgres={"ok": True},
        redis={"ok": True},
        catalog_feature_count=17,
    )

    node = {item["id"]: item for item in status["nodes"]}["strike_zone"]
    assert node["status"] == "partial"
    assert node["research_run"]["evidence_item_count"] == 35
    assert node["research_run"]["trade_execution_allowed"] is False
    assert "x_social" in node["missing"]
    assert status["execution_authority"] is False


def test_24h_price_change_is_explicitly_deferred_and_non_blocking():
    status = assemble_pipeline_status(
        probes=_probes(),
        postgres={"ok": True},
        redis={"ok": True},
        catalog_feature_count=17,
    )
    gaps = {gap["id"]: gap for gap in status["capability_gaps"]}
    # Implemented 2026-09-08 from the venue's own prevDayPx, which arrives in
    # the same metaAndAssetCtxs response as the mark price.
    assert gaps["price_change_24h"]["status"] == "implemented"
    assert gaps["price_change_24h"]["blocking"] == "nothing"


def test_pipeline_endpoint_returns_the_versioned_contract():
    payload = assemble_pipeline_status(
        probes=_probes(),
        postgres={"ok": True},
        redis={"ok": True},
        catalog_feature_count=17,
    )
    with patch(
        "app.main.collect_integration_pipeline", new=AsyncMock(return_value=payload)
    ):
        response = client.get("/state/integration-pipeline")

    assert response.status_code == 200
    assert response.json()["schema_version"] == "integration_pipeline_status_v1"
    assert response.json()["execution_authority"] is False


class TestRecordFreshness:
    """Tier A stages must not claim to be live on the strength of an old row."""

    def test_a_recent_timestamp_counts_as_evidence(self):
        from datetime import datetime, timedelta, timezone

        from app.integration_pipeline import _is_recent

        recent = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        assert _is_recent(recent) is True

    def test_an_old_timestamp_does_not(self):
        from datetime import datetime, timedelta, timezone

        from app.integration_pipeline import _is_recent

        stale = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        assert _is_recent(stale) is False

    def test_a_naive_timestamp_is_read_as_utc_not_rejected(self):
        from datetime import datetime, timedelta, timezone

        from app.integration_pipeline import _is_recent

        naive = (datetime.now(timezone.utc) - timedelta(seconds=30)).replace(
            tzinfo=None
        ).isoformat()
        assert _is_recent(naive) is True

    def test_missing_or_malformed_timestamps_are_not_evidence(self):
        from app.integration_pipeline import _is_recent

        assert _is_recent(None) is False
        assert _is_recent("") is False
        assert _is_recent("not-a-timestamp") is False


class TestFreshnessEvidence:
    """A reachable service with frozen pollers must not read as live."""

    def test_fresh_readiness_is_summarised_with_ages(self):
        from app.integration_pipeline import _freshness_evidence

        line = _freshness_evidence({
            "ready": True,
            "symbols": [
                {"symbol": "BTC-PERP", "state": "fresh", "age_seconds": 2.1},
                {"symbol": "ETH-PERP", "state": "fresh", "age_seconds": 3.4},
            ],
        })
        assert "fresh" in line
        assert "BTC-PERP 2.1s" in line

    def test_a_stale_report_names_the_reason(self):
        from app.integration_pipeline import _freshness_evidence

        line = _freshness_evidence({
            "ready": False,
            "reason": "stale: BTC-PERP",
            "symbols": [{"symbol": "BTC-PERP", "state": "stale", "age_seconds": 3600.0}],
        })
        assert "stale: BTC-PERP" in line
        assert "3600.0s" in line

    def test_no_report_is_stated_rather_than_assumed_fresh(self):
        from app.integration_pipeline import _freshness_evidence

        assert "not reported" in _freshness_evidence({})


def test_frozen_pollers_are_not_reported_as_live():
    """The 2026-09-07 failure: reachable service, no data flowing.

    /healthz answered 200 for an hour while nothing was stored. Tier A must
    reflect the job, not the port.
    """
    probes = _probes()
    probes["market_ready"] = {
        "ok": False,
        "data": {
            "ready": False,
            "reason": "stale: BTC-PERP",
            "symbols": [
                {"symbol": "BTC-PERP", "state": "stale", "age_seconds": 3600.0}
            ],
        },
    }

    status = assemble_pipeline_status(
        probes=probes,
        postgres={"ok": True, "latest_signal_ts": None, "latest_opportunity_ts": None},
        redis={"ok": True},
        catalog_feature_count=17,
        generated_at="2026-09-08T12:00:00+00:00",
    )

    nodes = {node["id"]: node for node in status["nodes"]}
    assert nodes["hyperliquid"]["status"] == "offline"
    assert nodes["market_data"]["status"] == "offline"
    # And the reason must be visible, not merely the state.
    assert any("stale" in item for item in nodes["market_data"]["missing"])
    assert status["tier_a"]["ready_count"] < 4
