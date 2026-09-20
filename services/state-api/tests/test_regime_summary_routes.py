"""The regime-summary route reads one snapshot and the stored history, and never answers a bare unknown."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import regime_summary_routes as routes
from app.main import app, state

client = TestClient(app)

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def snapshot(**over):
    """A healthy reading, timed against the real clock.

    The route stamps its own ``now_ms``, and an input older than the freshness
    limit is correctly refused, so a fixture pinned to a fixed epoch would read
    as stale on every run and never exercise the classified path.
    """
    now_ms = int(time.time() * 1000)
    base = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": now_ms - 1_000,
        "snapshot_age_ms": 1_000,
        "data_age_ms": 1_000,
        "regimes": {"funding": "neutral", "oi": "build", "volume": "high", "trend": "strong_trend",
                    "market_condition": "trending_healthy", "confidence": "high", "confidence_note": None},
        "funding": {"regime": "neutral"},
        "oi": {"regime": "build"},
        "volume": {"regime": "high"},
        "available_metrics": [
            {"metric": "funding", "status": "REAL", "source": "hyperliquid", "last_updated": now_ms - 1_000},
            {"metric": "oi", "status": "REAL", "source": "hyperliquid", "last_updated": now_ms - 1_000},
            {"metric": "volume", "status": "REAL", "source": "hyperliquid", "last_updated": now_ms - 1_000},
        ],
    }
    base.update(over)
    return base


class Pool:
    """Stands in for the asyncpg pool; the route only needs acquire() and fetch()."""

    def __init__(self, rows=()):
        self.rows = list(rows)

    def acquire(self):
        rows = self.rows

        class Ctx:
            async def __aenter__(self):
                conn = AsyncMock()
                conn.fetch = AsyncMock(return_value=rows)
                return conn

            async def __aexit__(self, *exc):
                return False

        return Ctx()


def history_row(regime, opportunity_id):
    return {"regime": regime, "trailing_return_pct": 0.4, "lookback_minutes": 60,
            "computed_at": NOW, "opportunity_id": opportunity_id, "snapshot_ts": NOW}


def test_the_summary_carries_the_evidence_behind_a_classified_regime() -> None:
    with patch.object(state, "pool", Pool()), \
            patch.object(routes, "read_snapshot", AsyncMock(return_value=snapshot())):
        resp = client.get("/state/market/regime-summary?symbol=btc-perp")
    body = resp.json()
    assert resp.status_code == 200
    assert body["symbol"] == "BTC-PERP" and body["schema_version"] == "regime_summary_v1"
    assert body["current"]["condition"] == "trending_healthy" and body["current"]["known"] is True
    assert body["confidence"]["level"] == "high" and body["why_not_higher"] == []
    assert [c["input"] for c in body["components"]] == ["funding", "oi", "volume"]
    assert body["read_at_ms"] > 0 and body["authority"] == "context_only"


def test_a_market_data_outage_names_every_unread_input_instead_of_a_bare_unknown() -> None:
    with patch.object(state, "pool", Pool()), \
            patch.object(routes, "read_snapshot", AsyncMock(return_value=None)):
        resp = client.get("/state/market/regime-summary?symbol=ETH-PERP")
    body = resp.json()
    # Deliberately a 200: "market-data did not answer" is the explanation the page exists to show.
    assert resp.status_code == 200 and body["source_read"] is False
    assert body["current"]["condition"] == "unknown"
    assert [m["input"] for m in body["missing_inputs"]] == ["funding", "oi", "volume"]
    assert len(body["why_not_higher"]) == 3


def test_the_stored_labels_become_the_transition_history() -> None:
    rows = [history_row("rising", "11111111-1111-1111-1111-111111111111"),
            history_row("rising", "22222222-2222-2222-2222-222222222222"),
            history_row("falling", "33333333-3333-3333-3333-333333333333")]
    with patch.object(state, "pool", Pool(rows)), \
            patch.object(routes, "read_snapshot", AsyncMock(return_value=snapshot())):
        resp = client.get("/state/market/regime-summary?symbol=BTC-PERP")
    history = resp.json()["history"]
    assert history["held"]["regime"] == "rising" and history["held"]["readings"] == 2
    assert [(t["from"], t["to"]) for t in history["transitions"]] == [("falling", "rising")]
    assert history["readings"] == 3


def test_the_reading_still_stands_when_the_history_cannot_be_read() -> None:
    with patch.object(state, "pool", None), \
            patch.object(routes, "read_snapshot", AsyncMock(return_value=snapshot())):
        resp = client.get("/state/market/regime-summary?symbol=BTC-PERP")
    body = resp.json()
    assert resp.status_code == 200
    assert body["history"]["transitions"] == [] and body["history"]["held"] is None
    assert body["current"]["condition"] == "trending_healthy"
