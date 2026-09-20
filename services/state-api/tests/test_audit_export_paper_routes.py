"""The export's paper sections through the routes: shaped rows, bounded reads, CSV per section and no tick flood."""

import csv
import io
import json
from datetime import datetime, timezone
from unittest.mock import patch

from audit_fakes import FakeConn, pool_of
from fastapi.testclient import TestClient

from app import audit_export_paper_queries as paper_queries
from app.main import app, state
from tradesync_core import audit_export
from tradesync_core.managed_paper import advance, open_position

client = TestClient(app)
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def book(at, bid, ask):
    return {"poll_ts": at * 1000, "best_bid": bid, "best_ask": ask,
            "bids": [{"price": bid, "size": 100.0}], "asks": [{"price": ask, "size": 100.0}]}


OPENED = open_position("long", "scalp", 1000, 1, book(1000, 99.99, 100.01), 1000)
CLOSED = advance(advance(OPENED, book(1010, 100.4, 100.41), 1010), book(1020, 100.7, 100.71), 1020, manual_close=True)


def rehearsals():
    return [{"id": "r1", "created_at": NOW, "opportunity_id": "o1", "symbol": "BTC-PERP", "direction": "LONG",
             "size_usd": 250.0, "status": "refused", "plan": json.dumps({"action": "Paper market order"}),
             "risk_verdict": json.dumps({"allowed": False, "reason_code": "MARKET_STALE"}), "fill": None,
             "market": json.dumps({"snapshot_age_ms": 45000}), "evidence_digest": "d" * 64}]


def positions():
    return [{"id": "p1", "opportunity_id": "o1", "symbol": "BTC-PERP", "created_at": NOW, "updated_at": NOW,
             "evidence_sha256": "e" * 64, "position_state": json.dumps(CLOSED), "evidence_digest": "d" * 64,
             "events": 3, "observation_events": 1, "first_event_at": NOW, "last_event_at": NOW}]


def events():
    return [{"id": "e2", "position_id": "p1", "symbol": "BTC-PERP", "created_at": NOW, "kind": "closed",
             "payload": json.dumps({"position": CLOSED, "book": book(1020, 100.7, 100.71), "funding_rows_added": 0})},
            {"id": "e1", "position_id": "p1", "symbol": "BTC-PERP", "created_at": NOW, "kind": "opened",
             "payload": json.dumps(OPENED)}]


def answers(**over):
    rows = {
        "FROM paper_rehearsals": lambda days, cap: rehearsals()[:cap],
        "JOIN managed_paper_events e": lambda days, cap: events()[:cap],
        "FROM managed_paper_positions p\nLEFT JOIN": lambda days, cap: positions()[:cap],
    }
    rows.update(over)
    return list(rows.items())


def test_the_json_export_carries_paper_activity_with_its_digests():
    conn = FakeConn(answers())
    with patch.object(state, "pool", pool_of(conn)):
        body = client.get("/state/audit/export", params={"days": 14}).json()
    sections = body["sections"]
    [rehearsal] = sections["paper_rehearsals"]["rows"]
    assert rehearsal["status"] == "refused" and rehearsal["risk_verdict"]["reason_code"] == "MARKET_STALE"
    assert rehearsal["evidence_digest"] == "d" * 64

    [position] = sections["paper_positions"]["rows"]
    assert position["status"] == "closed" and position["exit_reason"] == "operator_close"
    assert position["net_usdc"] == CLOSED["net_estimate_usdc"] and position["evidence_sha256"] == "e" * 64
    assert position["observation_events"] == 1 and position["created_at"] == NOW.isoformat()

    closed, opened = sections["paper_position_events"]["rows"]
    assert (closed["kind"], opened["kind"]) == ("closed", "opened")
    assert opened["fill_price"] == OPENED["entry_price"] and closed["fill_price"] == CLOSED["exit_price"]
    assert opened["payload_sha256"] == audit_export.digest_of(OPENED)
    assert sections["paper_position_events"]["computed_digests"] == ["payload_sha256"]
    assert conn.bounded()


def test_the_paper_reads_are_windowed_bounded_and_never_load_observation_ticks():
    conn = FakeConn(answers())
    with patch.object(state, "pool", pool_of(conn)):
        client.get("/state/audit/export", params={"days": 3, "rows": 50})
    assert conn.bounded()
    assert "e.kind <> 'observed'" in paper_queries.EVENTS_SQL
    assert "count(*) FILTER (WHERE kind = 'observed')" in paper_queries.POSITIONS_SQL
    for sql in (paper_queries.REHEARSALS_SQL, paper_queries.POSITIONS_SQL, paper_queries.EVENTS_SQL):
        assert "make_interval(days => $1)" in sql and "LIMIT $2" in sql
    assert "p.updated_at > now()" in paper_queries.POSITIONS_SQL and "p.updated_at > now()" in paper_queries.EVENTS_SQL


def test_each_paper_section_exports_as_csv_with_its_declared_header():
    for section, count in (("paper_rehearsals", 1), ("paper_positions", 1), ("paper_position_events", 2)):
        with patch.object(state, "pool", pool_of(FakeConn(answers()))):
            response = client.get("/state/audit/export.csv", params={"section": section})
        assert response.status_code == 200
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == list(audit_export.SECTIONS[section]) and len(rows) == count + 1
        assert response.headers["X-Export-Row-Count"] == str(count)


def test_a_paper_section_that_reached_its_cap_says_so():
    with patch.object(state, "pool", pool_of(FakeConn(answers()))):
        body = client.get("/state/audit/export", params={"rows": 1}).json()
    events_section = body["sections"]["paper_position_events"]
    assert events_section["row_count"] == 1 and events_section["truncated"] is True and body["truncated"] is True


def test_an_empty_paper_window_is_a_result():
    empty = {"FROM paper_rehearsals": [], "JOIN managed_paper_events e": [], "FROM managed_paper_positions p\nLEFT JOIN": []}
    with patch.object(state, "pool", pool_of(FakeConn(answers(**empty)))):
        body = client.get("/state/audit/export").json()
    assert all(body["sections"][name]["row_count"] == 0 for name in paper_queries.PAPER_SECTION_SQL)
