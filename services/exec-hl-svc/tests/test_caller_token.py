"""The order route answers only state-api's caller token, before anything else runs (finding L6)."""

from __future__ import annotations

import importlib
import os

from fastapi.testclient import TestClient

from tradesync_core.service_tokens import EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER

TOKEN = "e" * 40
ORDER = {"symbol": "BTC-PERP", "side": "buy", "size_usd": 50, "venue": "hyperliquid"}


def load(token: str | None = TOKEN):
    """Import the service with the gate shut, as it always runs, and the given caller token."""
    for key in (EXEC_TOKEN_ENV, "EXECUTION_ENABLED", "DRY_RUN"):
        os.environ.pop(key, None)
    os.environ.update({"EXECUTION_ENABLED": "false", "DRY_RUN": "true"})
    if token is not None:
        os.environ[EXEC_TOKEN_ENV] = token
    import app.main as main

    return importlib.reload(main)


def test_an_order_without_the_caller_token_is_refused_before_it_is_read() -> None:
    client = TestClient(load().app)
    assert client.post("/exec/hl/order", json=ORDER).status_code == 401
    # Not 422: a caller without the token learns nothing about the order format.
    assert client.post("/exec/hl/order", content=b"{not json").status_code == 401
    wrong = client.post("/exec/hl/order", json=ORDER, headers={EXEC_TOKEN_HEADER: "w" * 40})
    assert wrong.status_code == 401 and EXEC_TOKEN_HEADER in wrong.json()["detail"]


def test_with_the_token_the_order_reaches_the_closed_execution_gate() -> None:
    response = TestClient(load().app).post("/exec/hl/order", json=ORDER, headers={EXEC_TOKEN_HEADER: TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False and body["status"] == "rejected"
    assert body["error"]["code"] == "EXEC_DISABLED" and body["execution_enabled"] is False


def test_with_no_token_configured_every_order_is_refused() -> None:
    client = TestClient(load(token=None).app)
    response = client.post("/exec/hl/order", json=ORDER, headers={EXEC_TOKEN_HEADER: TOKEN})
    assert response.status_code == 503 and EXEC_TOKEN_ENV in response.json()["detail"]
    assert client.get("/healthz").json()["caller_token"] == "disabled"


def test_reads_stay_open_and_never_show_the_token() -> None:
    client = TestClient(load().app)
    health = client.get("/healthz")
    assert health.status_code == 200 and health.json()["caller_token"] == "required"
    assert TOKEN not in health.text
