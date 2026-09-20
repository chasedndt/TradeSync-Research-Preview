"""Free, context-only market enrichment feeds.

These providers enrich the operator dashboard. They are deliberately isolated
from scoring, risk, approvals, and execution. Hyperliquid remains the only
authoritative venue feed and the only future execution venue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

from . import context_shapes
from .context_feed_providers import fetch_calendar, fetch_coingecko, fetch_defillama, fetch_fred

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class CacheEntry:
    payload: Dict[str, Any]
    fetched_at: float


class ContextFeedService:
    """Fetch slow contextual data with independent caches and failures."""

    def __init__(self) -> None:
        self.coingecko_enabled = _env_bool("COINGECKO_CONTEXT_ENABLED", True)
        self.defillama_enabled = _env_bool("DEFILLAMA_CONTEXT_ENABLED", True)
        self.fred_enabled = _env_bool("FRED_CONTEXT_ENABLED", False)
        self.fred_api_key = os.getenv("FRED_API_KEY", "").strip()
        self.fred_series = [
            item.strip()
            for item in os.getenv("FRED_SERIES", "DFF,DTWEXBGS").split(",")
            if item.strip()
        ]
        self.timeout_seconds = float(os.getenv("CONTEXT_FEED_TIMEOUT_SECONDS", "6"))
        self.calendar_enabled = _env_bool("CALENDAR_CONTEXT_ENABLED", True)
        self.ttls = {
            "coingecko": int(os.getenv("COINGECKO_CONTEXT_TTL_SECONDS", "300")),
            "defillama": int(os.getenv("DEFILLAMA_CONTEXT_TTL_SECONDS", "900")),
            "fred": int(os.getenv("FRED_CONTEXT_TTL_SECONDS", "3600")),
            # The ForexFactory feed is a courtesy feed with unpublished terms:
            # once an hour is the most it is asked, and the answer is cached.
            "calendar": int(os.getenv("CALENDAR_CONTEXT_TTL_SECONDS", "3600")),
        }
        self._cache: Dict[str, CacheEntry] = {}
        self._failed_at: Dict[str, float] = {}
        self.failure_hold_seconds = int(os.getenv("CONTEXT_FEED_FAILURE_HOLD_SECONDS", "900"))
        self._locks = {name: asyncio.Lock() for name in self.ttls}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                headers={"User-Agent": "TradeSync-ContextFeeds/1.0"},
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _disabled(self, provider: str, reason: str = "disabled_by_configuration") -> Dict[str, Any]:
        return context_shapes.disabled(provider, reason)

    def _unavailable(self, provider: str, error: str, failed_at: float) -> Dict[str, Any]:
        return context_shapes.unavailable(
            provider, error, failed_at, self.failure_hold_seconds, self.ttls[provider]
        )

    def _format(self, provider: str, entry: CacheEntry, cached: bool) -> Dict[str, Any]:
        return context_shapes.formatted(
            provider, entry.payload, entry.fetched_at, cached, self.ttls[provider]
        )

    async def _cached_fetch(
        self,
        provider: str,
        fetcher: Callable[[], Awaitable[Dict[str, Any]]],
        force_refresh: bool,
    ) -> Dict[str, Any]:
        now = time.time()
        cached = self._cache.get(provider)
        if cached and not force_refresh and now - cached.fetched_at < self.ttls[provider]:
            return self._format(provider, cached, cached=True)

        async with self._locks[provider]:
            now = time.time()
            cached = self._cache.get(provider)
            if cached and not force_refresh and now - cached.fetched_at < self.ttls[provider]:
                return self._format(provider, cached, cached=True)

            # A recent failure is remembered too. Without this, a provider that
            # is rate-limiting us gets asked again on every overview poll — once
            # a minute from the Cockpit — which is exactly how a short 429
            # becomes a long one.
            held = self._failed_at.get(provider)
            if held and not force_refresh and now - held < self.failure_hold_seconds:
                if cached:
                    result = self._format(provider, cached, cached=True)
                    result.update(status="degraded", error="provider_refresh_failed")
                    return result
                return self._unavailable(provider, "provider_fetch_failed_recently", held)

            try:
                payload = await fetcher()
                entry = CacheEntry(payload=payload, fetched_at=time.time())
                self._cache[provider] = entry
                self._failed_at.pop(provider, None)
                return self._format(provider, entry, cached=False)
            except Exception as exc:
                logger.warning("Context provider %s failed: %s", provider, type(exc).__name__)
                self._failed_at[provider] = time.time()
                if cached:
                    result = self._format(provider, cached, cached=True)
                    result.update(status="degraded", error="provider_refresh_failed")
                    return result
                return self._unavailable(provider, "provider_fetch_failed", self._failed_at[provider])

    # What each provider is asked, and what is made of its answer, lives in
    # app/context_feed_providers.py. These stay methods so caching, failure holds
    # and tests that replace them on an instance behave exactly as before.
    async def _fetch_coingecko(self) -> Dict[str, Any]:
        return await fetch_coingecko(self._get_client)

    async def _fetch_defillama(self) -> Dict[str, Any]:
        return await fetch_defillama(self._get_client)

    async def _fetch_fred(self) -> Dict[str, Any]:
        return await fetch_fred(self._get_client, self.fred_api_key, self.fred_series)

    async def _fetch_calendar(self) -> Dict[str, Any]:
        """ForexFactory's weekly feed, plus FRED release dates when a key exists."""
        return await fetch_calendar(self._get_client, self.fred_api_key)

    async def fetch_overview(self, force_refresh: bool = False) -> Dict[str, Any]:
        tasks = []
        names = []
        if self.calendar_enabled:
            names.append("calendar")
            tasks.append(self._cached_fetch("calendar", self._fetch_calendar, force_refresh))

        if self.coingecko_enabled:
            names.append("coingecko")
            tasks.append(self._cached_fetch("coingecko", self._fetch_coingecko, force_refresh))
        if self.defillama_enabled:
            names.append("defillama")
            tasks.append(self._cached_fetch("defillama", self._fetch_defillama, force_refresh))
        if self.fred_enabled and self.fred_api_key:
            names.append("fred")
            tasks.append(self._cached_fetch("fred", self._fetch_fred, force_refresh))

        results = await asyncio.gather(*tasks) if tasks else []
        providers = {name: result for name, result in zip(names, results)}
        if not self.coingecko_enabled:
            providers["coingecko"] = self._disabled("coingecko")
        if not self.defillama_enabled:
            providers["defillama"] = self._disabled("defillama")
        if not self.fred_enabled:
            providers["fred"] = self._disabled("fred")
        elif not self.fred_api_key:
            providers["fred"] = self._disabled("fred", "free_api_key_not_configured")
        if not self.calendar_enabled:
            providers["calendar"] = self._disabled("calendar")

        return {
            "role": "context_only",
            "authoritative_market_source": "hyperliquid",
            "execution_venue": "hyperliquid",
            "execution_authority": False,
            "providers": providers,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "role": "context_only",
            "execution_authority": False,
            "providers": {
                "coingecko": {"enabled": self.coingecko_enabled, "ttl_seconds": self.ttls["coingecko"]},
                "defillama": {"enabled": self.defillama_enabled, "ttl_seconds": self.ttls["defillama"]},
                "fred": {
                    "enabled": self.fred_enabled,
                    "configured": bool(self.fred_api_key),
                    "ttl_seconds": self.ttls["fred"],
                    "series": self.fred_series,
                },
                "calendar": {
                    "enabled": self.calendar_enabled,
                    "ttl_seconds": self.ttls["calendar"],
                    "sources": ["forexfactory"] + (["fred"] if self.fred_api_key else []),
                },
            },
        }


context_feed = ContextFeedService()
