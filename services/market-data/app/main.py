"""
Market Data Service - Phase 3B

Main entry point that runs:
1. Provider pollers (rate-limited)
2. Normalizer (raw -> normalized)
3. Snapshotter (normalized -> snapshots with regimes)
4. Alert emitter (regime changes)

The work itself lives beside this file, one responsibility per module:

- ``runtime``: configuration and the state the loops and routes share;
- ``pollers``: the polling loops;
- ``enrichment``: what is attached to a snapshot before it is stored;
- ``health_routes``, ``market_routes``, ``chart_routes``: the read surface.

This module is the composition root: it creates the app, runs the loops for the
life of the process, and mounts the routers. ``services/market-data/Dockerfile``
runs ``app.main:app``.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import binance_liquidations, liquidation_context, liquidity_context
from .chart_routes import router as chart_router
from .depth_books import AGGREGATIONS as DEPTH_AGGREGATIONS
from .depth_stream import run_depth_stream
from .enrichment import fetch_map_bars
from .feed_status_route import router as feed_status_router
from .funding_history_route import router_for as funding_history_router
from .health_routes import router as health_router
from .http_clients import clients as http_clients
from .market_routes import (
    DEFAULT_FEATURE_HISTORY_WINDOW_MS,
    FEATURE_HISTORY_WINDOWS_MS,
    router as market_router,
)
from .market_stream import run_market_stream
from .pollers import (
    poll_context_loop,
    poll_funding_history_loop,
    poll_orderbook_loop,
)
from .reference_pollers import (
    poll_cross_venue_loop,
    poll_news_tone_loop,
    poll_spot_reference_loop,
)
from .providers import HyperliquidProvider
from .redis_client import redis_client
from .runtime import (
    ENABLE_HYPERLIQUID,
    MARKET_STREAM_ENABLED,
    SYMBOLS,
    background_tasks,
    depth_books,
    logger,
    market_stream,
    providers,
    trade_flow,
)
from .stream_resync import resync_from_rest
from .trade_stream import run_trade_stream

# The batch and single feature-history endpoints share one window table
# (``app/market_routes.py``); re-exported here because that is where it was
# defined and where tests read it from.
__all__ = ["app", "DEFAULT_FEATURE_HISTORY_WINDOW_MS", "FEATURE_HISTORY_WINDOWS_MS"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Market Data Service...")

    # Connect to Redis
    await redis_client.connect()

    # Initialize providers
    if ENABLE_HYPERLIQUID:
        providers.append(HyperliquidProvider())
        logger.info("Hyperliquid provider enabled")


    if not providers:
        logger.warning("No providers enabled!")

    # Start background tasks
    hyperliquid = next((p for p in providers if p.venue == "hyperliquid"), None)
    if MARKET_STREAM_ENABLED and hyperliquid is not None:
        # Asset contexts, the scoring book and candles; the poll loops fall back to REST while it is stale.
        background_tasks.append(asyncio.create_task(run_market_stream(
            market_stream, lambda: resync_from_rest(hyperliquid, market_stream, SYMBOLS)
        )))
    background_tasks.append(asyncio.create_task(poll_context_loop()))
    background_tasks.append(asyncio.create_task(poll_orderbook_loop()))
    background_tasks.append(asyncio.create_task(poll_funding_history_loop()))
    background_tasks.append(asyncio.create_task(poll_spot_reference_loop()))
    background_tasks.append(asyncio.create_task(poll_news_tone_loop()))
    background_tasks.append(asyncio.create_task(poll_cross_venue_loop()))
    background_tasks.append(asyncio.create_task(liquidation_context.run(redis_client.client)))
    background_tasks.append(asyncio.create_task(binance_liquidations.run(redis_client.client, SYMBOLS)))
    background_tasks.append(asyncio.create_task(liquidity_context.run(redis_client.client, SYMBOLS, fetch_map_bars)))
    for n_sig_figs in DEPTH_AGGREGATIONS:
        background_tasks.append(
            asyncio.create_task(
                run_depth_stream(depth_books, [s.replace('-PERP', '') for s in SYMBOLS], n_sig_figs)
            )
        )
    background_tasks.append(
        asyncio.create_task(
            run_trade_stream(trade_flow, [s.replace('-PERP', '') for s in SYMBOLS])
        )
    )

    logger.info("Market Data Service started")

    yield

    # Shutdown
    logger.info("Shutting down Market Data Service...")

    for task in background_tasks:
        task.cancel()

    await asyncio.gather(*background_tasks, return_exceptions=True)
    # Every provider's pooled connections, closed once nothing is left to use them.
    await http_clients.close_all()
    await redis_client.disconnect()

    logger.info("Market Data Service stopped")


# FastAPI app
app = FastAPI(
    title="TradeSync Market Data Service",
    version="0.1.0",
    description="Phase 3B - Market Data Expansion",
    lifespan=lifespan
)

app.include_router(health_router)
app.include_router(market_router)
app.include_router(chart_router)
app.include_router(funding_history_router(providers, SYMBOLS))
app.include_router(feed_status_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
