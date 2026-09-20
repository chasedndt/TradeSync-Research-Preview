"""The five reconciliation views over fake storage: read-only, bounded, and exact about the window."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from audit_fakes import FakeConn, pool_of
from fastapi.testclient import TestClient

from app.main import app, state

client = TestClient(app)
NOW = datetime.now(timezone.utc)


def answers(**over):
    """Rows for each of the six reads, each needle unique to its statement."""
    rows = {
        "FROM events": [{"id": "e1", "source": "hyperliquid", "kind": "trade", "symbol": "BTC-PERP",
                         "ts": NOW - timedelta(minutes=5)},
                        {"id": "e2", "source": "hyperliquid", "kind": "trade", "symbol": "BTC-PERP",
                         "ts": NOW - timedelta(minutes=4)}],
        "FROM signals": [{"id": "s1", "event_ids": ["e1"]}],
        "links->>'evidence_digest'": [
            {"id": "o1", "symbol": "BTC-PERP", "timeframe": "1m", "dir": "LONG",
             "snapshot_ts_s": NOW.timestamp() - 300, "evidence_digest": "d" * 64},
            {"id": "o2", "symbol": "BTC-PERP", "timeframe": "1m", "dir": "LONG",
             "snapshot_ts_s": NOW.timestamp() - 295, "evidence_digest": "d" * 64},
        ],
        "FROM control_envelopes": [{"envelope_id": "env1", "approval_id": "a1", "candidate_id": "c1",
                                    "created_at_s": NOW.timestamp() - 6 * 3600, "consumed_at_s": None}],
        "FROM exec_orders": [],
        "LEFT JOIN opportunity_outcomes": [
            {"id": "o1", "symbol": "BTC-PERP", "opened_at_s": NOW.timestamp() - 200 * 60, "outcomes": []},
        ],
    }
    rows.update(over)
    return list(rows.items())


def read(conn, **params):
    with patch.object(state, "pool", pool_of(conn)):
        response = client.get("/state/reconciliation/views", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def view_of(body, name):
    return next(view for view in body["views"] if view["name"] == name)


def test_the_route_is_registered_beside_the_execution_reconciliation():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/state/reconciliation/views", "GET") in paths
    assert ("/state/execution/reconciliation", "GET") in paths


def test_it_refuses_rather_than_guessing_when_the_database_is_unavailable():
    with patch.object(state, "pool", None):
        assert client.get("/state/reconciliation/views").status_code == 503


def test_all_five_views_are_returned_and_each_says_what_it_compared_and_over_what_window():
    body = read(FakeConn(answers()))
    names = [view["name"] for view in body["views"]]
    assert names == ["orphaned_events", "duplicate_candidates", "stale_approvals",
                     "partial_orders", "missing_outcomes"]
    for view in body["views"]:
        assert view["compared"] and view["window"]
        assert str(body["window"]["hours"]) in view["window"] or "h)" in view["window"]


def test_the_reading_carries_the_exact_instant_and_the_exact_window():
    body = read(FakeConn(answers()), hours=6)
    taken = datetime.fromisoformat(body["generated_at"])
    start = datetime.fromisoformat(body["window"]["from"])
    assert body["window"]["hours"] == 6
    assert body["window"]["to"] == body["generated_at"]
    assert round((taken - start).total_seconds()) == 6 * 3600


def test_an_event_no_signal_referenced_is_reported():
    body = read(FakeConn(answers()))
    orphans = view_of(body, "orphaned_events")
    assert orphans["considered"] == 2
    assert [f["subject_id"] for f in orphans["findings"]] == ["e2"]


def test_two_opportunities_sharing_an_evidence_digest_are_reported():
    body = read(FakeConn(answers()))
    duplicates = view_of(body, "duplicate_candidates")
    assert [f["kind"] for f in duplicates["findings"]] == ["duplicate_evidence_digest"]


def test_an_approval_never_consumed_past_its_validity_is_reported():
    body = read(FakeConn(answers()))
    assert [f["kind"] for f in view_of(body, "stale_approvals")["findings"]] == ["stale_approval"]


def test_the_empty_order_table_is_reported_as_nothing_compared_not_as_clean():
    """No order has ever been placed. That must not read as a passing reconciliation."""
    orders = view_of(read(FakeConn(answers())), "partial_orders")
    assert orders["considered"] == 0
    assert "nothing to compare" in orders["summary"]


def test_a_closed_horizon_with_no_verdict_is_reported():
    missing = view_of(read(FakeConn(answers())), "missing_outcomes")
    assert {f["observed"]["horizon_minutes"] for f in missing["findings"]} == {15, 60}


def test_a_tree_with_nothing_wrong_is_reported_as_a_clean_result():
    conn = FakeConn(answers(**{
        "FROM events": [{"id": "e1", "source": "hyperliquid", "kind": "trade", "symbol": "BTC-PERP", "ts": NOW}],
        "links->>'evidence_digest'": [],
        "FROM control_envelopes": [],
        "LEFT JOIN opportunity_outcomes": [],
    }))
    body = read(conn)
    assert body["clean"] is True and body["findings"] == 0
    assert "no divergence" in body["summary"]


def test_every_read_goes_through_the_bounded_pattern():
    """This database has a history of crash resets under whole-table scans."""
    conn = FakeConn(answers())
    read(conn)
    assert conn.bounded()
    assert len(conn.statements) == 6


def test_the_window_is_bounded_by_the_route():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        assert client.get("/state/reconciliation/views", params={"hours": 0}).status_code == 422
        assert client.get("/state/reconciliation/views", params={"hours": 721}).status_code == 422


def test_the_reading_claims_no_authority_and_points_at_the_existing_view():
    body = read(FakeConn(answers()))
    assert body["authority"] == "read_only"
    assert "/state/execution/reconciliation" in body["beside"]
    assert "can place, amend, cancel or consume" in body["note"]
