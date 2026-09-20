"""Whether a TradingView alert came from TradingView, decided before its body is read (finding L2).

The Cloudflare WAF blocks every source but TradingView's four addresses at the
edge. This is the receiver's own copy of that check, so an edited or disabled
edge rule does not leave the endpoint open to anyone who knows the URL.

Behind the tunnel every request arrives from cloudflared, so the TCP peer is the
connector. Its address on the pine-ingress network is fixed
(``ops/compose.ingress.yml``) and named in ``TRADINGVIEW_INGRESS_PEERS``. The
connector is also named by its service name in ``TRADINGVIEW_INGRESS_HOSTS``,
resolved for each alert: a connector created before it moved to pine-ingress
sits on the shared network at an address Docker assigned, and with only the
fixed address believed, every alert it forwarded was refused. Only from those
peers is Cloudflare's ``CF-Connecting-IP`` believed. From any other peer the
header is ignored and the peer itself is the source. uvicorn runs with
``--no-proxy-headers``, so the peer is the socket's own address, never one a
caller forwarded.

``TRADINGVIEW_SOURCE_CHECK=off`` switches the check off as a rollback lever. The
body secret, the 16 KB bound and digest dedupe stay in force either way.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, Collection, Mapping, Sequence

from starlette.requests import Request
from starlette.responses import JSONResponse

from tradesync_core.tradingview_webhook import alert_source, is_allowed_source, normalise_ip

logger = logging.getLogger("state-api")

PEERS_ENV = "TRADINGVIEW_INGRESS_PEERS"
HOSTS_ENV = "TRADINGVIEW_INGRESS_HOSTS"
CHECK_ENV = "TRADINGVIEW_SOURCE_CHECK"
CF_CONNECTING_IP = "cf-connecting-ip"
REFUSAL = {
    "accepted": False,
    "reasons": [
        {
            "code": "source_not_allowed",
            "detail": "alerts are accepted only from TradingView's published webhook addresses",
        }
    ],
    "authority": "none",
}


def configured_peers(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """The tunnel connector addresses from ``TRADINGVIEW_INGRESS_PEERS``, comma-separated; entries that are not addresses are dropped."""
    raw = (os.environ if environ is None else environ).get(PEERS_ENV, "")
    return frozenset(address for address in map(normalise_ip, raw.split(",")) if address)


def check_enforced(environ: Mapping[str, str] | None = None) -> bool:
    return (os.environ if environ is None else environ).get(CHECK_ENV, "").strip().lower() != "off"


def configured_hosts(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The tunnel connector's host names from ``TRADINGVIEW_INGRESS_HOSTS``, comma-separated; blanks dropped."""
    raw = (os.environ if environ is None else environ).get(HOSTS_ENV, "")
    return tuple(host.strip() for host in raw.split(",") if host.strip())


async def _addresses(host: str) -> list[str]:
    """Every address ``host`` resolves to now, looked up off the event loop."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    return [info[4][0] for info in infos]


async def resolve_peers(
    hosts: Sequence[str], lookup: Callable[[str], Awaitable[list[str]]] | None = None
) -> frozenset[str]:
    """The addresses the connector's names resolve to for this alert.

    Resolved per alert rather than once at start, because Docker assigns the
    connector's address on a shared network and changes it when the container
    is recreated or moved. A name that does not resolve adds no peer, so the
    check fails closed.
    """
    lookup = lookup or _addresses
    addresses: set[str] = set()
    for host in hosts:
        try:
            found = await lookup(host)
        except (OSError, UnicodeError):
            continue
        addresses.update(filter(None, map(normalise_ip, found)))
    return frozenset(addresses)


TUNNEL_PEERS = configured_peers()
TUNNEL_HOSTS = configured_hosts()
ENFORCED = check_enforced()


async def refusal(
    request: Request,
    *,
    peers: Collection[str] | None = None,
    hosts: Sequence[str] | None = None,
    enforced: bool | None = None,
) -> JSONResponse | None:
    """A 403 for an alert whose source is not TradingView, or None when it may proceed."""
    if not (ENFORCED if enforced is None else enforced):
        return None
    tunnel_peers = TUNNEL_PEERS if peers is None else frozenset(filter(None, map(normalise_ip, peers)))
    peer = request.client.host if request.client else None
    if normalise_ip(peer) not in tunnel_peers:
        tunnel_peers = tunnel_peers | await resolve_peers(TUNNEL_HOSTS if hosts is None else hosts)
    source = alert_source(peer, request.headers.get(CF_CONNECTING_IP), tunnel_peers)
    if is_allowed_source(source):
        return None
    via = "tunnel" if normalise_ip(peer) in tunnel_peers else "direct"
    logger.warning(f"tradingview alert refused: source {source or 'unknown'} via {via}", extra={"trace_id": "webhook"})
    return JSONResponse(status_code=403, content=REFUSAL)
