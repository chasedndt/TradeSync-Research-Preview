"""The keyless delivery-state reading: six states from stored facts, over a window, with no device secret."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from audit_fakes import FakeConn, pool_of
from fastapi.testclient import TestClient

from app import mobile_delivery, mobile_delivery_states as states
from app.main import app, state

client = TestClient(app)
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
KEY = "k" * 40
DEVICE = uuid.UUID("11111111-2222-3333-4444-555555555555")


def outbox(status, **over):
    """An outbox row as the database returns it, carrying columns the reading must never pass on."""
    row = {
        "id": uuid.uuid4(), "device_id": DEVICE, "platform": "ios", "kind": "attention", "status": status,
        "transport": None, "attempts": 0, "created_at": NOW, "next_attempt_at": NOW, "attempted_at": None,
        "accepted_at": None, "acknowledged_at": None, "acknowledged_by": None, "dead_lettered_at": None,
        "dead_letter_reason": None, "last_error": None, "expires_at": NOW + timedelta(minutes=10),
        # Device secrets and personal text that a query could one day return.
        "topic": "tradesync-secret-topic", "endpoint": "https://fcm.googleapis.com/fcm/send/secret",
        "ack_token_hash": "f" * 64, "provider_id": "provider-message-1", "device_label": "Chase's iPhone",
    }
    row.update(over)
    return row


def lifecycle_rows():
    return [
        outbox("queued"),
        outbox("retry", attempts=2, transport="ntfy", attempted_at=NOW + timedelta(seconds=30), last_error="ConnectError"),
        outbox("provider_accepted", attempts=1, transport="web_push", attempted_at=NOW + timedelta(seconds=1),
               accepted_at=NOW + timedelta(seconds=2)),
        outbox("operator_confirmed", attempts=1, transport="ntfy", attempted_at=NOW, accepted_at=NOW + timedelta(seconds=1),
               acknowledged_at=NOW + timedelta(minutes=3), acknowledged_by="operator"),
        outbox("provider_accepted", attempts=1, transport="web_push", attempted_at=NOW, accepted_at=NOW,
               acknowledged_at=NOW + timedelta(seconds=40), acknowledged_by="device"),
        outbox("expired", attempts=1, transport="ntfy", attempted_at=NOW),
        outbox("dead_letter", attempts=5, transport="ntfy", attempted_at=NOW, dead_lettered_at=NOW + timedelta(minutes=4),
               dead_letter_reason="No delivery after 5 attempts. Last error ReadTimeout.", last_error="ReadTimeout"),
        outbox("failed", attempts=3, transport="ntfy", attempted_at=NOW, last_error="HTTPStatusError"),
    ]


def read(stored, **params):
    conn = FakeConn([("FROM mobile_alert_outbox", lambda days, cap: stored[:cap])])
    with patch.object(state, "pool", pool_of(conn)):
        response = client.get("/state/mobile-alerts/delivery-states", params=params)
    return response, conn


def test_the_reading_is_registered_beside_the_keyed_ledger():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/state/mobile-alerts/delivery-states", "GET") in paths
    assert ("/state/mobile-alerts/ledger", "GET") in paths


def test_it_needs_no_control_key_while_the_ledger_keeps_its_key():
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        response, _ = read(lifecycle_rows())
        assert response.status_code == 200
        assert client.get("/state/mobile-alerts/ledger").status_code == 403


def test_a_database_it_cannot_read_is_an_error_and_never_an_empty_window():
    with patch.object(state, "pool", None):
        assert client.get("/state/mobile-alerts/delivery-states").status_code == 503


def test_an_empty_window_is_a_result_with_its_exact_bounds():
    response, _ = read([], days=1)
    body = response.json()
    assert response.status_code == 200
    assert body["rows"] == [] and body["row_count"] == 0 and body["truncated"] is False
    assert body["window"]["days"] == 1 and body["window"]["to"] == body["generated_at"]
    frm, to = datetime.fromisoformat(body["window"]["from"]), datetime.fromisoformat(body["window"]["to"])
    assert to - frm == timedelta(days=1)
    assert body["counts"] == {name: 0 for name in states.STATES}


def test_each_state_is_one_stored_fact_with_its_stored_time():
    body = read(lifecycle_rows())[0].json()
    by_status = [(row["status"], row["states"]) for row in body["rows"]]
    queued, retry, accepted, confirmed, tapped, expired, dead, failed = (s for _, s in by_status)

    assert queued["triggered"]["at"] == NOW.isoformat() and all(queued[name] is None for name in states.STATES[1:])
    assert retry["routed"] == {"at": (NOW + timedelta(seconds=30)).isoformat(), "transport": "ntfy", "attempts": 2}
    assert retry["delivered"] is None
    assert accepted["delivered"] == {"at": (NOW + timedelta(seconds=2)).isoformat(), "transport": "web_push"}
    assert confirmed["acknowledged"] == {"at": (NOW + timedelta(minutes=3)).isoformat(), "by": "operator"}
    assert tapped["acknowledged"]["by"] == "device"
    assert expired["expired"] == {"at": (NOW + timedelta(minutes=10)).isoformat(), "basis": "end of window"}
    assert expired["delivered"] is None and expired["dead_lettered"] is None
    assert dead["dead_lettered"] == {"at": (NOW + timedelta(minutes=4)).isoformat(),
                                     "reason": "No delivery after 5 attempts. Last error ReadTimeout."}
    # Written before dead letters were recorded: shown as stored, not promoted to a state no row recorded.
    assert failed["dead_lettered"] is None and failed["routed"]["attempts"] == 3


def test_stored_statuses_travel_verbatim_and_no_state_is_invented():
    body = read(lifecycle_rows())[0].json()
    assert body["states"] == ["triggered", "routed", "delivered", "acknowledged", "expired", "dead_lettered"]
    assert [row["status"] for row in body["rows"]] == [
        "queued", "retry", "provider_accepted", "operator_confirmed", "provider_accepted", "expired", "dead_letter", "failed"]
    assert all(set(row["states"]) == set(states.STATES) for row in body["rows"])
    assert body["counts"] == {"triggered": 8, "routed": 7, "delivered": 3, "acknowledged": 2, "expired": 1, "dead_lettered": 1}
    assert body["stored_statuses"] == {"queued": 1, "retry": 1, "provider_accepted": 2, "operator_confirmed": 1,
                                       "expired": 1, "dead_letter": 1, "failed": 1}
    assert set(body["definitions"]) == set(states.STATES)


def test_no_device_secret_or_label_leaves_the_reading():
    response, _ = read(lifecycle_rows())
    for secret in ("tradesync-secret-topic", "fcm.googleapis.com", "f" * 64, "provider-message-1", "Chase's iPhone"):
        assert secret not in response.text
    assert all(set(row) == set(states.COLUMNS) | {"states"} for row in response.json()["rows"])


def test_the_query_selects_no_secret_column_and_is_bounded():
    sql = mobile_delivery.DELIVERY_STATES_SQL
    for column in ("topic", "endpoint", "ack_token", "provider_id", "label", "p256dh", "auth"):
        assert column not in sql
    response, conn = read(lifecycle_rows(), days=14, rows=3)
    body = response.json()
    assert conn.bounded() and conn.asked("make_interval(days => $1)")
    assert body["row_count"] == 3 and body["row_cap"] == 3 and body["truncated"] is True
    assert body["counts_basis"].startswith("the rows shown")


def test_the_window_and_row_bounds_are_enforced():
    for params in ({"days": 0}, {"days": 32}, {"rows": 0}, {"rows": 1001}):
        assert read([], **params)[0].status_code == 422


def test_the_wording_the_page_prints_avoids_retired_execution_words():
    import re

    retired = re.compile(r"\bdemo\b|\bobserve\b|dry[\s_-]?run|\bsimulat\w*", re.IGNORECASE)
    for text in (states.NOTE, *states.DEFINITIONS.values()):
        assert not retired.search(text), text
