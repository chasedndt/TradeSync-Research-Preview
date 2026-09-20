"""What the charts draw: candles, the context beside them, books and liquidations.

Moved out of ``app/main.py`` unchanged. Every response here states
``authority: display_only`` where it already did: a chart must never become a
source of scoring authority.
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from . import binance_liquidations, book_history, liquidation_context, liquidation_events
from .candles import (
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    SUPPORTED_INTERVALS,
    CandleRequestError,
    normalize_candles,
    resolve_window,
)
from .context_series import bucket_series, describe_coverage
from .depth import summarise_book
from .redis_client import redis_client
from .runtime import SYMBOLS, depth_books, open_interest_history, providers
from .stream_candles import candles_for

router = APIRouter()


@router.get("/candles/{venue}/{symbol}")
async def get_candles(
    venue: str,
    symbol: str,
    interval: str = DEFAULT_INTERVAL,
    limit: int = DEFAULT_LIMIT,
    start_ms: int | None = None,
    end_ms: int | None = None,
):
    """Return venue OHLCV candles for the Market Canvas and outcome measurement.

    Display and annotation only. These never enter the feature catalog, so a
    chart cannot become a source of scoring authority.

    ``start_ms``/``end_ms`` select an explicit range instead of the latest
    ``limit`` candles, for measurements that need a window older than the
    most recent history.
    """
    if venue != "hyperliquid":
        return JSONResponse(
            status_code=404,
            content={"error": "unsupported_venue", "venue": venue},
        )

    explicit_range = start_ms is not None or end_ms is not None
    try:
        resolved_interval, resolved_limit, start_ms, end_ms = resolve_window(
            interval, limit, start_ms=start_ms, end_ms=end_ms
        )
    except CandleRequestError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "detail": str(exc),
                "supported_intervals": list(SUPPORTED_INTERVALS),
            },
        )

    provider = next((p for p in providers if p.venue == venue and p.enabled), None)
    if provider is None:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unavailable", "venue": venue},
        )

    # The market stream's held candles when they answer the whole request (app/stream_candles.py).
    raw, source = await candles_for(provider, symbol, resolved_interval, resolved_limit, start_ms, end_ms,
                                    explicit_range=explicit_range)
    candles = normalize_candles(raw)
    return {
        "venue": venue,
        "symbol": symbol,
        "interval": resolved_interval,
        "requested": resolved_limit,
        "count": len(candles),
        "candles": candles,
        "source": source,
        # Stated on every response so a consumer cannot mistake a chart for a
        # scoring input.
        "authority": "display_only",
    }


@router.get("/context/{venue}/{symbol}")
async def get_canvas_context(
    venue: str,
    symbol: str,
    interval: str = DEFAULT_INTERVAL,
    limit: int = DEFAULT_LIMIT,
):
    """Funding and open interest aligned to the candles the canvas is drawing.

    Two sources with two different reaches, reported separately rather than
    blended into one line:

    - **Funding** comes from the venue's own ``fundingHistory``. It is hourly,
      authoritative, and available for as far back as the chart goes.
    - **Open interest** comes from our own context poller. Hyperliquid publishes
      only the current value, so there is no history to ask for; ours is a
      rolling 24 hours and stops there. The response says how much of the
      window it actually covers so the pane can state the limit instead of
      drawing a line that quietly ends.

    Display only. Neither series enters the feature catalog from here.
    """
    if venue != "hyperliquid":
        return JSONResponse(
            status_code=404,
            content={"error": "unsupported_venue", "venue": venue},
        )

    try:
        resolved_interval, resolved_limit, start_ms, end_ms = resolve_window(
            interval, limit
        )
    except CandleRequestError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "detail": str(exc),
                "supported_intervals": list(SUPPORTED_INTERVALS),
            },
        )

    provider = next((p for p in providers if p.venue == venue and p.enabled), None)
    if provider is None:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unavailable", "venue": venue},
        )

    bucket_s = SUPPORTED_INTERVALS[resolved_interval] // 1000
    candle_times = [
        (start_ms // 1000 // bucket_s) * bucket_s + index * bucket_s
        for index in range(resolved_limit + 1)
    ]

    # Funding is published once an hour. Judged against 15m candles it can never
    # score above 25% however complete it is, which would read as a data problem
    # that does not exist. It is measured against its own hourly grid instead;
    # open interest, which really is sampled per candle, keeps the candle grid.
    FUNDING_PERIOD_S = 3600
    funding_times = (
        candle_times
        if bucket_s >= FUNDING_PERIOD_S
        else [
            (start_ms // 1000 // FUNDING_PERIOD_S) * FUNDING_PERIOD_S
            + index * FUNDING_PERIOD_S
            for index in range((resolved_limit * bucket_s) // FUNDING_PERIOD_S + 1)
        ]
    )

    # Funding is a flow: over a bucket wider than an hour the meaningful number
    # is the total paid, not one hour of it picked out of the middle.
    # Paged across the whole window (Hyperliquid returns 500 rows per request) and cached per market.
    funding_raw = await provider.fetch_funding_history(symbol, start_ms, end_ms)
    funding = bucket_series(
        funding_raw,
        bucket_s,
        statistic="sum" if bucket_s > 3600 else "last",
        value_key="rate",
    )

    # Open interest is a level: the value standing at the close of the bucket.
    # The poller writes several identical points per poll, so "last" is also
    # what removes that duplication.
    oi_raw = await redis_client.get_timeseries(
        venue, symbol, "oi", end_ms - start_ms
    )
    open_interest = bucket_series(oi_raw, bucket_s, statistic="last")

    return {
        "venue": venue,
        "symbol": symbol,
        "interval": resolved_interval,
        "bucket_s": bucket_s,
        "funding": {
            "series": funding,
            "unit": "rate_per_hour" if bucket_s <= 3600 else "rate_summed_over_bucket",
            "source": "hyperliquid fundingHistory",
            "native_period_s": FUNDING_PERIOD_S,
            "coverage": describe_coverage(funding, funding_times),
        },
        "open_interest": {
            "series": open_interest,
            "unit": "usd",
            "source": "market-data context poller (rolling 24h)",
            "coverage": describe_coverage(open_interest, candle_times),
            "limit_note": (
                "Hyperliquid publishes only current open interest, so this is "
                "our own recording and reaches back at most 24 hours."
            ),
        },
        "authority": "display_only",
    }


@router.get("/depth/{venue}/{symbol}")
async def get_depth(venue: str, symbol: str):
    """The current L2 book as a cumulative ladder, plus any resting walls.

    A single poll, not a series: the book is replaced wholesale each time, so
    there is nothing here to draw across past candles.
    """
    if venue != "hyperliquid":
        return JSONResponse(
            status_code=404,
            content={"error": "unsupported_venue", "venue": venue},
        )

    provider = next((p for p in providers if p.venue == venue and p.enabled), None)
    if provider is None:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unavailable", "venue": venue},
        )

    book = summarise_book(await provider.fetch_orderbook(symbol))
    if book is None:
        return JSONResponse(
            status_code=503,
            content={
                "error": "book_unavailable",
                "venue": venue,
                "symbol": symbol,
                "detail": "The venue did not return a book; none is reconstructed.",
            },
        )
    return book


@router.get("/book-history/{symbol}")
async def get_book_history(symbol: str):
    if symbol not in SYMBOLS:
        return JSONResponse(status_code=404, content={"error": "unsupported_symbol"})
    return await book_history.history(redis_client.client, symbol)


@router.get("/liquidation-context/{symbol}")
async def get_liquidation_context(symbol: str):
    if symbol not in SYMBOLS:
        return JSONResponse(status_code=404, content={"error": "unsupported_symbol"})
    return await liquidation_context.history(redis_client.client, symbol)


@router.get("/depth-books/{symbol}")
async def get_depth_books(symbol: str):
    """The latest aggregated Hyperliquid books (nSigFigs 2 and 3) for one market."""
    if symbol not in SYMBOLS:
        return JSONResponse(status_code=404, content={"error": "untracked_symbol", "symbol": symbol})
    return {"venue": "hyperliquid", "symbol": symbol, "books": depth_books.latest(symbol.replace('-PERP', '')),
            "authority": "display_only",
            "note": "Resting orders as displayed, aggregated to 2 and 3 significant figures. Orders can be cancelled; not executable depth."}


@router.get("/liquidation-events/{symbol}")
async def get_liquidation_events(symbol: str):
    """Liquidations received from Bybit and Binance in the last hour, in one shape."""
    bybit = await liquidation_context.history(redis_client.client, symbol)
    binance = await binance_liquidations.history(redis_client.client, symbol)
    return liquidation_events.merged(symbol, bybit, binance)


@router.get("/open-interest-history/binance/{symbol}")
async def get_binance_open_interest_history(symbol: str, period: str = "1h", limit: int = 500):
    """Binance aggregated open-interest history (context for the estimated liquidation map)."""
    try:
        return await open_interest_history.get(symbol, period, limit)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": "invalid_request", "detail": str(exc)})
    except httpx.HTTPError as exc:
        return JSONResponse(status_code=502, content={"error": "provider_unavailable", "detail": type(exc).__name__})
