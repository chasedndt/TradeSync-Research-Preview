"""The tunnel connector reaches state-api and Cloudflare, and nothing else in the stack (M3).

cloudflared is the only container with a route in from the internet. Until
15 September it sat on the compose default network with every service,
including Postgres, Redis (no password) and the signer. It now joins two
networks and never default:

- pine-ingress, internal, shared with state-api only: the route the one ingress
  rule uses;
- pine-egress, which nothing else joins: its route out to Cloudflare.

state-api declares pine-ingress in compose.full.yml, the file every profile
uses, so recreating it without compose.ingress.yml keeps the tunnel's route.
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _compose_stack import OPS, environment, load, members, networks_of, stack  # noqa: E402

TUNNEL_NETWORKS = {"pine-ingress", "pine-egress"}


def test_cloudflared_joins_its_two_networks_and_not_default() -> None:
    services, _ = stack()
    assert networks_of(services["cloudflared"]) == TUNNEL_NETWORKS


def test_only_state_api_shares_a_network_with_cloudflared() -> None:
    assert members("pine-ingress") == {"cloudflared", "state-api"}
    assert members("pine-egress") == {"cloudflared"}


def test_the_shared_network_is_internal_and_the_route_out_is_not() -> None:
    _, networks = stack()
    assert networks["pine-ingress"].get("internal") is True
    assert not networks["pine-egress"].get("internal")


def test_state_api_joins_the_tunnel_network_from_the_file_every_profile_uses() -> None:
    full = load("compose.full.yml")
    assert {"default", "pine-ingress"} <= set(full["services"]["state-api"]["networks"])
    assert "pine-ingress" in full["networks"]
    assert "state-api" not in (load("compose.ingress.yml").get("services") or {})


def test_the_one_ingress_rule_resolves_to_state_api_on_the_shared_network() -> None:
    template = yaml.safe_load((OPS / "ingress" / "cloudflared.config.template.yml").read_text(encoding="utf-8"))
    rules = template["ingress"]
    routed = [rule for rule in rules if rule.get("hostname")]
    assert len(routed) == 1
    assert routed[0]["path"] == "^/webhook/tradingview$"
    assert routed[0]["service"] == "http://state-api:8000"
    assert rules[-1] == {"service": "http_status:404"}
    # Docker resolves a service name on the networks both containers join.
    services, _ = stack()
    assert networks_of(services["cloudflared"]) & networks_of(services["state-api"]) == {"pine-ingress"}


def test_the_one_trusted_webhook_peer_is_cloudflareds_fixed_address() -> None:
    """state-api believes CF-Connecting-IP only from this address (finding L2)."""
    services, networks = stack()
    address = ipaddress.ip_address(services["cloudflared"]["networks"]["pine-ingress"]["ipv4_address"])
    [pool] = networks["pine-ingress"]["ipam"]["config"]
    assert address in ipaddress.ip_network(pool["subnet"])
    # Outside the range Docker assigns from, so no other container is given it.
    assert address not in ipaddress.ip_network(pool["ip_range"])
    assert environment("state-api")["TRADINGVIEW_INGRESS_PEERS"] == f"${{TRADINGVIEW_INGRESS_PEERS:-{address}}}"


def test_state_api_serves_the_tunnel_hostname_the_cloudflare_profile_names() -> None:
    """The Host check admits that name on /webhook/tradingview only (finding L1)."""
    profile = (OPS / "ingress" / "TRADESYNC_CLOUDFLARE_PROFILE.md").read_text(encoding="utf-8")
    hostname = re.search(r"\| Public hostname \| `([^`]+)` \|", profile).group(1)
    assert environment("state-api")["STATE_API_TUNNEL_HOSTS"] == f"${{STATE_API_TUNNEL_HOSTS:-{hostname}}}"
