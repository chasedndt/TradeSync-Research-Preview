"""The venue polling loops: Hyperliquid context, books and funding history.

Moved out of ``app/main.py``. Hyperliquid is the authoritative venue, so these
three loops are what the service exists to run; the external reference sources
beside them live in ``app/reference_pollers.py``.

The context and book loops read the Hyperliquid market stream first and the
REST endpoint only for markets whose stream reading is stale
(``app/stream_readings.py``). Their cadence is unchanged: a loop still builds a
snapshot per interval, it just no longer needs a request to do it.
"""

import asyncio
import time

from . import book_history
from .enrichment import store_snapshot_and_features
from .market_stream import HEARTBEAT as STREAM_HEARTBEAT
from .redis_client import redis_client
from .runtime import (
    FUNDING_HISTORY_LOOKBACK_SECONDS,
    MARKET_STREAM_ENABLED,
    MARKET_STREAM_FRESH_MS,
    POLL_INTERVAL_CONTEXT,
    POLL_INTERVAL_FUNDING_HISTORY,
    POLL_INTERVAL_ORDERBOOK,
    SYMBOLS,
    feature_sampling_intervals,
    logger,
    market_stream,
    normalizer,
    providers,
    snapshotter,
)
from .stream_readings import contexts_for, orderbook_for


def _stream():
    """The market stream's state, or None when the stream is switched off and REST answers everything."""
    return market_stream if MARKET_STREAM_ENABLED else None


def _now_ms() -> int:
    return int(time.time() * 1000)


async def poll_context_loop():
    """Poll context data (funding, OI, volume) from all providers."""
    logger.info(f"Starting context poller for symbols: {SYMBOLS}")

    while True:
        try:
            for provider in providers:
                if not provider.enabled:
                    continue

                try:
                    # Fresh stream contexts, and one REST request for any market without one
                    raw_data = await contexts_for(
                        provider, SYMBOLS, _stream(), _now_ms(), MARKET_STREAM_FRESH_MS, STREAM_HEARTBEAT
                    )

                    if not raw_data:
                        continue

                    # Normalize
                    events = normalizer.normalize_context(provider.venue, raw_data)

                    # Push to Redis stream and update snapshots
                    for event in events:
                        # Push normalized event to stream
                        await redis_client.push_normalized(event.model_dump())

                        # Update snapshot
                        snapshot = snapshotter.process_event(event)
                        if snapshot:
                            # Store snapshot
                            await store_snapshot_and_features(snapshot)

                            # Check for regime changes
                            alerts = snapshotter.check_regime_change(
                                snapshot.venue,
                                snapshot.symbol,
                                snapshot.regimes
                            )
                            for alert in alerts:
                                await redis_client.push_alert(alert.model_dump())

                            # Append to timeseries
                            if snapshot.funding:
                                await redis_client.append_timeseries(
                                    snapshot.venue, snapshot.symbol,
                                    "funding", snapshot.funding.horizons.now,
                                    snapshot.ts
                                )
                            if snapshot.oi:
                                await redis_client.append_timeseries(
                                    snapshot.venue, snapshot.symbol,
                                    "oi", snapshot.oi.current_usd,
                                    snapshot.ts
                                )

                except Exception as e:
                    logger.error(f"Error polling {provider.venue} context: {e}")

            await asyncio.sleep(POLL_INTERVAL_CONTEXT / 1000)

        except asyncio.CancelledError:
            logger.info("Context poller cancelled")
            break
        except Exception as e:
            logger.error(f"Context poller error: {e}")
            await asyncio.sleep(5)


async def poll_orderbook_loop():
    """Poll orderbook data from all providers.

    Symbols are read concurrently, not one after another. The snapshot's
    timestamp is refreshed by this loop, and a sequential pass over ten
    symbols took about 25 seconds — so the first symbols in the list aged past
    Mission Control's 15-second freshness rule every cycle, as a staircase of
    ages (1s, 2s … 20s, 25s) showed on 2026-09-12. The venue rate limiter is
    still the throttle; concurrency only removes the self-inflicted queue.
    """
    logger.info(f"Starting orderbook poller for symbols: {SYMBOLS}")

    async def read_one(provider, symbol: str) -> None:
        try:
            # The scoring book: the stream's while fresh, one REST request otherwise
            orderbook = await orderbook_for(
                provider, symbol, _stream(), _now_ms(), MARKET_STREAM_FRESH_MS, STREAM_HEARTBEAT
            )
            if not orderbook:
                return
            try:
                await book_history.capture(redis_client.client, symbol, orderbook)
            except Exception as exc:
                logger.warning('Book history capture unavailable (%s)', type(exc).__name__)
            event = normalizer.normalize_orderbook(provider.venue, orderbook)
            if event:
                await redis_client.push_normalized(event.model_dump())
                snapshot = snapshotter.process_event(event)
                if snapshot:
                    await store_snapshot_and_features(snapshot)
        except Exception as e:
            logger.error(f"Error polling {provider.venue} orderbook for {symbol}: {e}")

    while True:
        try:
            for provider in providers:
                if not provider.enabled:
                    continue
                await asyncio.gather(*(read_one(provider, s) for s in SYMBOLS))

            await asyncio.sleep(POLL_INTERVAL_ORDERBOOK / 1000)

        except asyncio.CancelledError:
            logger.info("Orderbook poller cancelled")
            break
        except Exception as e:
            logger.error(f"Orderbook poller error: {e}")
            await asyncio.sleep(5)


async def poll_funding_history_loop():
    """Poll historical funding data periodically."""
    logger.info("Starting funding history poller")

    import time

    while True:
        try:
            # Fetch the feature catalog's seven-day funding comparison window.
            start_time = int((time.time() - FUNDING_HISTORY_LOOKBACK_SECONDS) * 1000)

            for provider in providers:
                if not provider.enabled:
                    continue

                for symbol in SYMBOLS:
                    try:
                        history = await provider.fetch_funding_history(symbol, start_time)

                        if history:
                            events = normalizer.normalize_funding_history(
                                provider.venue, symbol, history
                            )
                            for event in events:
                                # Just update snapshotter, don't flood Redis
                                snapshotter.process_event(event)
                                await redis_client.append_feature_timeseries(
                                    event.venue,
                                    event.symbol,
                                    "hl_funding_hourly_rate",
                                    float(event.value.get("rate", 0)),
                                    event.ts,
                                    feature_sampling_intervals[
                                        "hl_funding_hourly_rate"
                                    ],
                                )

                    except Exception as e:
                        logger.error(f"Error fetching funding history: {e}")

            await asyncio.sleep(POLL_INTERVAL_FUNDING_HISTORY / 1000)

        except asyncio.CancelledError:
            logger.info("Funding history poller cancelled")
            break
        except Exception as e:
            logger.error(f"Funding history poller error: {e}")
            await asyncio.sleep(60)
