"""The webhook refuses any source but TradingView, and believes CF-Connecting-IP only from the tunnel (L2)."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main, webhook_source
from app.webhook_source import CHECK_ENV, HOSTS_ENV, PEERS_ENV, check_enforced, configured_hosts, configured_peers
from tradesync_core.tradingview_webhook import TRADINGVIEW_SOURCE_IPS

TUNNEL = "172.29.53.10"
TRADINGVIEW = TRADINGVIEW_SOURCE_IPS[0]
WEBHOOK = "/webhook/tradingview"


def _from(peer: str):
    """A client whose requests arrive from ``peer``, as uvicorn reports the socket's address."""

    async def app(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "client": (peer, 40000)}
        await main.app(scope, receive, send)

    return TestClient(app)


@pytest.fixture(autouse=True)
def tunnel_configured():
    with patch.object(webhook_source, "TUNNEL_PEERS", frozenset({TUNNEL})), patch.object(
        webhook_source, "TUNNEL_HOSTS", ()
    ), patch.object(webhook_source, "ENFORCED", True), patch.object(main, "TRADINGVIEW_WEBHOOK_SECRET", ""):
        yield


def _post(peer: str, **headers):
    return _from(peer).post(WEBHOOK, content=b'{"secret": "x"}', headers=headers)


def test_a_tradingview_alert_through_the_tunnel_passes_the_source_check() -> None:
    # The next check answers: the secret is unset in this test, so the route says so.
    response = _post(TUNNEL, **{"CF-Connecting-IP": TRADINGVIEW})
    assert response.status_code == 503 and "TRADINGVIEW_WEBHOOK_SECRET" in response.json()["detail"]


@pytest.mark.parametrize(
    "peer,headers",
    [
        (TUNNEL, {"CF-Connecting-IP": "203.0.113.7"}),
        (TUNNEL, {}),
        (TUNNEL, {"CF-Connecting-IP": f"{TRADINGVIEW}, 203.0.113.7"}),
        ("172.18.0.1", {"CF-Connecting-IP": TRADINGVIEW}),
        ("172.29.53.1", {"CF-Connecting-IP": TRADINGVIEW}),
        ("127.0.0.1", {"X-Forwarded-For": TRADINGVIEW}),
        ("testclient", {"CF-Connecting-IP": TRADINGVIEW}),
    ],
)
def test_every_other_source_is_refused_before_anything_else(peer, headers) -> None:
    response = _post(peer, **headers)
    assert response.status_code == 403
    assert response.json() == webhook_source.REFUSAL


def test_the_refusal_comes_before_the_secret_the_database_and_the_body() -> None:
    with patch.object(main, "TRADINGVIEW_WEBHOOK_SECRET", "configured-secret"), patch.object(main.state, "pool", None):
        refused = _from("172.18.0.1").post(WEBHOOK, content=b"not even json")
    assert refused.status_code == 403


def test_a_source_that_passes_reaches_the_body_secret_check() -> None:
    body = json.dumps({"secret": "wrong", "indicator": "x", "ticker": "BTCUSD"}).encode()
    with patch.object(main, "TRADINGVIEW_WEBHOOK_SECRET", "configured-secret"), patch.object(main.state, "pool", object()):
        response = _from(TUNNEL).post(WEBHOOK, content=body, headers={"CF-Connecting-IP": TRADINGVIEW})
    assert response.status_code == 401
    assert "bad_secret" in [reason["code"] for reason in response.json()["reasons"]]


def test_the_rollback_lever_lets_any_source_through_to_the_secret_check() -> None:
    with patch.object(webhook_source, "ENFORCED", False):
        assert _post("172.18.0.1").status_code == 503


def test_a_refusal_is_logged_with_the_source_and_route_but_no_body(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="state-api"):
        _from(TUNNEL).post(WEBHOOK, content=b'{"secret": "do-not-log"}', headers={"CF-Connecting-IP": "203.0.113.7"})
    assert "tradingview alert refused: source 203.0.113.7 via tunnel" in caplog.text
    assert "do-not-log" not in caplog.text


def test_configuration_is_parsed_strictly() -> None:
    assert configured_peers({PEERS_ENV: f" {TUNNEL} , junk, ::ffff:172.29.53.11,"}) == {TUNNEL, "172.29.53.11"}
    assert configured_peers({}) == frozenset()
    assert check_enforced({}) is True
    assert check_enforced({CHECK_ENV: " OFF "}) is False
    assert check_enforced({CHECK_ENV: "no"}) is True
    assert configured_hosts({HOSTS_ENV: " cloudflared , ,tradesync-full-cloudflared-1"}) == ("cloudflared", "tradesync-full-cloudflared-1")
    assert configured_hosts({}) == ()


# --- the connector by name ----------------------------------------------------
#
# A connector created before it moved to pine-ingress sits on the shared network
# at an address Docker assigned. Believed only at the fixed address, every alert
# it forwarded was refused.

SHARED_NETWORK_CONNECTOR = "172.18.0.9"


def _resolving(names: dict[str, list[str]]):
    async def lookup(host: str) -> list[str]:
        if host not in names:
            raise OSError(f"{host} does not resolve")
        return names[host]

    return patch.object(webhook_source, "_addresses", lookup)


def test_the_connector_is_recognised_by_name_wherever_docker_placed_it() -> None:
    with patch.object(webhook_source, "TUNNEL_HOSTS", ("cloudflared",)), _resolving({"cloudflared": [SHARED_NETWORK_CONNECTOR]}):
        response = _post(SHARED_NETWORK_CONNECTOR, **{"CF-Connecting-IP": TRADINGVIEW})
    assert response.status_code == 503 and "TRADINGVIEW_WEBHOOK_SECRET" in response.json()["detail"]


def test_a_named_connector_still_forwards_only_tradingview(caplog) -> None:
    with patch.object(webhook_source, "TUNNEL_HOSTS", ("cloudflared",)), _resolving({"cloudflared": [SHARED_NETWORK_CONNECTOR]}):
        with caplog.at_level(logging.WARNING, logger="state-api"):
            response = _post(SHARED_NETWORK_CONNECTOR, **{"CF-Connecting-IP": "203.0.113.7"})
    assert response.status_code == 403
    assert "source 203.0.113.7 via tunnel" in caplog.text


def test_another_container_on_the_shared_network_is_judged_by_its_own_address() -> None:
    with patch.object(webhook_source, "TUNNEL_HOSTS", ("cloudflared",)), _resolving({"cloudflared": [SHARED_NETWORK_CONNECTOR]}):
        response = _post("172.18.0.5", **{"CF-Connecting-IP": TRADINGVIEW})
    assert response.status_code == 403


def test_a_connector_name_that_does_not_resolve_adds_no_peer() -> None:
    with patch.object(webhook_source, "TUNNEL_HOSTS", ("cloudflared",)), _resolving({}):
        response = _post(SHARED_NETWORK_CONNECTOR, **{"CF-Connecting-IP": TRADINGVIEW})
    assert response.status_code == 403


def test_the_fixed_address_needs_no_lookup() -> None:
    async def never(host: str) -> list[str]:
        raise AssertionError("the fixed pine-ingress address must not wait on a lookup")

    with patch.object(webhook_source, "TUNNEL_HOSTS", ("cloudflared",)), patch.object(webhook_source, "_addresses", never):
        response = _post(TUNNEL, **{"CF-Connecting-IP": TRADINGVIEW})
    assert response.status_code == 503
