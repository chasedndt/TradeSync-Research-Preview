"""A server error answers with a trace id and logs the exception's type; deliberate details pass unchanged (L4)."""

from __future__ import annotations

import json
import logging
import re
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import agent_connector, feed_routes, harness_gate, main
from app.error_responses import GENERIC_DETAIL, install, sanitising_http_exception_handler

# Shaped like the texts these handlers used to return: an internal address and a user name.
RAW = 'connection to server at "postgres" (172.18.0.8), port 5432 failed: password authentication failed for user "tradesync"'
HEX_ID = re.compile(r"[0-9a-f]{32}")


def _probe() -> TestClient:
    app = FastAPI()
    install(app)

    @app.get("/raw")
    async def raw():
        try:
            raise RuntimeError(RAW)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/raw-from")
    async def raw_from():
        try:
            raise ValueError(RAW)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/composed")
    async def composed():
        try:
            raise RuntimeError(RAW)
        except RuntimeError:
            raise HTTPException(status_code=500, detail="the catalog is missing; rebuild the image")

    @app.get("/client-error")
    async def client_error():
        try:
            raise ValueError("Unsupported venue: binance")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.get("/unavailable")
    async def unavailable():
        try:
            raise LookupError("paper limits row missing")
        except LookupError as exc:
            raise HTTPException(503, str(exc)) from None

    return TestClient(app)


def test_a_500_that_repeats_exception_text_answers_generically_and_logs_only_the_type(caplog) -> None:
    client = _probe()
    with caplog.at_level(logging.ERROR, logger="state-api"):
        responses = [client.get("/raw"), client.get("/raw-from")]
    for response in responses:
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == GENERIC_DETAIL and HEX_ID.fullmatch(body["trace_id"])
        assert RAW not in response.text and "postgres" not in response.text
    assert "GET /raw failed: RuntimeError" in caplog.text and "GET /raw-from failed: ValueError" in caplog.text
    assert RAW not in caplog.text
    assert {record.trace_id for record in caplog.records} == {r.json()["trace_id"] for r in responses}


def test_composed_500_details_and_deliberate_4xx_and_503_details_pass_unchanged() -> None:
    client = _probe()
    assert client.get("/composed").json() == {"detail": "the catalog is missing; rebuild the image"}
    assert client.get("/client-error").json() == {"detail": "Unsupported venue: binance"}
    unavailable = client.get("/unavailable")
    assert unavailable.status_code == 503 and unavailable.json() == {"detail": "paper limits row missing"}


def test_the_real_app_answers_with_the_request_trace_id() -> None:
    assert main.app.exception_handlers[StarletteHTTPException] is sanitising_http_exception_handler
    failing = MagicMock()
    failing.acquire.side_effect = RuntimeError(RAW)
    client = TestClient(main.app)
    with patch.object(main.state, "pool", failing):
        listed = client.get("/state/quarantine", headers={"X-Trace-Id": "trace-abc-123"})
        drawings = client.get("/state/canvas/drawings?symbol=BTC-PERP&interval=1h", headers={"X-Trace-Id": "x y"})
    assert listed.status_code == 500
    assert listed.json() == {"detail": GENERIC_DETAIL, "trace_id": "trace-abc-123"}
    assert listed.headers["X-Trace-Id"] == "trace-abc-123"
    # A router's handler goes through the same path; a trace id that is not a plain token is replaced.
    assert drawings.status_code == 500 and drawings.json()["detail"] == GENERIC_DETAIL
    assert HEX_ID.fullmatch(drawings.json()["trace_id"])
    for response in (listed, drawings):
        assert RAW not in response.text


def test_a_market_data_error_names_its_status_but_not_the_internal_address() -> None:
    upstream = httpx.Response(422, request=httpx.Request("GET", "http://market-data:8005/snapshot/hyperliquid/BTC-PERP"))
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=upstream):
        response = TestClient(main.app).get("/state/market/snapshot?venue=hyperliquid&symbol=BTC-PERP")
    assert response.status_code == 422
    assert response.json() == {"detail": "market-data answered HTTP 422"}


def _execute(monkeypatch, *, post=None, fetchrow=None):
    decision = {
        "id": "a4a43722-c0b4-4082-b640-4f8d6ec0b4d3", "opportunity_id": "e37f4127-df8e-4688-b337-2234fe4487ec",
        "venue": "hyperliquid", "requested": json.dumps({"size_usd": 50.0, "symbol": "BTC"}),
        "risk": json.dumps({"allowed": True}), "symbol": "BTC", "opp_status": "previewed", "quality": 100.0,
        "dir": "long", "expires_at": "2030-01-01T00:00:00+00:00",
    }
    monkeypatch.setenv("EXECUTION_ENABLED", "true")  # this test process only; the venue call is a mock
    conn = AsyncMock()
    conn.fetchrow.side_effect = fetchrow or [None, decision, {"symbol": "BTC"}]
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    # The shared state object's pool, which the route reads wherever it is registered.
    with patch.object(main.state, "pool", pool), patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=post):
        return TestClient(main.app).post("/actions/execute", json={"decision_id": decision["id"], "confirm": True})


def test_an_execution_error_quotes_a_reference_instead_of_the_exception(monkeypatch, caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="state-api"):
        venue_down = _execute(monkeypatch, post=httpx.ConnectError(RAW))
        broken = _execute(monkeypatch, fetchrow=RuntimeError(RAW))
    logged = {getattr(record, "trace_id", None) for record in caplog.records}
    for response, kind in ((venue_down, "ConnectError"), (broken, "RuntimeError")):
        assert response.status_code == 200
        message = response.json()["error"]["message"]
        assert kind in message and RAW not in response.text
        assert HEX_ID.search(message).group(0) in logged
    assert RAW not in caplog.text


def test_a_harness_transport_error_names_its_type_but_not_its_text(monkeypatch) -> None:
    with patch.object(agent_connector, "configured", return_value=True), patch.object(
        agent_connector, "ask", AsyncMock(side_effect=httpx.ConnectError(RAW))
    ), patch.object(main.state, "pool", object()), patch.object(
        harness_gate, "refusal", AsyncMock(return_value=None)
    ):
        response = TestClient(main.app).post("/state/agents/harness/ask", json={"intent": "explain", "prompt": "why"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "ConnectError" in detail and RAW not in detail and HEX_ID.search(detail)


def test_market_status_names_the_failure_type_but_not_the_internal_address() -> None:
    failure = httpx.ConnectError("All connection attempts failed: http://market-data:8005/status")
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=failure):
        body = TestClient(main.app).get("/state/market/status").json()
    assert body["status"] == "unavailable" and body["providers"] == []
    assert "market-data:8005" not in json.dumps(body)
    assert "ConnectError" in body["error"] and HEX_ID.search(body["error"])


def test_a_macro_headlines_failure_names_its_type_but_not_its_text() -> None:
    with patch.object(feed_routes.macro_feed, "fetch_headlines", AsyncMock(side_effect=RuntimeError(RAW))):
        body = TestClient(main.app).get("/state/macro/headlines").json()
    assert body["headlines"] == []
    assert "postgres" not in json.dumps(body) and "tradesync" not in json.dumps(body)
    assert body["status"]["error"].startswith("RuntimeError; log reference ") and HEX_ID.search(body["status"]["error"])

