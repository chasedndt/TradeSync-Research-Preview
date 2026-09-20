"""A change's body is refused before routing when it is larger than its path allows (L5)."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import main
from app.body_limit import DEFAULT_MAX_BODY_BYTES, LIMIT_ENV, PATH_LIMITS, BodyLimit, default_limit
from tradesync_core.tradingview_webhook import MAX_BODY_BYTES

MIB = 1024 * 1024


def _probe(**limit):
    """A limited app whose routes record the size of the body they read."""
    received: list[tuple[str, int]] = []
    inner = FastAPI()

    @inner.api_route("/state/change", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def change(request: Request):
        received.append(("change", len(await request.body())))
        return {"ok": True}

    @inner.post("/state/fleet/snapshot")
    async def snapshot(request: Request):
        received.append(("snapshot", len(await request.body())))
        return {"ok": True}

    @inner.post("/webhook/tradingview")
    async def webhook(request: Request):
        received.append(("webhook", len(await request.body())))
        return {"ok": True}

    return TestClient(BodyLimit(inner, **limit)), received


def test_a_change_up_to_the_default_passes_and_one_byte_more_is_refused_before_routing() -> None:
    client, received = _probe()
    for method in ("post", "put", "patch"):
        assert getattr(client, method)("/state/change", content=b"x" * DEFAULT_MAX_BODY_BYTES).status_code == 200
    refused = client.post("/state/change", content=b"x" * (DEFAULT_MAX_BODY_BYTES + 1))
    assert refused.status_code == 413
    assert refused.json()["limit_bytes"] == DEFAULT_MAX_BODY_BYTES
    assert received == [("change", DEFAULT_MAX_BODY_BYTES)] * 3


def test_the_webhook_keeps_its_16_kb_bound() -> None:
    assert PATH_LIMITS["/webhook/tradingview"] == MAX_BODY_BYTES == 16 * 1024
    client, received = _probe()
    assert client.post("/webhook/tradingview", content=b"x" * MAX_BODY_BYTES).status_code == 200
    assert client.post("/webhook/tradingview", content=b"x" * (MAX_BODY_BYTES + 1)).status_code == 413
    assert received == [("webhook", MAX_BODY_BYTES)]


def test_the_measured_bulk_posts_have_explicit_larger_limits() -> None:
    assert PATH_LIMITS["/state/fleet/snapshot"] == PATH_LIMITS["/state/strikezone/ingest"] == 4 * MIB
    client, received = _probe()
    assert client.post("/state/fleet/snapshot", content=b"x" * (2 * MIB)).status_code == 200
    assert client.post("/state/fleet/snapshot", content=b"x" * (4 * MIB + 1)).status_code == 413
    assert received == [("snapshot", 2 * MIB)]


def test_reads_are_not_limited() -> None:
    client, received = _probe(default=10)
    assert client.request("GET", "/state/change", content=b"x" * 100).status_code == 200
    assert received == [("change", 100)]


def test_a_body_without_content_length_is_counted_as_it_arrives() -> None:
    """Chunked bodies declare no size, so the limit is applied to what actually arrives."""
    reached: list[bytes] = []

    async def inner(scope, receive, send):
        message = await receive()
        reached.append(message["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    def run(chunks):
        messages = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
        sent: list[dict] = []

        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/state/change", "headers": [(b"transfer-encoding", b"chunked")]}
        asyncio.run(BodyLimit(inner, default=1000)(scope, receive, send))
        return sent[0]["status"]

    assert run([b"a" * 600, b"b" * 400]) == 200
    assert reached == [b"a" * 600 + b"b" * 400]
    assert run([b"a" * 600, b"b" * 401]) == 413
    assert len(reached) == 1


def test_a_content_length_that_is_not_a_number_is_refused() -> None:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": "/state/change", "headers": [(b"content-length", b"-5")]}
    asyncio.run(BodyLimit(None, default=1000)(scope, receive, send))
    assert sent[0]["status"] == 400


def test_the_default_comes_from_configuration_and_ignores_nonsense() -> None:
    assert default_limit({}) == DEFAULT_MAX_BODY_BYTES == MIB
    assert default_limit({LIMIT_ENV: " 2048 "}) == 2048
    for nonsense in ("0", "-1", "1e6", "lots"):
        assert default_limit({LIMIT_ENV: nonsense}) == DEFAULT_MAX_BODY_BYTES


def test_the_real_routes_refuse_an_oversized_change_before_touching_the_database(caplog) -> None:
    client = TestClient(BodyLimit(main.app))
    body = b'{"source": "chaseos", "payload": {"x": "' + b"y" * DEFAULT_MAX_BODY_BYTES + b'"}}'
    with patch.object(main.state, "pool", None), caplog.at_level(logging.WARNING, logger="state-api"):
        response = client.post("/state/quarantine", content=body, headers={"Content-Type": "application/json"})
    # Without the limit this route would answer 503 for the missing pool.
    assert response.status_code == 413
    assert "body refused: POST '/state/quarantine'" in caplog.text


@pytest.mark.parametrize("path", sorted(PATH_LIMITS))
def test_every_listed_path_is_a_real_change_route(path) -> None:
    routes = {(route.path, method) for route in main.app.routes for method in getattr(route, "methods", ()) or ()}
    assert (path, "POST") in routes


def test_a_tap_acknowledgement_has_the_tightest_limit_of_any_change() -> None:
    assert PATH_LIMITS["/state/mobile-alerts/acknowledgements"] == 1024 == min(PATH_LIMITS.values())
