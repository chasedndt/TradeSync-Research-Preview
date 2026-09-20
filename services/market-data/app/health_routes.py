"""Liveness, readiness and service status.

Moved out of ``app/main.py`` unchanged. Liveness and readiness stay separate on
purpose: a healthcheck that only proves the port is open will lie at exactly the
moment the truth matters.
"""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .http_clients import clients as http_clients
from .rate_limiter import rate_limiters
from .redis_client import redis_client
from .runtime import (
    READINESS_GRACE_SECONDS,
    SNAPSHOT_STALE_AFTER_SECONDS,
    SYMBOLS,
    _started_at,
    providers,
)
from .stream_status import stream_report

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Liveness only: the process is up and serving.

    Deliberately does not assert data freshness. Use /readyz for that; keeping
    the two separate means a stale-data condition is visible as exactly that,
    rather than looking like a dead process.
    """
    return {"ok": True, "service": "market-data"}


async def readiness_report() -> dict:
    """Whether this service is actually doing its job.

    On 2026-09-07 the pollers stopped for an hour while Redis refused writes.
    `/healthz` answered 200 throughout and Docker reported the container
    healthy, so the outage was invisible until the dashboard was inspected by
    hand. A healthcheck that only proves the port is open will lie at exactly
    the moment the truth matters.
    """
    now = time.time()
    symbols: list[dict] = []
    stale: list[str] = []
    missing: list[str] = []

    for symbol in SYMBOLS:
        snapshot = None
        try:
            snapshot = await redis_client.get_snapshot("hyperliquid", symbol)
        except Exception as exc:  # transport failure is itself unreadiness
            symbols.append({"symbol": symbol, "state": "unreadable", "reason": str(exc)})
            missing.append(symbol)
            continue
        if not snapshot or not snapshot.get("ts"):
            symbols.append({"symbol": symbol, "state": "missing"})
            missing.append(symbol)
            continue
        age = round(now - snapshot["ts"] / 1000, 1)
        state = "fresh" if age <= SNAPSHOT_STALE_AFTER_SECONDS else "stale"
        if state == "stale":
            stale.append(symbol)
        symbols.append({"symbol": symbol, "state": state, "age_seconds": age})

    uptime = now - _started_at
    starting = uptime < READINESS_GRACE_SECONDS and (stale or missing)
    ready = not stale and not missing
    # Freshness of the Hyperliquid market stream. A stale stream degrades the
    # service without making it unready: REST answers for the markets it misses.
    stream = stream_report(int(now * 1000))

    return {
        "ready": ready or starting,
        "starting": bool(starting),
        "degraded": stream["degraded"],
        "market_stream": stream,
        "reason": (
            ""
            if ready
            else "within startup grace period"
            if starting
            else f"stale: {', '.join(stale)}" if stale and not missing
            else f"missing: {', '.join(missing)}" if missing and not stale
            else f"stale: {', '.join(stale)}; missing: {', '.join(missing)}"
        ),
        "stale_after_seconds": SNAPSHOT_STALE_AFTER_SECONDS,
        "uptime_seconds": round(uptime, 1),
        "symbols": symbols,
    }


@router.get("/readyz")
async def readyz():
    """Readiness: fresh market observations are actually being stored."""
    report = await readiness_report()
    if not report["ready"]:
        return JSONResponse(status_code=503, content=report)
    return report


@router.get("/status")
async def status():
    """Get service status."""
    return {
        "providers": [
            {
                "venue": p.venue,
                "enabled": p.enabled,
                "metrics": p.get_supported_metrics()
            }
            for p in providers
        ],
        "symbols": SYMBOLS,
        "rate_limiters": rate_limiters.status(),
        # One pooled client per provider: clients_created stays at 1 while connections are reused.
        "http_clients": http_clients.status(),
    }
