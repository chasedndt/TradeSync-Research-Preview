"""The entry-evidence comparison endpoint: read-only, cached, and honest about coverage."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest
from fastapi.testclient import TestClient

from app import entry_evidence_comparison as module
from app.main import app, state

client = TestClient(app)
T0 = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
HISTORY = {"books": T0, "open_interest": T0, "liquidations": T0}


def book(bid_price=99.0, bid_size=7.0, ask_price=101.0, ask_size=3.0):
    return {"mid_price": 100.0, "bids": json.dumps([[bid_price, bid_size]]), "asks": json.dumps([[ask_price, ask_size]])}


def outcome(index, horizon=60, direction="LONG", signed=0.3):
    return {"opportunity_id": f"00000000-0000-0000-0000-{index:012d}", "symbol": "BTC-PERP",
            "direction": direction, "horizon_minutes": horizon,
            "opened_at": T0 + timedelta(minutes=90 * index), "signed_return_pct": signed}


def context(index, *, events=4, interest=(110.0, 100.0), funding=0.0000125, **book_over):
    return {"opportunity_id": f"00000000-0000-0000-0000-{index:012d}", "symbol": "BTC-PERP",
            **book(**book_over), "open_interest_latest": interest[0], "open_interest_earlier": interest[1],
            "funding_rate": funding, "long_usd": 900.0 if events else None,
            "short_usd": 100.0 if events else None, "events": events}


def fake_pool(history, outcomes, contexts, positions=0):
    conn = MagicMock()
    conn.fetch = AsyncMock(side_effect=[history, outcomes, contexts])
    conn.fetchval = AsyncMock(return_value=positions)
    conn.execute = AsyncMock()
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(acquire=MagicMock(return_value=acquire)), conn


@pytest.mark.asyncio
async def test_the_reading_measures_the_declared_family_and_writes_nothing():
    outcomes = [outcome(i) for i in range(40)]
    contexts = [context(i) for i in range(40)]
    pool, conn = await _run_pool(outcomes, contexts)
    report = await module.compute_entry_evidence_comparison(pool)

    assert report["schema_version"] == "entry-evidence-ablation-v1"
    assert report["family"]["version"] == "entry-evidence-ablation-v1" and len(report["family"]["sha256"]) == 64
    assert len(report["cells"]) == 36  # six readings, two polarities, three horizons
    assert report["population"]["cases"] == 40 and report["population"]["symbols"] == ["BTC-PERP"]
    assert report["authority"] == "research_only" and report["promotion_allowed"] is False

    # Read-only: SELECTs, and the bounded-read settings, and nothing else.
    assert all(call.args[0].lstrip().upper().startswith(("SELECT", "WITH")) for call in conn.fetch.await_args_list)
    assert all(call.args[0].startswith("SET LOCAL ") for call in conn.execute.await_args_list)


async def _run_pool(outcomes, contexts, positions=0):
    pool, conn = fake_pool([HISTORY], outcomes, contexts, positions)
    return pool, conn


@pytest.mark.asyncio
async def test_a_reading_that_cannot_be_reconstructed_is_absent_not_zero():
    """The timeframe lean is stored nowhere for a past call, and the liquidations of a quiet hour are missing."""
    outcomes = [outcome(i) for i in range(12)]
    contexts = [context(i, events=0) for i in range(12)]
    pool, _ = await _run_pool(outcomes, contexts)
    report = await module.compute_entry_evidence_comparison(pool)

    coverage = report["population_source"]["coverage"]
    assert coverage["no_liquidation_received"] == 12 and coverage["no_timeframe_measurement"] == 12
    assert report["population"]["context_coverage"]["liquidation_skew"] == 0
    assert report["population"]["context_coverage"]["horizon_lean"] == 0
    assert report["population"]["context_coverage"]["book_imbalance"] == 12
    lean = [cell for cell in report["cells"] if cell["variable"] == "horizon_lean"]
    assert lean and all(cell["sample_state"] == "no_context" and not cell["tested"] for cell in lean)


@pytest.mark.asyncio
async def test_the_population_says_it_is_opportunities_and_names_the_managed_paper_count():
    pool, _ = await _run_pool([outcome(i) for i in range(8)], [context(i) for i in range(8)], positions=0)
    report = await module.compute_entry_evidence_comparison(pool)
    source = report["population_source"]
    assert "not managed paper positions" in source["population"]
    assert "No managed paper position has been opened" in source["why"]
    assert report["managed_paper"]["positions"] == 0
    assert source["recorded_history_begins"]["books"] == T0.isoformat()


@pytest.mark.asyncio
async def test_no_recorded_history_measures_nothing_and_says_so():
    pool, conn = fake_pool([{"books": None, "open_interest": None, "liquidations": None}], [], [])
    report = await module.compute_entry_evidence_comparison(pool)
    assert report["cells"] == [] and "not a result" in report["note"]
    assert report["promotion_allowed"] is False
    # The outcome and context scans are never issued when there is nothing to read.
    assert conn.fetch.await_count == 1


def test_the_endpoint_needs_a_database_and_substitutes_nothing():
    with patch.object(state, "pool", None):
        assert client.get("/state/research/entry-evidence-comparison").status_code == 503


def test_a_cold_reading_answers_computing_rather_than_an_empty_result():
    pool, _ = fake_pool([HISTORY], [], [])
    try:
        with patch.object(state, "pool", pool):
            response = client.get("/state/research/entry-evidence-comparison")
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "computing" and body["schema_version"] == "entry-evidence-ablation-v1"
        assert "has not been measured" in body["note"]
    finally:
        module.CACHE.clear()
