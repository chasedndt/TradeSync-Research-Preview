"""Service-to-service caller tokens fail closed and travel only in their own header."""

from __future__ import annotations

import asyncio
import logging

import pytest
from starlette.testclient import TestClient

from tradesync_core.service_tokens import (
    EXEC_TOKEN_ENV,
    EXEC_TOKEN_HEADER,
    SIGNER_TOKEN_ENV,
    SIGNER_TOKEN_HEADER,
    CallerTokenGuard,
    caller_headers,
    caller_refusal,
)
from tradesync_core.state_api_access import MIN_TOKEN_CHARS, TOKEN_ENV

TOKEN = "c" * MIN_TOKEN_CHARS


def _guarded(token: str | None):
    """A signer-shaped app behind the guard, recording which paths its routes reached."""
    reached: list[str] = []

    async def inner(scope, receive, send):
        if scope["type"] != "http":
            reached.append(scope["type"])
            return
        reached.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"reached"})

    guard = CallerTokenGuard(inner, paths={"/sign"}, env=SIGNER_TOKEN_ENV, header=SIGNER_TOKEN_HEADER, token=token)
    return TestClient(guard), guard, reached


def test_each_boundary_has_its_own_variable_and_header() -> None:
    assert len({EXEC_TOKEN_ENV, SIGNER_TOKEN_ENV, TOKEN_ENV}) == 3
    assert EXEC_TOKEN_HEADER != SIGNER_TOKEN_HEADER


def test_a_caller_sends_the_header_only_when_it_holds_a_token() -> None:
    assert caller_headers(EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER, {}) == {}
    assert caller_headers(EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER, {EXEC_TOKEN_ENV: "  "}) == {}
    assert caller_headers(EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER, {EXEC_TOKEN_ENV: f" {TOKEN} "}) == {EXEC_TOKEN_HEADER: TOKEN}
    # The signer's token is not the exec token: holding one sends nothing for the other.
    assert caller_headers(SIGNER_TOKEN_ENV, SIGNER_TOKEN_HEADER, {EXEC_TOKEN_ENV: TOKEN}) == {}


@pytest.mark.parametrize("expected", ["", "   ", "c" * (MIN_TOKEN_CHARS - 1)])
def test_an_unset_or_short_token_refuses_every_caller(expected: str) -> None:
    status, detail = caller_refusal(expected, TOKEN.encode(), env=SIGNER_TOKEN_ENV, header=SIGNER_TOKEN_HEADER)
    assert status == 503 and SIGNER_TOKEN_ENV in detail


def test_only_the_configured_token_passes() -> None:
    def check(supplied):
        return caller_refusal(TOKEN, supplied, env=EXEC_TOKEN_ENV, header=EXEC_TOKEN_HEADER)

    assert check(None)[0] == 401
    assert check(b"")[0] == 401
    assert check(TOKEN[:-1].encode())[0] == 401
    assert check((TOKEN + "c").encode())[0] == 401
    assert check("é".encode("latin-1") * MIN_TOKEN_CHARS)[0] == 401
    assert check(TOKEN.encode()) is None
    assert EXEC_TOKEN_HEADER in check(None)[1]


def test_the_guard_refuses_before_the_route_runs_and_leaves_other_paths_alone() -> None:
    client, guard, reached = _guarded(TOKEN)
    assert guard.token_state == "required"
    assert client.post("/sign", content=b"{not json").status_code == 401
    assert client.post("/sign", headers={SIGNER_TOKEN_HEADER: "w" * MIN_TOKEN_CHARS}).status_code == 401
    assert client.get("/sign").status_code == 401
    assert reached == []
    assert client.get("/signer/status").status_code == 200
    assert client.post("/sign", headers={SIGNER_TOKEN_HEADER.lower(): TOKEN}).status_code == 200
    assert reached == ["/signer/status", "/sign"]


def test_with_no_token_configured_the_guarded_path_is_closed() -> None:
    client, guard, reached = _guarded("")
    assert guard.token_state == "disabled"
    response = client.post("/sign", headers={SIGNER_TOKEN_HEADER: TOKEN})
    assert response.status_code == 503
    assert response.json() == {
        "detail": f"{SIGNER_TOKEN_ENV} is not set on this service, so it refuses every caller.",
        "authority": "none",
    }
    assert reached == []


def test_the_token_is_read_from_the_environment_once(monkeypatch) -> None:
    monkeypatch.setenv(SIGNER_TOKEN_ENV, TOKEN)
    guard = CallerTokenGuard(None, paths={"/sign"}, env=SIGNER_TOKEN_ENV, header=SIGNER_TOKEN_HEADER)
    monkeypatch.setenv(SIGNER_TOKEN_ENV, "")
    assert guard.token_state == "required"


def test_a_refusal_never_carries_or_logs_a_token_value(caplog) -> None:
    client, _, _ = _guarded(TOKEN)
    wrong = "w" * (MIN_TOKEN_CHARS + 4)
    with caplog.at_level(logging.WARNING, logger="tradesync.caller_token"):
        response = client.post("/sign", headers={SIGNER_TOKEN_HEADER: wrong})
    assert "caller refused: POST '/sign' -> HTTP 401" in caplog.text
    for text in (response.text, caplog.text):
        assert TOKEN not in text and wrong not in text


def test_lifespan_passes_through() -> None:
    _, guard, reached = _guarded(TOKEN)
    asyncio.run(guard({"type": "lifespan"}, None, None))
    assert reached == ["lifespan"]
