"""The audit export over fake storage: bounded, checkable, and carrying no secret."""

import csv
import io
import json
from datetime import datetime, timezone
from unittest.mock import patch

from audit_fakes import FakeConn, pool_of
from fastapi.testclient import TestClient

from app.main import app, state
from tradesync_core import audit_export

client = TestClient(app)
NOW = datetime.now(timezone.utc)

SECRET = "sk-live-must-never-be-exported"


def order_rows():
    return [{
        "id": "o1", "created_at": NOW, "decision_id": "d1", "venue": "hyperliquid", "status": "placed",
        "dry_run": True, "txid": None,
        "request": json.dumps({"symbol": "BTC-PERP", "size_usd": 100.0, "api_key": SECRET}),
        "response": json.dumps({"ok": True}),
        # A column the export does not declare.
        "internal_note": "never exported",
    }]


def answers(**over):
    rows = {
        "FROM decisions": [{"id": "d1", "created_at": NOW, "opportunity_id": "op1", "venue": "hyperliquid",
                            "requested": json.dumps({"symbol": "BTC-PERP", "size_usd": 100.0}),
                            "risk": json.dumps({"verdict": "allow"})}],
        "FROM control_envelopes": [],
        "FROM exec_orders": order_rows(),
        "FROM opportunity_outcomes": [],
    }
    rows.update(over)
    return list(rows.items())


def test_the_export_routes_are_registered():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/state/audit/export", "GET") in paths
    assert ("/state/audit/export.csv", "GET") in paths


def test_it_refuses_rather_than_guessing_when_the_database_is_unavailable():
    with patch.object(state, "pool", None):
        assert client.get("/state/audit/export").status_code == 503
        assert client.get("/state/audit/export.csv", params={"section": "orders"}).status_code == 503


def test_the_json_export_carries_every_section_and_its_bounds():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        body = client.get("/state/audit/export", params={"days": 7}).json()
    assert set(body["sections"]) == {"decisions", "approvals", "orders", "outcomes",
                                     "paper_rehearsals", "paper_positions", "paper_position_events"}
    assert body["bounds"]["max_window_days"] == audit_export.MAX_WINDOW_DAYS
    assert body["window"]["days"] == 7.0 and body["window"]["to"] == body["generated_at"]
    assert len(body["content_digest"]) == 64


def test_no_secret_reaches_the_json_export():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        response = client.get("/state/audit/export")
    assert SECRET not in response.text
    body = response.json()
    assert body["sections"]["orders"]["rows"][0]["request"]["api_key"] == audit_export.REDACTED
    assert body["redacted_fields"] == 1


def test_no_secret_reaches_the_csv_export_and_no_undeclared_column_does_either():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        response = client.get("/state/audit/export.csv", params={"section": "orders"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert SECRET not in response.text
    assert "internal_note" not in response.text

    header, row = list(csv.reader(io.StringIO(response.text)))
    assert header == list(audit_export.SECTIONS["orders"])
    assert json.loads(dict(zip(header, row))["request"])["api_key"] == audit_export.REDACTED


def test_the_csv_states_the_bounds_that_applied_in_its_headers():
    """A spreadsheet cannot show a note, so the facts travel in the response."""
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        response = client.get("/state/audit/export.csv", params={"section": "orders", "days": 3})
    assert response.headers["X-Export-Truncated"] == "false"
    assert response.headers["X-Export-Row-Count"] == "1"
    assert response.headers["X-Export-Row-Cap"] == str(audit_export.MAX_ROWS_PER_SECTION)
    assert len(response.headers["X-Export-Content-Digest"]) == 64
    assert response.headers["X-Export-Redacted-Fields"] == "1"
    datetime.fromisoformat(response.headers["X-Export-Generated-At"])


def test_a_section_that_reached_its_cap_says_so():
    many = [{**order_rows()[0], "id": f"o{i}"} for i in range(4)]
    with patch.object(state, "pool", pool_of(FakeConn(answers(**{"FROM exec_orders": many})))):
        response = client.get("/state/audit/export.csv", params={"section": "orders", "rows": 2})
        body = client.get("/state/audit/export", params={"rows": 2}).json()
    assert response.headers["X-Export-Truncated"] == "true"
    assert response.headers["X-Export-Row-Count"] == "2"
    assert body["sections"]["orders"]["truncated"] is True
    assert body["truncated"] is True


def test_an_unknown_section_is_refused_by_name():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        response = client.get("/state/audit/export.csv", params={"section": "wallets"})
    assert response.status_code == 422
    assert "not an exportable section" in response.text


def test_the_window_is_bounded_by_the_route():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        assert client.get("/state/audit/export", params={"days": 0}).status_code == 422
        assert client.get("/state/audit/export",
                          params={"days": audit_export.MAX_WINDOW_DAYS + 1}).status_code == 422


def test_an_empty_section_is_a_result_not_an_error():
    with patch.object(state, "pool", pool_of(FakeConn(answers(**{"FROM exec_orders": []})))):
        response = client.get("/state/audit/export.csv", params={"section": "orders"})
    assert response.status_code == 200
    assert response.text.strip() == ",".join(audit_export.SECTIONS["orders"])


def test_every_read_goes_through_the_bounded_pattern():
    conn = FakeConn(answers())
    with patch.object(state, "pool", pool_of(conn)):
        client.get("/state/audit/export")
    assert conn.bounded() and len(conn.statements) == len(audit_export.SECTIONS) == 7
