"""One long-lived HTTP client per provider: repeated polls reuse it, and shutdown closes it.

Every request used to build its own ``httpx.AsyncClient``, which opened a new
TCP and TLS connection each time. On 16 September that churn (about five new
connections a second) preceded a Docker Desktop crash with ~2,060 connections
stuck in its network forwarder. These tests prove the replacement at the level
that matters: a loopback server counts TCP connections, not client objects.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app import main, reference_pollers
from app.http_clients import POLICIES, ProviderClients
from app.open_interest_history import OpenInterestHistory
from app.providers.hyperliquid import HyperliquidProvider


class Stop(BaseException):
    """Ends a polling loop from inside its sleep."""


class NoWaitLimiter:
    async def acquire(self) -> None:
        return None

    def on_success(self) -> None: ...
    def on_error(self) -> None: ...
    def on_rate_limit(self) -> None: ...


class KeepAliveServer:
    """A loopback HTTP/1.1 server that answers every request on a connection and counts the connections."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.opened = 0
        self.closed = 0
        self.requests: list[dict] = []

    async def __aenter__(self) -> "KeepAliveServer":
        self.server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/info"
        return self

    async def __aexit__(self, *exc) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.opened += 1
        try:
            while True:
                head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1").split("\r\n")
                headers = dict(line.split(":", 1) for line in head[1:] if ":" in line)
                length = int(next((v for k, v in headers.items() if k.lower() == "content-length"), "0"))
                body = json.loads(await reader.readexactly(length)) if length else {}
                self.requests.append(body)
                data = json.dumps(self.answer(body)).encode()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             + f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass  # the client closed its end
        finally:
            self.closed += 1
            writer.close()


def venue_answer(body: dict):
    if body.get("type") == "metaAndAssetCtxs":
        return [{"universe": [{"name": "BTC", "szDecimals": 5, "maxLeverage": 40}]},
                [{"funding": "0.0000125", "openInterest": "100", "dayNtlVlm": "1000000", "markPx": "100000",
                  "oraclePx": "99990", "premium": "0.0001", "prevDayPx": "98000"}]]
    if body.get("type") == "l2Book":
        return {"coin": "BTC", "time": 1, "levels": [[{"px": "99999", "sz": "1", "n": 1}], [{"px": "100001", "sz": "1", "n": 1}]]}
    return []


def counting_factory(created: list, **transport):
    def factory(**kwargs):
        client = httpx.AsyncClient(**transport, **kwargs)
        created.append(client)
        return client
    return factory


def test_a_provider_gets_the_same_client_every_time_and_it_is_created_once() -> None:
    created: list = []
    http = ProviderClients(factory=counting_factory(created))
    assert http.get("hyperliquid") is http.get("hyperliquid")
    assert http.get("binance") is not http.get("hyperliquid")
    assert len(created) == 2
    assert http.status()["hyperliquid"] == {"open": True, "clients_created": 1}
    assert http.status()["gdelt"] == {"open": False, "clients_created": 0}
    asyncio.run(http.close_all())


def test_an_unknown_provider_has_no_default_client() -> None:
    with pytest.raises(KeyError):
        ProviderClients().get("somewhere-else")


def test_every_client_keeps_connections_alive_longer_than_its_poll_interval() -> None:
    for name, policy in POLICIES.items():
        assert policy.max_keepalive >= 1, name
        assert policy.keepalive_expiry_s >= 30, name


def test_repeated_hyperliquid_polls_ride_one_kept_alive_connection_until_shutdown() -> None:
    created: list = []

    async def scenario():
        async with KeepAliveServer(venue_answer) as server:
            http = ProviderClients(factory=counting_factory(created))
            provider = HyperliquidProvider(http=http, api_url=server.url)
            provider.limiter = NoWaitLimiter()
            for _ in range(5):
                assert "BTC-PERP" in await provider.fetch_context(["BTC-PERP"])
            for _ in range(3):
                assert (await provider.fetch_orderbook("BTC-PERP"))["best_bid"] == 99999.0
            during = (server.opened, server.closed, len(server.requests))
            await http.close_all()
            for _ in range(50):  # the server notices the close on its next read
                if server.closed:
                    break
                await asyncio.sleep(0.01)
            return during, (server.opened, server.closed)

    during, after = asyncio.run(scenario())
    assert during == (1, 0, 8), "eight polls must share one TCP connection"
    assert after == (1, 1), "shutdown must close the pooled connection"
    assert len(created) == 1 and created[0].is_closed


