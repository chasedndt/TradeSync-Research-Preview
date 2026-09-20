"""
Hyperliquid market data provider.

API Documentation: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
"""

import httpx
import logging
import time
from typing import Dict, List, Any, Optional

from .base import BaseProvider
from ..http_clients import ProviderClients, clients as shared_clients
from ..rate_limiter import get_limiter
from .funding_history import FundingHistoryCache
from .hyperliquid_book import parse_l2_book
from .hyperliquid_context import context_entry

logger = logging.getLogger(__name__)

HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"


class HyperliquidProvider(BaseProvider):
    """Hyperliquid market data provider."""

    def __init__(self, http: Optional[ProviderClients] = None, api_url: str = HYPERLIQUID_API_URL):
        super().__init__("hyperliquid")
        self.api_url = api_url
        self.limiter = get_limiter("hyperliquid")
        # One pooled client for every request this provider makes (app/http_clients.py).
        self._http = http or shared_clients

        # Symbol mappings
        self._symbol_map = {
            "BTC": "BTC-PERP",
            "ETH": "ETH-PERP",
            "SOL": "SOL-PERP",
        }
        self._reverse_map = {v: k for k, v in self._symbol_map.items()}

    def normalize_symbol(self, venue_symbol: str) -> str:
        """Convert HL symbol (e.g., 'BTC') to canonical (e.g., 'BTC-PERP')."""
        return self._symbol_map.get(venue_symbol.upper(), f"{venue_symbol.upper()}-PERP")

    def denormalize_symbol(self, canonical_symbol: str) -> str:
        """Convert canonical symbol to HL format."""
        return self._reverse_map.get(canonical_symbol, canonical_symbol.replace("-PERP", ""))

    async def _request(self, payload: Dict[str, Any]) -> Any:
        """Make rate-limited request to Hyperliquid API."""
        await self.limiter.acquire()

        try:
            # The shared client keeps the connection alive for the next request,
            # rather than a client per request paying a TCP and TLS handshake each time.
            response = await self._http.get("hyperliquid").post(
                self.api_url,
                json=payload,
                timeout=10.0
            )

            if response.status_code == 429:
                self.limiter.on_rate_limit()
                raise Exception("Rate limited")

            response.raise_for_status()
            self.limiter.on_success()
            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                self.limiter.on_rate_limit()
            else:
                self.limiter.on_error()
            raise
        except Exception as e:
            self.limiter.on_error()
            raise

    async def fetch_asset_contexts(self, symbols: List[str]) -> Dict[str, tuple]:
        """The venue's asset contexts as sent: ``{canonical: (venue_symbol, ctx, asset_info)}``.

        Raises on a failed request; ``fetch_context`` is the forgiving reader.
        """
        data = await self._request({"type": "metaAndAssetCtxs"})

        # data is [meta, assetCtxs]
        # meta['universe'] has asset definitions
        # assetCtxs is parallel array of contexts
        universe = data[0]["universe"]
        asset_ctxs = data[1]

        contexts = {}
        for i, asset_info in enumerate(universe):
            venue_symbol = asset_info["name"]
            canonical = self.normalize_symbol(venue_symbol)
            if canonical in symbols:
                contexts[canonical] = (venue_symbol, asset_ctxs[i], asset_info)
        return contexts

    async def fetch_context(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Fetch main context data using metaAndAssetCtxs endpoint.

        Returns funding, OI, volume, mark/oracle prices for all assets.
        """
        try:
            contexts = await self.fetch_asset_contexts(symbols)
            poll_ts = int(time.time() * 1000)

            # The entry itself is built in providers/hyperliquid_context.py.
            result = {
                canonical: context_entry(self.venue, canonical, venue_symbol, ctx, poll_ts, asset_info)
                for canonical, (venue_symbol, ctx, asset_info) in contexts.items()
            }

            logger.debug(f"Fetched context for {len(result)} symbols from Hyperliquid")
            return result

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid context: {e}")
            return {}

    async def fetch_l2_book(self, symbol: str) -> Optional[Dict[str, Any]]:
        """The venue's ``l2Book`` answer as sent (20 levels a side and the venue time), or None."""
        try:
            data = await self._request({"type": "l2Book", "coin": self.denormalize_symbol(symbol)})
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid orderbook for {symbol}: {e}")
            return None
        return data if isinstance(data, dict) else None

    async def fetch_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch L2 orderbook for a symbol.

        Returns 20 levels per side.
        """
        data = await self.fetch_l2_book(symbol)
        if data is None:
            return None
        try:
            # The parsing, depth and imbalance arithmetic lives in
            # providers/hyperliquid_book.py.
            return parse_l2_book(self.venue, symbol, data, int(time.time() * 1000))

        except Exception as e:
            logger.error(f"Error fetching Hyperliquid orderbook for {symbol}: {e}")
            return None

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV candles for the Market Canvas.

        Display data only. Nothing returned here is admitted to the feature
        catalog or permitted to influence a paper signal.
        """
        venue_symbol = self.denormalize_symbol(symbol)
        try:
            data = await self._request({
                "type": "candleSnapshot",
                "req": {
                    "coin": venue_symbol,
                    "interval": interval,
                    "startTime": start_time,
                    "endTime": end_time,
                },
            })
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid candles for {symbol}: {e}")
            return []

        if not isinstance(data, list):
            logger.warning(f"Unexpected candle payload for {symbol}: {type(data)}")
            return []
        return data

    async def fetch_funding_history(
        self,
        symbol: str,
        start_time: int,
        end_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch historical funding rates across the whole window.

        Hyperliquid pages ``fundingHistory`` 500 rows at a time. The cache in
        ``funding_history`` pages through a window once, then fetches only the
        hours published since. Rows keep the premium.

        Args:
            symbol: Canonical symbol
            start_time: Unix timestamp (ms)
            end_time: Unix timestamp (ms); now when omitted
        """
        hl_symbol = self.denormalize_symbol(symbol)
        cache = self._funding_cache()
        try:
            result = await cache.history(symbol, hl_symbol, start_time, end_time)
            logger.debug(f"Funding history for {symbol}: {len(result)} entries in the window")
            return result
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid funding history: {e}")
            # What is already held for the window is still true; the missing pages are retried next time.
            end = end_time if end_time is not None else int(time.time() * 1000)
            return cache.cached(symbol, start_time, end)

    def _funding_cache(self) -> FundingHistoryCache:
        if getattr(self, "_funding_history_cache", None) is None:
            self._funding_history_cache = FundingHistoryCache(self._request, self.venue)
        return self._funding_history_cache

    async def fetch_predicted_funding(self) -> Dict[str, Any]:
        """Fetch predicted funding rates (cross-venue)."""
        try:
            data = await self._request({"type": "predictedFundings"})
            return data
        except Exception as e:
            logger.error(f"Error fetching predicted funding: {e}")
            return {}
