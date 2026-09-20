"""What /actions/execute records for an order the execution boundary answered.

The venue's order id is the venue's to format: paper mode answers "sim_hl_..."
and Hyperliquid answers numbers, and neither is a UUID. Used as the key of the
uuid ``exec_orders.id`` column it failed every insert, so no order was ever
recorded, the caller was told the order failed with ``dry_run`` false, and a
retry found no order for the decision and reached the venue a second time.
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app, state

DECISION = {
    "id": "a4a43722-c0b4-4082-b640-4f8d6ec0b4d3",
    "opportunity_id": "e37f4127-df8e-4688-b337-2234fe4487ec",
    "venue": "hyperliquid",
    "requested": json.dumps({"size_usd": 50.0, "symbol": "BTC"}),
    "risk": json.dumps({"allowed": True}),
    "symbol": "BTC",
    "opp_status": "previewed",
    "quality": 100.0,
    "dir": "long",
    "expires_at": "2030-01-01T00:00:00+00:00",
}


def _execute(monkeypatch, venue_order_id, insert_error=None):
    """Send one confirmed decision through the route; return the response and the recording connection."""
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("DRY_RUN", "true")
    conn = AsyncMock()
    conn.fetchrow.side_effect = [None, DECISION, {"symbol": "BTC", "bias": 0.5}]
    if insert_error is not None:
        conn.execute.side_effect = insert_error
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    # The shared state object's pool, which the route reads wherever it is registered.
    with patch.object(state, "pool", pool), patch("httpx.AsyncClient.post", new_callable=AsyncMock) as venue:
        venue.return_value.status_code = 200
        venue.return_value.json = MagicMock(return_value={
            "ok": True, "venue": "hyperliquid", "dry_run": True, "execution_enabled": True, "status": "placed",
            "order_id": venue_order_id, "idempotency_key": DECISION["id"], "request_payload": {"size_usd": 50.0},
            "response_payload": {}, "error": None, "ts": "2026-09-16T12:00:00Z",
        })
        response = TestClient(app).post("/actions/execute", json={"decision_id": DECISION["id"], "confirm": True})
    return response, conn


def _order_insert(conn):
    inserts = [c for c in conn.execute.call_args_list if "INSERT INTO exec_orders" in c.args[0]]
    assert len(inserts) == 1
    return inserts[0].args


def test_a_simulated_order_id_is_kept_as_the_txid_and_never_used_as_the_row_key(monkeypatch):
    response, conn = _execute(monkeypatch, "sim_hl_00112233aabbccdd")

    assert response.status_code == 200
    assert response.json()["status"] == "placed"
    assert response.json()["order_id"] == "sim_hl_00112233aabbccdd"
    args = _order_insert(conn)
    row_id, txid = args[1], args[8]
    assert str(uuid.UUID(row_id)) == row_id
    assert txid == "sim_hl_00112233aabbccdd"


def test_a_numeric_venue_order_id_is_kept_as_the_txid(monkeypatch):
    _, conn = _execute(monkeypatch, "91234567890")

    args = _order_insert(conn)
    assert str(uuid.UUID(args[1])) == args[1]
    assert args[8] == "91234567890"


def test_every_order_record_gets_its_own_key(monkeypatch):
    _, first = _execute(monkeypatch, "sim_hl_1")
    _, second = _execute(monkeypatch, "sim_hl_1")

    assert _order_insert(first)[1] != _order_insert(second)[1]


def test_a_failure_after_the_venue_answered_reports_the_configured_mode_not_live(monkeypatch):
    response, _ = _execute(monkeypatch, "sim_hl_1", insert_error=RuntimeError("database said something private"))

    body = response.json()
    assert body["status"] == "error"
    assert body["dry_run"] is True
    assert body["execution_enabled"] is True
    assert "something private" not in json.dumps(body)
