"""One long-lived HTTP client per external provider, shared by every poll and closed on shutdown.

On 16 September Docker Desktop crashed with about 2,060 TCP connections stuck
"in progress" in its network forwarder. Its log showed market-data opening a new
HTTPS connection to Hyperliquid (behind CloudFront) and to Cloudflare-hosted
APIs roughly five times a second, and after the restart the service sat around
140 sockets in TIME_WAIT. Every request had built its own ``httpx.AsyncClient``,
so every request paid a TCP and TLS handshake and closed its socket as soon as
it was answered.

Each provider now has exactly one client for the life of the process, created on
first use. Its pool keeps connections alive between polls, so a steady poll
rides one warm connection instead of opening a new one each time, and
``close_all`` closes them when the service shuts down. A request may still pass
its own ``timeout``; everything else about the connection is the provider's.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClientPolicy:
    """How one provider's pooled connections behave."""

    timeout_s: float
    max_connections: int
    max_keepalive: int
    # Longer than the provider's poll interval, so a connection survives from one poll to the next.
    keepalive_expiry_s: float
    headers: tuple[tuple[str, str], ...] = ()

    def limits(self) -> httpx.Limits:
        return httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive,
            keepalive_expiry=self.keepalive_expiry_s,
        )


POLICIES: Mapping[str, ClientPolicy] = {
    # Hyperliquid's info endpoint. Every request also passes the venue rate limiter,
    # so a handful of pooled connections is more than it ever uses at once.
    "hyperliquid": ClientPolicy(timeout_s=10.0, max_connections=10, max_keepalive=4, keepalive_expiry_s=60.0),
    # Coinbase Exchange tickers, read every three seconds.
    "coinbase": ClientPolicy(timeout_s=5.0, max_connections=6, max_keepalive=3, keepalive_expiry_s=60.0,
                             headers=(("User-Agent", "tradesync/1.0"),)),
    # Binance USD-M futures: premium index and open interest every minute, open-interest history on demand.
    "binance": ClientPolicy(timeout_s=15.0, max_connections=10, max_keepalive=4, keepalive_expiry_s=90.0,
                            headers=(("User-Agent", "tradesync/1.0"),)),
    # GDELT DOC 2.0: one request at a time, fifteen seconds apart, a cycle every fifteen minutes.
    "gdelt": ClientPolicy(timeout_s=20.0, max_connections=2, max_keepalive=1, keepalive_expiry_s=30.0,
                          headers=(("User-Agent", "tradesync/1.0 (private research)"),)),
}

ClientFactory = Callable[..., httpx.AsyncClient]


class ProviderClients:
    """The one client per provider, created on first use and kept until ``close_all``."""

    def __init__(self, policies: Mapping[str, ClientPolicy] = POLICIES, factory: ClientFactory = httpx.AsyncClient) -> None:
        self._policies = dict(policies)
        self._factory = factory
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._created: dict[str, int] = {}

    def get(self, provider: str) -> httpx.AsyncClient:
        """The provider's client. An unknown provider raises ``KeyError``: there is no default client."""
        policy = self._policies[provider]
        client = self._clients.get(provider)
        if client is None or client.is_closed:
            client = self._factory(timeout=policy.timeout_s, limits=policy.limits(), headers=dict(policy.headers))
            self._clients[provider] = client
            self._created[provider] = self._created.get(provider, 0) + 1
        return client

    async def close_all(self) -> None:
        """Close every client; a later ``get`` opens a fresh one."""
        clients, self._clients = self._clients, {}
        for provider, client in clients.items():
            try:
                await client.aclose()
            except Exception as exc:  # shutdown must finish even if one pool fails to close cleanly
                logger.warning("closing the %s HTTP client failed (%s)", provider, type(exc).__name__)

    def status(self) -> dict[str, Any]:
        """Per provider: whether a client is open, and how many have been created since the service started."""
        return {
            provider: {
                "open": provider in self._clients and not self._clients[provider].is_closed,
                "clients_created": self._created.get(provider, 0),
            }
            for provider in self._policies
        }


clients = ProviderClients()
