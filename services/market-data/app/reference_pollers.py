"""The external reference loops: Coinbase spot, Binance funding and OI, GDELT tone.

Moved out of ``app/main.py`` unchanged, and kept apart from the venue loops in
``app/pollers.py`` because their standing is different: everything here is
Tier B context. Each failure is logged and skipped, so an outage at an external
reference never disturbs Hyperliquid observation.

Each loop reads through its provider's one long-lived client
(``app/http_clients.py``); none opens a client of its own per cycle.
"""

import asyncio
import time

from .cross_venue import (
    BINANCE_OPEN_INTEREST_URL,
    BINANCE_PREMIUM_INDEX_URL,
    binance_symbol_for,
    parse_open_interest,
    parse_premium_index,
)
from .news_tone import (
    BACKOFF_AFTER_429_S,
    GDELT_DOC_URL,
    MIN_REQUEST_SPACING_S,
    parse_timelinetone,
    query_for,
)
from .http_clients import clients
from .runtime import (
    CROSS_VENUE_POLL_INTERVAL_S,
    NEWS_TONE_POLL_INTERVAL_S,
    NEWS_TONE_STARTUP_DELAY_S,
    SPOT_POLL_INTERVAL_MS,
    SYMBOLS,
    cross_venue_reference,
    logger,
    news_tone_reference,
    spot_reference,
)
from .spot_premium import COINBASE_TICKER_URL, coinbase_product_for, spot_mid


async def poll_spot_reference_loop():
    """Poll Coinbase spot for the premium reference.

    Failures are logged and skipped: this is Tier B context, and an outage at an
    external reference must never disturb Hyperliquid observation.
    """
    logger.info("Starting Coinbase spot reference poller")
    while True:
        try:
            async def read_one(client, symbol: str) -> None:
                product = coinbase_product_for(symbol)
                if not product:
                    return
                try:
                    response = await client.get(
                        COINBASE_TICKER_URL.format(product=product),
                        timeout=5.0,
                    )
                    response.raise_for_status()
                    mid = spot_mid(response.json())
                    if mid is not None:
                        # Stamped at the moment of the read, not the end of the
                        # batch, so alignment skew reflects this symbol only.
                        spot_reference[symbol] = (mid, int(time.time() * 1000))
                except Exception as exc:
                    logger.warning(f"Coinbase spot unavailable for {product}: {exc}")

            client = clients.get("coinbase")
            # Concurrently: read sequentially and the last symbol is always
            # the stalest, which showed up as an intermittently missing
            # premium on SOL.
            await asyncio.gather(*(read_one(client, s) for s in SYMBOLS))
        except Exception as exc:
            logger.warning(f"Spot reference poll failed: {exc}")
        await asyncio.sleep(SPOT_POLL_INTERVAL_MS / 1000)


async def poll_cross_venue_loop():
    """Read Binance funding and OI for every symbol, concurrently, once a minute.

    Two public requests per coin per minute. A coin Binance does not list
    simply never gets a reading. Failures are logged and skipped: an external
    reference venue must never disturb Hyperliquid observation.
    """
    logger.info("Starting Binance cross-venue poller")
    while True:
        try:
            async def read_one(client, symbol: str) -> None:
                venue_symbol = binance_symbol_for(symbol)
                try:
                    premium_raw = await client.get(
                        BINANCE_PREMIUM_INDEX_URL, params={"symbol": venue_symbol}, timeout=8.0
                    )
                    premium_raw.raise_for_status()
                    premium = parse_premium_index(premium_raw.json())
                    if premium is None:
                        return
                    entry = cross_venue_reference.setdefault(symbol, {})
                    entry["premium"] = premium
                    oi_raw = await client.get(
                        BINANCE_OPEN_INTEREST_URL, params={"symbol": venue_symbol}, timeout=8.0
                    )
                    oi_raw.raise_for_status()
                    oi = parse_open_interest(oi_raw.json(), premium["mark_price_usd"])
                    if oi is not None:
                        entry["open_interest"] = oi
                except Exception as exc:
                    logger.warning(f"Binance unavailable for {venue_symbol}: {exc}")

            client = clients.get("binance")
            await asyncio.gather(*(read_one(client, s) for s in SYMBOLS))
        except Exception as exc:
            logger.warning(f"Cross-venue poll failed: {exc}")
        await asyncio.sleep(CROSS_VENUE_POLL_INTERVAL_S)


async def poll_news_tone_loop():
    """Ask GDELT for each coin's tone, one request at a time, spaced apart.

    GDELT's limit is one request every five seconds. Coins are polled
    sequentially with a gap, not concurrently, and a coin without a safe query
    is skipped. Failures are logged and skipped: Tier B context must never
    disturb Hyperliquid observation.
    """
    logger.info("Starting GDELT news tone poller")
    # Every redeploy used to fire a full cycle at once; several redeploys in an
    # afternoon read, to GDELT, like a burst. Wait before the first cycle.
    await asyncio.sleep(NEWS_TONE_STARTUP_DELAY_S)
    while True:
        try:
            client = clients.get("gdelt")
            for symbol in SYMBOLS:
                query = query_for(symbol)
                if not query:
                    continue
                try:
                    response = await client.get(
                        GDELT_DOC_URL,
                        params={
                            "query": query,
                            "mode": "timelinetone",
                            # A day, not six hours: for smaller coins GDELT
                            # answers a six-hour window with an empty object.
                            # Freshness still governs what gets attached.
                            "timespan": "24h",
                            "format": "json",
                        },
                        timeout=20.0,
                    )
                    if response.status_code == 429:
                        # GDELT's limit is per-IP and bursty; one refusal
                        # means back off well past the nominal spacing.
                        logger.warning(f"GDELT rate-limited on {symbol}; backing off {BACKOFF_AFTER_429_S:.0f}s")
                        await asyncio.sleep(BACKOFF_AFTER_429_S)
                        continue
                    response.raise_for_status()
                    reading = parse_timelinetone(response.json(), int(time.time() * 1000))
                    if reading is not None:
                        news_tone_reference[symbol] = reading
                    else:
                        body = response.text[:160].replace("\n", " ")
                        logger.warning(f"GDELT tone for {symbol}: no closed bucket in response ({body!r})")
                except Exception as exc:
                    logger.warning(f"GDELT tone unavailable for {symbol}: {exc}")
                await asyncio.sleep(MIN_REQUEST_SPACING_S)
        except Exception as exc:
            logger.warning(f"News tone poll failed: {exc}")
        await asyncio.sleep(NEWS_TONE_POLL_INTERVAL_S)