def test_the_spot_poller_reads_every_cycle_through_one_coinbase_client() -> None:
    created: list = []
    urls: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"bid": "100", "ask": "101"})

    http = ProviderClients(factory=counting_factory(created, transport=httpx.MockTransport(answer)))
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise Stop

    with patch.object(reference_pollers, "clients", http), \
            patch.object(reference_pollers, "SYMBOLS", ["BTC-PERP", "ETH-PERP"]), \
            patch.dict(reference_pollers.spot_reference, clear=True), \
            patch.object(reference_pollers.asyncio, "sleep", sleep):
        with pytest.raises(Stop):
            asyncio.run(reference_pollers.poll_spot_reference_loop())
        assert set(reference_pollers.spot_reference) == {"BTC-PERP", "ETH-PERP"}
    assert len(urls) == 6 and len(created) == 1
    assert created[0].headers["User-Agent"] == "tradesync/1.0"
    asyncio.run(http.close_all())


def test_the_cross_venue_poller_and_open_interest_history_share_one_binance_client() -> None:
    created: list = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("premiumIndex"):
            return httpx.Response(200, json={"lastFundingRate": "0.0001", "markPrice": "100", "time": 1_789_380_000_000})
        if request.url.path.endswith("openInterest"):
            return httpx.Response(200, json={"openInterest": "10", "time": 1_789_380_000_000})
        return httpx.Response(200, json=[{"timestamp": 1_789_380_000_000, "sumOpenInterest": "10", "sumOpenInterestValue": "1000"}])

    http = ProviderClients(factory=counting_factory(created, transport=httpx.MockTransport(answer)))
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise Stop

    with patch.object(reference_pollers, "clients", http), \
            patch.object(reference_pollers, "SYMBOLS", ["BTC-PERP"]), \
            patch.dict(reference_pollers.cross_venue_reference, clear=True), \
            patch.object(reference_pollers.asyncio, "sleep", sleep):
        with pytest.raises(Stop):
            asyncio.run(reference_pollers.poll_cross_venue_loop())
        assert reference_pollers.cross_venue_reference["BTC-PERP"]["open_interest"]["contracts"] == 10.0
    asyncio.run(OpenInterestHistory(http=http).get("BTC-PERP", "1h"))
    assert len(created) == 1


def test_the_news_tone_poller_keeps_one_gdelt_client_across_cycles() -> None:
    created: list = []
    http = ProviderClients(factory=counting_factory(
        created, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"timeline": []}))))
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 6:  # start-up delay, then two cycles of (two spacings + the cycle wait)
            raise Stop

    with patch.object(reference_pollers, "clients", http), \
            patch.object(reference_pollers, "SYMBOLS", ["BTC-PERP", "ETH-PERP"]), \
            patch.object(reference_pollers.asyncio, "sleep", sleep):
        with pytest.raises(Stop):
            asyncio.run(reference_pollers.poll_news_tone_loop())
    assert len(created) == 1
    assert created[0].headers["User-Agent"] == "tradesync/1.0 (private research)"


def test_the_service_lifespan_closes_every_provider_client_on_shutdown() -> None:
    created: list = []
    http = ProviderClients(factory=counting_factory(
        created, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))))

    async def idle(*args, **kwargs):
        await asyncio.Event().wait()

    loops = ["poll_context_loop", "poll_orderbook_loop", "poll_funding_history_loop", "poll_spot_reference_loop",
             "poll_news_tone_loop", "poll_cross_venue_loop", "run_depth_stream", "run_trade_stream"]
    patches = [patch.object(main, name, idle) for name in loops if hasattr(main, name)]
    patches += [patch.object(main.liquidation_context, "run", idle), patch.object(main.binance_liquidations, "run", idle),
                patch.object(main.liquidity_context, "run", idle), patch.object(main, "http_clients", http),
                patch.object(main, "providers", []), patch.object(main, "background_tasks", []),
                patch.object(main.redis_client, "connect", AsyncMock()), patch.object(main.redis_client, "disconnect", AsyncMock())]

    async def scenario():
        async with main.lifespan(main.app):
            http.get("hyperliquid")
            http.get("coinbase")
            assert not any(client.is_closed for client in created)

    for p in patches:
        p.start()
    try:
        asyncio.run(scenario())
    finally:
        for p in reversed(patches):
            p.stop()
    assert len(created) == 2 and all(client.is_closed for client in created)
