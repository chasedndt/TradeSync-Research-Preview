"""Snapshots, admitted features, their history, alerts and raw timeseries.

Moved out of ``app/main.py`` unchanged. These are the observation reads: what
the venue looked like, and what the feature catalog admits from it.
"""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .feature_extractor import extract_feature_observations
from .redis_client import redis_client
from .runtime import SYMBOLS

router = APIRouter()

FEATURE_HISTORY_WINDOWS_MS = {
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
}
DEFAULT_FEATURE_HISTORY_WINDOW_MS = FEATURE_HISTORY_WINDOWS_MS["7d"]
MAX_BATCH_FEATURE_IDS = 64
# Normalization never looks further back than a feature's lookback_points
# (168 today). A 7-day series holds thousands, so callers get a bounded
# tail by default rather than the whole store.
DEFAULT_SERIES_POINTS = 250


@router.get("/snapshots")
async def get_snapshots():
    """All current snapshots, in the configured symbol order.

    Redis returns keys in an arbitrary order, and the Cockpit now derives its
    symbol list from this response instead of a constant — so the order here
    is the order the operator sees everywhere. Anything not in MARKET_SYMBOLS
    (a symbol removed from the list whose key has not expired yet) sorts last.
    """
    rank = {symbol: index for index, symbol in enumerate(SYMBOLS)}
    snapshots = sorted(
        await redis_client.get_all_snapshots(),
        key=lambda s: (rank.get(s.get("symbol"), len(rank)), s.get("symbol", "")),
    )
    # Two different ages, stated separately. ``data_age_ms`` (set by the
    # snapshotter) is the age of the oldest *metric* inside the snapshot — a
    # completeness measure. ``snapshot_age_ms`` is how long since the venue
    # was last observed for the symbol at all — a liveness measure. Mission
    # Control judged "LIVE" on the first and read a healthy feed as stale.
    now_ms = int(time.time() * 1000)
    for snapshot in snapshots:
        ts = snapshot.get("ts")
        snapshot["snapshot_age_ms"] = max(0, now_ms - int(ts)) if isinstance(ts, int) else None
    return {"snapshots": snapshots, "count": len(snapshots)}


@router.get("/snapshot/{venue}/{symbol}")
async def get_snapshot(venue: str, symbol: str):
    """Get snapshot for specific venue/symbol."""
    snapshot = await redis_client.get_snapshot(venue, symbol)
    if not snapshot:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "venue": venue, "symbol": symbol}
        )
    return snapshot


@router.get("/features/{venue}/{symbol}")
async def get_features(venue: str, symbol: str):
    """Extract current admitted feature values from the latest snapshot."""
    snapshot = await redis_client.get_snapshot(venue, symbol)
    if not snapshot:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "venue": venue, "symbol": symbol},
        )
    observations = extract_feature_observations(snapshot)
    return {
        "venue": venue,
        "symbol": symbol,
        "observations": observations,
        "count": len(observations),
    }


@router.get("/feature-histories/{venue}/{symbol}")
async def get_feature_histories(
    venue: str,
    symbol: str,
    feature_ids: str,
    window: str = "7d",
    points: int = DEFAULT_SERIES_POINTS,
):
    """Return several feature histories in one response.

    A regime evaluation needs one history per normalized feature. Fetching them
    individually costs one HTTP round trip each, per symbol, per cycle, which
    saturated this service as the catalog grew. Batching keeps that cost flat.
    """
    requested = [part.strip() for part in feature_ids.split(",") if part.strip()]
    if not requested:
        return JSONResponse(
            status_code=400,
            content={"error": "feature_ids_required", "venue": venue, "symbol": symbol},
        )
    if len(requested) > MAX_BATCH_FEATURE_IDS:
        return JSONResponse(
            status_code=400,
            content={
                "error": "too_many_feature_ids",
                "limit": MAX_BATCH_FEATURE_IDS,
                "requested": len(requested),
            },
        )

    window_ms = FEATURE_HISTORY_WINDOWS_MS.get(
        window, DEFAULT_FEATURE_HISTORY_WINDOW_MS
    )
    series = {}
    for feature_id in requested:
        series[feature_id] = await redis_client.get_feature_timeseries(
            venue, symbol, feature_id, window_ms, limit=points
        )
    return {
        "venue": venue,
        "symbol": symbol,
        "window": window,
        "points": points,
        "series": series,
        "count": len(series),
    }


@router.get("/feature-history/{venue}/{symbol}/{feature_id}")
async def get_feature_history(
    venue: str,
    symbol: str,
    feature_id: str,
    window: str = "7d",
    points: int = 0,
):
    """Return cadence-governed feature history used by the shared normalizer.

    ``points`` bounds the response to the most recent N samples; 0 keeps the
    whole window, which remains useful for inspection and replay.
    """
    window_ms = FEATURE_HISTORY_WINDOWS_MS.get(
        window, DEFAULT_FEATURE_HISTORY_WINDOW_MS
    )
    data = await redis_client.get_feature_timeseries(
        venue, symbol, feature_id, window_ms, limit=points or None
    )
    return {
        "venue": venue,
        "symbol": symbol,
        "feature_id": feature_id,
        "window": window,
        "data": data,
        "count": len(data),
    }


@router.get("/alerts")
async def get_alerts(limit: int = 50):
    """Get recent market alerts.

    An unreadable stream answers 503, never an empty list: "no alert" and
    "could not read the alerts" must not look the same to the caller.
    """
    try:
        alerts = await redis_client.get_alerts(limit)
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"error": "alert_stream_unreadable", "detail": "The market alert stream could not be read"},
        )
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/timeseries/{venue}/{symbol}/{metric}")
async def get_timeseries(
    venue: str,
    symbol: str,
    metric: str,
    window: str = "1h"
):
    """Get timeseries data for metric."""
    window_ms = {
        "5m": 5 * 60 * 1000,
        "15m": 15 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
        "24h": 24 * 60 * 60 * 1000,
    }.get(window, 60 * 60 * 1000)

    data = await redis_client.get_timeseries(venue, symbol, metric, window_ms)
    return {
        "venue": venue,
        "symbol": symbol,
        "metric": metric,
        "window": window,
        "data": data,
        "count": len(data)
    }
