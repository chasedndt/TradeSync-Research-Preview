"""How exec-hl-svc asks the isolated signer for a signature: with its caller token, or not at all.

signer-svc refuses ``POST /sign`` from any caller not presenting
``SIGNER_CALLER_TOKEN`` (finding M4). This is the one sanctioned path from this
service to the signer. Without the token it makes no request at all rather than
arriving unauthenticated, and it ignores proxy variables, so the token goes
nowhere but the signer.

Nothing calls it yet. Real execution is not implemented, the order route fails
closed while EXECUTION_ENABLED is false, and the signer holds no key. It exists
so the caller half of the boundary is built and tested before either is needed.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

import httpx

from tradesync_core.service_tokens import SIGNER_TOKEN_ENV, SIGNER_TOKEN_HEADER, caller_headers

SIGNER_URL = os.getenv("SIGNER_URL", "http://signer-svc:8006").rstrip("/")
SIGN_TIMEOUT_S = 5.0


class SignerCallRefused(RuntimeError):
    """Raised, before any request is made, when this service holds no signer caller token."""


async def request_signature(
    signing_request: Mapping[str, Any],
    *,
    signer_url: str = SIGNER_URL,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.Response:
    """POST one signing request with the caller token and return the signer's answer for the caller to judge."""
    headers = caller_headers(SIGNER_TOKEN_ENV, SIGNER_TOKEN_HEADER, environ)
    if not headers:
        raise SignerCallRefused(f"{SIGNER_TOKEN_ENV} is not set; exec-hl-svc does not call the signer without it")
    async with httpx.AsyncClient(trust_env=False, transport=transport, timeout=SIGN_TIMEOUT_S) as client:
        return await client.post(f"{signer_url.rstrip('/')}/sign", json=dict(signing_request), headers=headers)
