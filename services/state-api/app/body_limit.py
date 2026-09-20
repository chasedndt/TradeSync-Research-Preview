"""How large a change's request body may be, refused before the route reads it (finding L5).

Only the TradingView webhook bounded its body. Every other change parsed whatever
arrived, and FleetSnapshot and LabIngest take unbounded lists. Since the
loopback bindings only a local caller can send one, but a mistaken or hostile
local process could still hold the API's memory.

A change (POST, PUT, PATCH, DELETE) may carry at most ``DEFAULT_MAX_BODY_BYTES``,
1 MiB, unless its path is listed in ``PATH_LIMITS``. A larger body is refused
with 413 before routing: at once when Content-Length says so, and as it arrives
when it is sent without one. ``STATE_API_MAX_BODY_BYTES`` changes the default,
as a rollback lever; the listed paths keep their own limits.

The listed limits, set from sizes measured read-only on 15 September 2026:

- ``/webhook/tradingview``: 16 KB, the receiver's own bound
  (``tradesync_core.tradingview_webhook.MAX_BODY_BYTES``).
- ``/state/fleet/snapshot``: 4 MiB. The fleet bridge posts every job, up to
  1,500 runs and up to 2,000 usage rows. The stored rows came to about 650 KB
  (jobs 82 KB, the newest 1,500 runs 473 KB, 321 usage rows 94 KB); a full
  usage tail adds about half a megabyte.
- ``/state/strikezone/ingest``: 4 MiB. The route takes up to 2,000 rows a post
  (``MAX_ROWS_PER_POST``); the quant bridge sends 500, measured at 281 KB of
  signals and 350 KB of outcomes, and 72 KB of documents.
- ``/state/mobile-alerts/acknowledgements``: 1 KiB, far below the default. The
  body is one 43-character token, and like the webhook it does not need the
  operator token (app/access_guard.py), so it gets the tightest limit.

Nothing else needs more than the default: the largest stored quarantine payload
was 49 KB, and quarantine itself refuses payloads over 64 KB.
"""

from __future__ import annotations

import logging
import os
from typing import Mapping

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.mobile_tap_ack import MAX_BODY_BYTES as TAP_ACKNOWLEDGEMENT_MAX_BODY_BYTES
from app.mobile_tap_ack import PATH as TAP_ACKNOWLEDGEMENT_PATH
from tradesync_core.tradingview_webhook import MAX_BODY_BYTES as WEBHOOK_MAX_BODY_BYTES

logger = logging.getLogger("state-api")

LIMIT_ENV = "STATE_API_MAX_BODY_BYTES"
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
LIMITED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
PATH_LIMITS: Mapping[str, int] = {
    "/webhook/tradingview": WEBHOOK_MAX_BODY_BYTES,
    "/state/fleet/snapshot": 4 * 1024 * 1024,
    "/state/strikezone/ingest": 4 * 1024 * 1024,
    TAP_ACKNOWLEDGEMENT_PATH: TAP_ACKNOWLEDGEMENT_MAX_BODY_BYTES,
}


def default_limit(environ: Mapping[str, str] | None = None) -> int:
    """``STATE_API_MAX_BODY_BYTES`` when it is a positive whole number of bytes, otherwise 1 MiB."""
    raw = (os.environ if environ is None else environ).get(LIMIT_ENV, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_MAX_BODY_BYTES


class BodyLimit:
    """ASGI middleware: a change whose body exceeds its path's limit is refused before routing."""

    def __init__(self, app: ASGIApp, *, default: int | None = None) -> None:
        self.app = app
        self.default = default_limit() if default is None else default

    def limit_for(self, path: str) -> int:
        return PATH_LIMITS.get(path, self.default)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"].upper() not in LIMITED_METHODS:
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope.get("path", ""))
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            if not declared.strip().isdigit():
                await self._refuse(scope, receive, send, 400, "Content-Length is not a byte count.", limit)
            elif int(declared) > limit:
                await self._refuse(scope, receive, send, 413, self._too_large(limit), limit)
            else:
                await self.app(scope, receive, send)
            return
        # No Content-Length: the size is unknown until the body has arrived. Read
        # it here, up to the limit, and give the route exactly what arrived.
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return  # the client went away before sending the whole body
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await self._refuse(scope, receive, send, 413, self._too_large(limit), limit)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        pending: list[Message] = [{"type": "http.request", "body": b"".join(chunks), "more_body": False}]

        async def replay() -> Message:
            return pending.pop() if pending else await receive()

        await self.app(scope, replay, send)

    @staticmethod
    def _too_large(limit: int) -> str:
        return f"Request body over {limit} bytes for this path; refused before the route ran."

    async def _refuse(self, scope: Scope, receive: Receive, send: Send, status: int, detail: str, limit: int) -> None:
        logger.warning("body refused: %s %r (limit %s bytes) -> HTTP %s", scope["method"], scope.get("path"), limit, status)
        response = JSONResponse({"detail": detail, "limit_bytes": limit, "authority": "none"}, status_code=status)
        await response(scope, receive, send)
