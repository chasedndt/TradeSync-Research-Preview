"""state-api presents its caller token with every order it routes, and never a token it should not hold (L6)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app, state
from tradesync_core.service_tokens import EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER, SIGNER_TOKEN_ENV, SIGNER_TOKEN_HEADER

TOKEN = "e" * 40
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
REJECTED = {
    "ok": False,
    "venue": "hyperliquid",
    "dry_run": True,
    "execution_enabled": False,
    "status": "rejected",
    "idempotency_key": DECISION["id"],
    "request_payload": {},
    "response_payload": {},
    "error": {"code": "EXEC_DISABLED", "message": "Execution disabled"},
    "ts": "2026-09-15T00:00:00Z",
}


def _route_one_order(monkeypatch, **env):
    """Send one confirmed decision through /actions/execute and return what was posted to exec-hl-svc."""
    for key in (EXEC_TOKEN_ENV, SIGNER_TOKEN_ENV):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # The risk check refuses at the execute phase while the gate is shut, before
    # any venue call. Only this test process sees the value, as in
    # test_exec_routing.py; the venue call itself is a mock.
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    conn = AsyncMock()
    conn.fetchrow.side_effect = [None, DECISION, {"symbol": "BTC", "bias": 0.5}]
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    # The shared state object's pool, which the route reads wherever it is registered.
    with patch.object(state, "pool", pool), patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value.status_code = 200
        post.return_value.json = MagicMock(return_value=REJECTED)
        response = TestClient(app).post("/actions/execute", json={"decision_id": DECISION["id"], "confirm": True})
    assert response.status_code == 200, response.text
    assert post.await_count == 1
    args, kwargs = post.call_args
    assert args[0] == "http://exec-hl-svc:8004/exec/hl/order"
    return kwargs


def test_the_order_carries_the_caller_token_in_its_header(monkeypatch) -> None:
    sent = _route_one_order(monkeypatch, **{EXEC_TOKEN_ENV: TOKEN})
    assert sent["headers"] == {EXEC_TOKEN_HEADER: TOKEN}
    assert TOKEN not in json.dumps(sent["json"])


def test_without_a_token_nothing_is_invented_and_exec_hl_svc_refuses(monkeypatch) -> None:
    assert _route_one_order(monkeypatch)["headers"] == {}


def test_state_api_never_sends_the_signer_token(monkeypatch) -> None:
    sent = _route_one_order(monkeypatch, **{EXEC_TOKEN_ENV: TOKEN, SIGNER_TOKEN_ENV: "s" * 40})
    assert SIGNER_TOKEN_HEADER not in sent["headers"]
