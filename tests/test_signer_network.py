"""The signer is reachable from exec-hl-svc and state-api only, and has no route out (M4).

signer-svc shared the compose default network with every service, the
internet-facing cloudflared and the Discord reader among them, and checked no
caller. It now joins one internal network, signer, with exec-hl-svc (the one
caller that may ask for signatures) and state-api (which reads its status). The
caller token, tradesync_core.service_tokens, decides which of those may sign;
state-api never holds it.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _compose_stack import environment, load, members, networks_of, stack  # noqa: E402

from tradesync_core.service_tokens import SIGNER_TOKEN_ENV  # noqa: E402


def test_the_signer_joins_only_its_internal_network() -> None:
    services, networks = stack()
    assert networks_of(services["signer-svc"]) == {"signer"}
    assert networks["signer"].get("internal") is True


def test_only_its_caller_and_its_status_reader_share_that_network() -> None:
    assert members("signer") == {"signer-svc", "exec-hl-svc", "state-api"}
    services, _ = stack()
    signer = networks_of(services["signer-svc"])
    for other in ("cloudflared", "discord-reader", "redis", "postgres", "cockpit-ui", "core-scorer"):
        assert not signer & networks_of(services[other]), other


def test_the_memberships_live_in_the_file_every_profile_uses() -> None:
    full = load("compose.full.yml")
    assert "signer" in full["networks"]
    assert "signer" in full["services"]["state-api"]["networks"]
    assert "signer" in full["services"]["exec-hl-svc"]["networks"]


def test_the_signer_reads_its_caller_token_and_state_api_never_holds_it() -> None:
    assert SIGNER_TOKEN_ENV in environment("signer-svc")
    for service in ("state-api", "core-scorer", "discord-reader", "cloudflared"):
        assert SIGNER_TOKEN_ENV not in environment(service), service
