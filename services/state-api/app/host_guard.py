"""Which Host names state-api answers to, checked before anything else runs (finding L1).

A web page can have the browser resolve its own hostname to 127.0.0.1 (DNS
rebinding). The page is then same-origin with itself while it talks to this API,
so it could read every GET: paper positions, job descriptions, quarantine
payloads, the watched wallet address. The origin check in access_guard.py
refuses its changes but cannot stop reads. The browser still sends the page's
own hostname in ``Host``, and that is what this checks.

Every path answers to ``127.0.0.1``, ``localhost`` and ``state-api``. The host
bridges and Docker healthchecks use the first two, the containers use the
compose service name, and the Cockpit's nginx forwards the browser's own Host
(127.0.0.1 or localhost). ``STATE_API_ALLOWED_HOSTS`` adds names,
comma-separated; ``*`` switches the check off, as a rollback lever.

``/webhook/tradingview`` alone also answers to ``STATE_API_TUNNEL_HOSTS``, the
tunnel's public hostname, which cloudflared sends as Host. Every other path
under that name is refused, so a change to the tunnel's routing cannot publish
the rest of the API.

Ports are ignored: the loopback bindings decide which ports answer. A request
without a Host header is refused.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("state-api")

HOSTS_ENV = "STATE_API_ALLOWED_HOSTS"
TUNNEL_HOSTS_ENV = "STATE_API_TUNNEL_HOSTS"
DEFAULT_HOSTS = ("127.0.0.1", "localhost", "state-api")
TUNNEL_PATHS = frozenset({"/webhook/tradingview"})


def host_name(value: str) -> str:
    """The hostname in a Host header value: lowercased, without its port or a trailing dot."""
    value = value.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[: end + 1] if end > 0 else ""
    if value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value.rstrip(".")


def _names(values: Iterable[str]) -> set[str]:
    return {host_name(value) for value in values if value.strip()}


class HostGuard:
    """ASGI middleware: a request whose Host this API does not answer to is refused before routing."""

    def __init__(
        self, app: ASGIApp, *, allowed_hosts: Iterable[str] | None = None, tunnel_hosts: Iterable[str] | None = None
    ) -> None:
        self.app = app
        extra = os.getenv(HOSTS_ENV, "").split(",") if allowed_hosts is None else list(allowed_hosts)
        configured = _names((*DEFAULT_HOSTS, *extra))
        self.enforced = "*" not in configured
        self.allowed_hosts = frozenset(configured - {"*", ""})
        tunnel = os.getenv(TUNNEL_HOSTS_ENV, "").split(",") if tunnel_hosts is None else list(tunnel_hosts)
        self.tunnel_hosts = frozenset(_names(tunnel) - {"*", ""})

    def allows(self, host: str, path: str) -> bool:
        name = host_name(host)
        if name in self.allowed_hosts:
            return True
        return name in self.tunnel_hosts and path in TUNNEL_PATHS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket") or not self.enforced:
            await self.app(scope, receive, send)
            return
        host, path = Headers(scope=scope).get("host", ""), scope.get("path", "")
        if self.allows(host, path):
            await self.app(scope, receive, send)
            return
        logger.warning("host refused: %r for %r", host[:100], path[:200])
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        response = JSONResponse({"detail": "This Host is not served by the TradeSync state API.", "authority": "none"}, 400)
        await response(scope, receive, send)
