"""exec-hl-svc calls the signer only with its caller token, and only in the header (finding M4)."""

from __future__ import annotations

import asyncio
import inspect
import json

import httpx
import pytest

from app import signer_client
from app.signer_client import SignerCallRefused, request_signature
from tradesync_core.service_tokens import SIGNER_TOKEN_ENV, SIGNER_TOKEN_HEADER

TOKEN = "s" * 40
BODY = {
    "schema_version": "signing_request_v1",
    "payload_digest": "a" * 64,
    "envelope_id": "tce_1",
    "approval_id": "appr_1",
}


def _recording(status: int = 200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"refused": status != 200})

    return httpx.MockTransport(handler), seen


def test_the_signer_is_called_with_the_caller_token_in_its_header() -> None:
    transport, seen = _recording()
    response = asyncio.run(
        request_signature(BODY, signer_url="http://signer-svc:8006/", environ={SIGNER_TOKEN_ENV: TOKEN}, transport=transport)
    )
    assert response.status_code == 200
    [sent] = seen
    assert sent.method == "POST" and str(sent.url) == "http://signer-svc:8006/sign"
    assert sent.headers[SIGNER_TOKEN_HEADER] == TOKEN
    assert json.loads(sent.content) == BODY
    assert TOKEN not in str(sent.url) and TOKEN.encode() not in sent.content


def test_without_the_token_no_request_is_made() -> None:
    transport, seen = _recording()
    with pytest.raises(SignerCallRefused) as refused:
        asyncio.run(request_signature(BODY, environ={}, transport=transport))
    assert seen == []
    assert SIGNER_TOKEN_ENV in str(refused.value)


def test_a_refusal_from_the_signer_is_returned_for_the_caller_to_judge() -> None:
    transport, _ = _recording(status=401)
    response = asyncio.run(request_signature(BODY, environ={SIGNER_TOKEN_ENV: TOKEN}, transport=transport))
    assert response.status_code == 401


def test_proxy_variables_are_ignored_so_the_token_goes_only_to_the_signer() -> None:
    source = inspect.getsource(signer_client.request_signature)
    assert "trust_env=False" in source
