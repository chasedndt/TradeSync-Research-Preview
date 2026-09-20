"""state-api answers only to the names its callers use, and to the tunnel hostname on the webhook only (L1)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.host_guard import DEFAULT_HOSTS, HOSTS_ENV, TUNNEL_HOSTS_ENV, TUNNEL_PATHS, HostGuard, host_name

TUNNEL = "tradesync-pine.chaseintech.com"


def _probe(**guard):
    """A guarded app whose routes record that they ran."""
    reached = []
    inner = FastAPI()

    @inner.api_route("/state/health", methods=["GET", "POST"])
    async def health(request: Request):
        reached.append("health")
        return {"ok": True}

    @inner.post("/webhook/tradingview")
    async def webhook():
        reached.append("webhook")
        return {"ok": True}

    return TestClient(HostGuard(inner, **guard)), reached


@pytest.mark.parametrize(
    "value,name",
    [
        ("127.0.0.1:8000", "127.0.0.1"),
        ("LOCALHOST:3000", "localhost"),
        ("state-api:8000", "state-api"),
        ("localhost.", "localhost"),
        ("[::1]:8000", "[::1]"),
        ("localhost:3000:1", "localhost:3000:1"),
        ("", ""),
    ],
)
def test_host_names_are_read_without_port_case_or_trailing_dot(value, name) -> None:
    assert host_name(value) == name


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "127.0.0.1:3000", "localhost:3000", "localhost:8000", "state-api:8000"])
def test_the_names_every_caller_uses_are_served(host) -> None:
    client, reached = _probe(allowed_hosts=[], tunnel_hosts=[])
    assert client.get("/state/health", headers={"Host": host}).status_code == 200
    assert client.post("/state/health", headers={"Host": host}).status_code == 200
    assert reached == ["health", "health"]


@pytest.mark.parametrize(
    "host", ["rebind.example", "127.0.0.1.nip.io:8000", "state-api.rebind.example", "[::1]:8000", "localhost:3000:1", TUNNEL]
)
def test_any_other_host_is_refused_before_routing(host) -> None:
    client, reached = _probe(allowed_hosts=[], tunnel_hosts=[TUNNEL])
    response = client.get("/state/health", headers={"Host": host})
    assert response.status_code == 400 and response.json()["authority"] == "none"
    assert reached == []


def test_the_tunnel_hostname_is_served_on_the_webhook_path_only() -> None:
    client, reached = _probe(allowed_hosts=[], tunnel_hosts=[f"{TUNNEL.upper()}:443"])
    assert TUNNEL_PATHS == frozenset({"/webhook/tradingview"})
    assert client.post("/webhook/tradingview", headers={"Host": TUNNEL}).status_code == 200
    assert client.post("/state/health", headers={"Host": TUNNEL}).status_code == 400
    assert client.post("/webhook/tradingview/", headers={"Host": TUNNEL}).status_code == 400
    assert reached == ["webhook"]


def test_without_a_tunnel_host_configured_the_webhook_needs_a_local_name() -> None:
    client, reached = _probe(allowed_hosts=[], tunnel_hosts=[])
    assert client.post("/webhook/tradingview", headers={"Host": TUNNEL}).status_code == 400
    assert client.post("/webhook/tradingview", headers={"Host": "127.0.0.1:8000"}).status_code == 200
    assert reached == ["webhook"]


def test_names_come_from_configuration(monkeypatch) -> None:
    monkeypatch.setenv(HOSTS_ENV, " Studio.Local:5173 , ")
    monkeypatch.setenv(TUNNEL_HOSTS_ENV, TUNNEL)
    guard = HostGuard(FastAPI())
    assert guard.allowed_hosts == frozenset({*DEFAULT_HOSTS, "studio.local"})
    assert guard.tunnel_hosts == frozenset({TUNNEL})
    assert guard.enforced


def test_a_wildcard_switches_the_check_off_as_a_rollback_lever() -> None:
    client, reached = _probe(allowed_hosts=["*"], tunnel_hosts=["*"])
    assert client.get("/state/health", headers={"Host": "rebind.example"}).status_code == 200
    assert reached == ["health"]


def test_a_refusal_is_logged_with_the_host_it_refused(caplog) -> None:
    client, _ = _probe(allowed_hosts=[], tunnel_hosts=[])
    with caplog.at_level(logging.WARNING, logger="state-api"):
        client.get("/state/health", headers={"Host": "rebind.example:8000"})
    assert "host refused: 'rebind.example:8000' for '/state/health'" in caplog.text


def test_lifespan_passes_through() -> None:
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(HostGuard(inner, allowed_hosts=[], tunnel_hosts=[])({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_the_deployed_entry_point_checks_the_host_before_anything_else() -> None:
    from app import asgi

    assert isinstance(asgi.app, HostGuard)
