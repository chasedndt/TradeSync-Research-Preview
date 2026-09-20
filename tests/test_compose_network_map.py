"""Which services left the default-only layout, and exactly which networks each joined.

Every other service stays on the compose default network alone. A change to
this map should be a deliberate edit to this test, with the reason in the
security review: docs/security/2026-09-15_local-access-review.md (M3, M4).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _compose_stack import networks_of, stack  # noqa: E402

JOINED = {
    "state-api": {"default", "pine-ingress", "signer"},
    "exec-hl-svc": {"default", "signer"},
    "cloudflared": {"pine-ingress", "pine-egress"},
    "signer-svc": {"signer"},
}


def test_every_service_joins_exactly_the_networks_it_should() -> None:
    services, _ = stack()
    assert set(JOINED) <= set(services)
    for name, body in services.items():
        assert networks_of(body) == JOINED.get(name, {"default"}), name
