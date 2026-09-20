"""What each free context provider is asked, and what is made of its answer.

Moved out of ``app/context_feed.py`` unchanged. The service keeps its
``_fetch_*`` methods, which delegate here, so caching, failure holds and the
tests that replace those methods on an instance all behave exactly as before.

Each function takes the service's client *getter* rather than a client, so a
refusal that needs no network — FRED without a key — still happens before any
client is created.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Sequence

import httpx

from . import economic_calendar, fed_calendar

# The feed's own logger name, so moving these functions changes no log line.
logger = logging.getLogger("app.context_feed")

ClientGetter = Callable[[], Awaitable[httpx.AsyncClient]]


async def fetch_coingecko(get_client: ClientGetter) -> Dict[str, Any]:
    client = await get_client()
    response = await client.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": "bitcoin,ethereum,solana",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        },
    )
    response.raise_for_status()
    raw = response.json()
    symbols = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}
    assets = {}
    for asset_id, symbol in symbols.items():
        item = raw.get(asset_id) or {}
        if "usd" not in item:
            continue
        assets[symbol] = {
            "price_usd": item["usd"],
            "change_24h_pct": item.get("usd_24h_change"),
            "observed_at": item.get("last_updated_at"),
        }
    if not assets:
        raise ValueError("CoinGecko response contained no tracked assets")
    return {"metric_family": "aggregate_spot_reference", "assets": assets}


async def fetch_defillama(get_client: ClientGetter) -> Dict[str, Any]:
    client = await get_client()
    response = await client.get("https://api.llama.fi/tvl/hyperliquid")
    response.raise_for_status()
    return {
        "metric_family": "protocol_context",
        "protocol": "Hyperliquid",
        "tvl_usd": float(response.json()),
    }


async def fetch_fred(get_client: ClientGetter, api_key: str, series: Sequence[str]) -> Dict[str, Any]:
    if not api_key:
        raise RuntimeError("FRED API key is not configured")
    client = await get_client()
    values: Dict[str, Any] = {}
    for series_id in series:
        response = await client.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": "1",
            },
        )
        response.raise_for_status()
        observations = response.json().get("observations") or []
        if observations:
            latest = observations[0]
            values[series_id] = {"value": latest.get("value"), "date": latest.get("date")}
    return {"metric_family": "macro_reference", "series": values}


async def fetch_calendar(get_client: ClientGetter, fred_api_key: str) -> Dict[str, Any]:
    """ForexFactory's weekly feed, plus FRED release dates when a key exists.

    Each feed is validated event by event; a malformed event is dropped
    and counted rather than shown at a guessed time. FRED failing does not
    lose the ForexFactory half, and vice versa — the payload says which
    sources answered.
    """
    client = await get_client()
    now = datetime.now(timezone.utc)
    response = await client.get(
        economic_calendar.FF_FEED_URL,
        headers={"User-Agent": "TradeSync private research workstation"},
    )
    response.raise_for_status()
    parts = [economic_calendar.normalise_forexfactory(response.json(), now)]
    if fred_api_key:
        try:
            fred = await client.get(
                "https://api.stlouisfed.org/fred/releases/dates",
                params={
                    "api_key": fred_api_key,
                    "file_type": "json",
                    "include_release_dates_with_no_data": "true",
                    "realtime_start": now.strftime("%Y-%m-%d"),
                    "sort_order": "asc",
                    # About forty releases a business day: 200 rows ended the
                    # window after two days, and daily series need the whole
                    # week to be recognised as daily.
                    "limit": "1000",
                },
            )
            fred.raise_for_status()
            parts.append(economic_calendar.normalise_fred_release_dates(fred.json(), now))
        except Exception as exc:  # the other half still stands
            logger.warning("FRED release dates failed: %s", type(exc).__name__)
    # FOMC decision days from the Fed's published calendar, where the week's feed lacks them.
    parts.append(fed_calendar.fomc_decisions(now, [e for part in parts for e in part.events]))
    payload = economic_calendar.merge(*parts)
    payload["fred_configured"] = bool(fred_api_key)
    return payload
