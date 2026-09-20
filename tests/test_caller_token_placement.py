"""Each caller token reaches exactly the two services on either side of its boundary (M4, L6).

EXEC_HL_CALLER_TOKEN: state-api sends it, exec-hl-svc checks it.
SIGNER_CALLER_TOKEN: exec-hl-svc sends it, signer-svc checks it.

No other service is given either, so a compromised state-api, Discord reader
or tunnel connector holds nothing the signer would accept.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _compose_stack import stack  # noqa: E402

from tradesync_core.service_tokens import EXEC_TOKEN_ENV, SIGNER_TOKEN_ENV  # noqa: E402


def _holders(variable: str) -> set[str]:
    services, _ = stack()
    return {name for name, body in services.items() if variable in (body.get("environment") or {})}


def test_the_exec_token_is_held_by_state_api_and_exec_hl_svc_only() -> None:
    assert _holders(EXEC_TOKEN_ENV) == {"state-api", "exec-hl-svc"}


def test_the_signer_token_is_held_by_exec_hl_svc_and_the_signer_only() -> None:
    assert _holders(SIGNER_TOKEN_ENV) == {"exec-hl-svc", "signer-svc"}


def test_both_come_from_runtime_env_with_no_default_value() -> None:
    services, _ = stack()
    for variable in (EXEC_TOKEN_ENV, SIGNER_TOKEN_ENV):
        for name in _holders(variable):
            assert services[name]["environment"][variable] == f"${{{variable}:-}}", (name, variable)
