"""Tokens one TradeSync service presents to another at the execution boundary.

Two calls cross into the execution boundary, and neither may rest on network
placement alone:

- state-api calls exec-hl-svc ``POST /exec/hl/order`` with
  ``EXEC_HL_CALLER_TOKEN`` in ``X-Exec-Caller-Token`` (finding L6);
- exec-hl-svc calls signer-svc ``POST /sign`` with ``SIGNER_CALLER_TOKEN`` in
  ``X-Signer-Caller-Token`` (finding M4).

They are separate secrets, so holding one opens nothing at the other boundary:
state-api never holds the signer's token. Unlike state-api's optional operator
token, both fail closed. A receiving service with no token, or one shorter than
32 characters, refuses every call on its guarded paths.

The comparison is constant time over bytes. Nothing here logs, prints or
returns a token; a refusal names the variable and the header, never a value.

``CallerTokenGuard`` is plain ASGI and needs no web framework. It answers before
the request body is read or validated, so a caller without the token learns
nothing about the request format behind it.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from typing import Any, Awaitable, Callable, Iterable, Mapping, MutableMapping

from tradesync_core.state_api_access import MIN_TOKEN_CHARS, token_state

EXEC_TOKEN_ENV = "EXEC_HL_CALLER_TOKEN"
EXEC_TOKEN_HEADER = "X-Exec-Caller-Token"
SIGNER_TOKEN_ENV = "SIGNER_CALLER_TOKEN"
SIGNER_TOKEN_HEADER = "X-Signer-Caller-Token"

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

logger = logging.getLogger("tradesync.caller_token")


def caller_headers(env: str, header: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """What a caller adds to its request: the header with its configured token, or nothing when it has none."""
    token = (os.environ if environ is None else environ).get(env, "").strip()
    return {header: token} if token else {}


def caller_refusal(expected: str, supplied: bytes | None, *, env: str, header: str) -> tuple[int, str] | None:
    """Why a call is refused, or None when the caller presented the configured token."""
    configured = token_state(expected)
    if configured == "disabled":
        return 503, f"{env} is not set on this service, so it refuses every caller."
    if configured == "misconfigured":
        return 503, f"{env} is shorter than {MIN_TOKEN_CHARS} characters, so this service refuses every caller."
    if supplied is None or not hmac.compare_digest(supplied, expected.strip().encode("utf-8")):
        return 401, f"Caller token missing or wrong. Send it in {header}."
    return None


class CallerTokenGuard:
    """ASGI middleware: a request to one of ``paths`` must carry ``header`` equal to the token in ``env``."""

    def __init__(
        self, app: ASGIApp, *, paths: Iterable[str], env: str, header: str, token: str | None = None
    ) -> None:
        self.app = app
        self.paths = frozenset(paths)
        self.env, self.header = env, header
        self._name = header.lower().encode("latin-1")
        # Read once. A token that can change under a running process can be
        # changed by whatever changed it.
        self._token = (os.getenv(env, "") if token is None else token).strip()
        self.token_state = token_state(self._token)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("path") in self.paths:
            supplied = next((value for name, value in scope.get("headers") or () if name == self._name), None)
            refusal = caller_refusal(self._token, supplied, env=self.env, header=self.header)
            if refusal is not None:
                status, detail = refusal
                logger.warning("caller refused: %s %r -> HTTP %s", scope.get("method"), scope.get("path"), status)
                await _send_json(send, status, {"detail": detail, "authority": "none"})
                return
        await self.app(scope, receive, send)


async def _send_json(send: Send, status: int, body: dict[str, Any]) -> None:
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode("ascii"))],
        }
    )
    await send({"type": "http.response.body", "body": payload})
