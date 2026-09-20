"""The regime summary for one market: the condition, the evidence behind it, and why confidence is not higher.

``GET /state/market/regime-summary?symbol=`` gathers the market-data snapshot
for one market and the regime labels already stored against that market's
opportunities, and hands both to ``tradesync_core.regime_summary.summarize``.
The assembly is pure and tested there; this module only fetches.

A market-data outage is **not** a 503 here. The summary's whole purpose is to
explain an unclassified regime, and "market-data did not answer" is the most
useful explanation there is, so an unreadable snapshot produces a summary whose
condition is ``unknown`` with every required input named as unread. The stored
history is read separately and a database outage likewise leaves the history
empty rather than taking the reading down with it.

Read-only: two SELECTs and one internal GET. Nothing here writes, scores or acts.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Query

from tradesync_core import normalize_symbol
from tradesync_core.regime_summary import summarize

logger = logging.getLogger("state-api")
router = APIRouter(tags=["market"])

VENUE = "hyperliquid"
HISTORY_LIMIT = 40
TIMEOUT_S = 8.0

# Newest first, one row per opportunity that has been given an entry regime.
HISTORY_SQL = """
SELECT r.regime, r.trailing_return_pct, r.lookback_minutes, r.computed_at, r.opportunity_id, o.snapshot_ts
FROM opportunity_entry_regimes r
JOIN opportunities o ON o.id = r.opportunity_id
WHERE r.symbol = $1
ORDER BY o.snapshot_ts DESC
LIMIT $2
"""


async def read_snapshot(market_data_url: str, symbol: str) -> dict[str, Any] | None:
    """One market's snapshot, or None when market-data cannot be read."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, trust_env=False) as client:
            response = await client.get(f"{market_data_url}/snapshot/{VENUE}/{symbol}")
            if response.status_code != 200:
                return None
            body = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return body if isinstance(body, dict) and body.get("symbol") else None


async def read_history(pool, symbol: str) -> list[dict[str, Any]]:
    """The stored entry-regime labels for this market, newest first; empty when they cannot be read."""
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(HISTORY_SQL, symbol, HISTORY_LIMIT)
    except Exception as exc:  # the reading still stands without its history
        logger.warning(f"regime history unavailable for {symbol}: {type(exc).__name__}", extra={"trace_id": "regime-summary"})
        return []
    return [
        {
            "regime": row["regime"],
            "trailing_return_pct": row["trailing_return_pct"],
            "lookback_minutes": row["lookback_minutes"],
            "computed_at_ms": int(row["computed_at"].timestamp() * 1000) if row["computed_at"] else None,
            "opportunity_id": str(row["opportunity_id"]),
        }
        for row in rows
    ]


def register(app, state, *, market_data_url: str) -> None:
    @router.get("/state/market/regime-summary")
    async def regime_summary(symbol: str = Query("BTC-PERP", max_length=24)):
        symbol = normalize_symbol(symbol)
        snapshot = await read_snapshot(market_data_url, symbol)
        history = await read_history(getattr(state, "pool", None), symbol)
        return summarize(
            symbol=symbol,
            venue=VENUE,
            snapshot=snapshot,
            history=history,
            now_ms=int(time.time() * 1000),
        )

    app.include_router(router)
