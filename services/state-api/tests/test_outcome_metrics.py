"""Thesis adherence and regime fit over fake storage, served from frozen evidence only."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

from audit_fakes import FakeConn, pool_of
from fastapi.testclient import TestClient

from app.main import app, state
from tradesync_core.regime_weights import config_digest

client = TestClient(app)
NOW = datetime.now(timezone.utc)

# The worked example from tradesync_core.thesis_adherence: three checks pass,
# two fail, nothing absent.
PLAN = {"side": "long", "stop": 98.50, "target": 103.00, "expiry": 4600.0,
        "rules": {"max_depth_bps": 5.0},
        "slippage": {"entry": {"mid": 100.00, "fill_price": 100.02, "half_spread_bps": 1.0}}}
STATE = {"side": "long", "status": "closed",
         "exit": {"rule": "operator_close", "fill_price": 98.20, "at": 5000.0}}

RULEBOOK = {"schema_version": "regime_rulebook_v1", "rulebook_id": "tradesync-intraday-regime", "version": "1.0.0"}
DIGEST = config_digest(RULEBOOK)


def position_rows():
    return [{"id": "p1", "symbol": "BTC-PERP", "created_at": NOW, "updated_at": NOW,
             "initial_plan": json.dumps(PLAN), "position_state": json.dumps(STATE)}]


def call_rows(digest=DIGEST, regime="rising"):
    return [{"id": "o1", "symbol": "BTC-PERP", "direction": "LONG", "opened_at_s": NOW.timestamp(),
             "snapshot_ts": NOW, "entry_regime": regime, "rulebook_digest": digest}]


def test_both_readings_are_registered():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/state/outcomes/thesis-adherence", "GET") in paths
    assert ("/state/outcomes/regime-fit", "GET") in paths


def test_they_refuse_rather_than_guessing_when_the_database_is_unavailable():
    with patch.object(state, "pool", None):
        assert client.get("/state/outcomes/thesis-adherence").status_code == 503
        assert client.get("/state/outcomes/regime-fit").status_code == 503


def test_adherence_scores_a_stored_plan_against_its_stored_lifecycle():
    conn = FakeConn([("FROM managed_paper_positions", position_rows())])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/thesis-adherence").json()
    scored = body["positions"][0]
    assert scored["position_id"] == "p1" and scored["symbol"] == "BTC-PERP"
    assert scored["adherence"] == 0.6
    assert scored["departures"] == ["stop_respected", "time_respected"]
    assert body["summary"]["mean_adherence"] == 0.6
    assert body["summary"]["positions_scored"] == 1
    assert conn.bounded()


def test_adherence_reads_the_frozen_plan_and_never_a_market():
    conn = FakeConn([("FROM managed_paper_positions", position_rows())])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/thesis-adherence").json()
    assert "no market was re-read" in body["positions"][0]["basis"]
    assert body["authority"] == "read_only"


def test_an_empty_portfolio_scores_nothing_rather_than_zero():
    with patch.object(state, "pool", pool_of(FakeConn([]))):
        body = client.get("/state/outcomes/thesis-adherence").json()
    assert body["positions"] == [] and body["summary"]["mean_adherence"] is None


def test_regime_fit_abstains_as_undeclared_while_no_rulebook_declares_an_expectation():
    """The live case today: every call abstains, and that is reported as an abstention."""
    conn = FakeConn([
        ("opportunity_entry_regimes", call_rows()),
        ("FROM regime_rulebooks", [{"config_digest": DIGEST, "config": json.dumps(RULEBOOK)}]),
    ])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/regime-fit").json()
    assert body["calls"][0]["verdict"] == "undeclared"
    assert body["summary"]["regime_fit_rate"] is None
    assert body["summary"]["abstained_by_reason"] == {"undeclared": 1}
    assert body["rulebooks_held"] == 1


def test_regime_fit_judges_a_call_whose_rulebook_declares_an_expectation():
    declared = {**RULEBOOK, "regime_expectation": {"schema": "regime_expectation_v1",
                                                   "LONG": ["rising"], "SHORT": ["falling"]}}
    digest = config_digest(declared)
    conn = FakeConn([
        ("opportunity_entry_regimes", call_rows(digest=digest)),
        ("FROM regime_rulebooks", [{"config_digest": digest, "config": json.dumps(declared)}]),
    ])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/regime-fit").json()
    assert body["calls"][0]["verdict"] == "fit"
    assert body["summary"]["regime_fit_rate"] == 1.0


def test_a_call_scored_under_a_rulebook_no_longer_held_abstains():
    conn = FakeConn([
        ("opportunity_entry_regimes", call_rows(digest="f" * 64)),
        ("FROM regime_rulebooks", []),
    ])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/regime-fit").json()
    assert body["calls"][0]["verdict"] == "no_rulebook"
    assert body["rulebooks_held"] == 0


def test_an_unlabelled_entry_regime_abstains_rather_than_counting_as_a_misfit():
    declared = {**RULEBOOK, "regime_expectation": {"schema": "regime_expectation_v1", "LONG": ["rising"]}}
    digest = config_digest(declared)
    conn = FakeConn([
        ("opportunity_entry_regimes", call_rows(digest=digest, regime=None)),
        ("FROM regime_rulebooks", [{"config_digest": digest, "config": json.dumps(declared)}]),
    ])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/regime-fit").json()
    assert body["calls"][0]["verdict"] == "unlabelled"
    assert body["summary"]["misfit"] == 0


def test_the_regime_fit_reading_carries_its_exact_window():
    conn = FakeConn([("opportunity_entry_regimes", call_rows())])
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/outcomes/regime-fit", params={"hours": 24}).json()
    taken = datetime.fromisoformat(body["generated_at"])
    start = datetime.fromisoformat(body["window"]["from"])
    assert body["window"]["hours"] == 24
    assert round((taken - start).total_seconds()) == 24 * 3600


def test_the_windows_and_limits_are_bounded_by_the_routes():
    with patch.object(state, "pool", pool_of(FakeConn([]))):
        assert client.get("/state/outcomes/regime-fit", params={"hours": 721}).status_code == 422
        assert client.get("/state/outcomes/thesis-adherence", params={"limit": 501}).status_code == 422
