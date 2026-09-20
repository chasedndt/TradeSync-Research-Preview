"""Measure what happened after each recorded paper opportunity.

Runs on its own cadence, separate from the producer: measuring is not part of
deciding, and a slow measurement must never delay or influence a verdict.

The job is idempotent. A horizon that is still open is written as ``pending``
and re-measured on a later pass, so restarting mid-run loses nothing.

Candles are fetched for the windows actually pending, not for "the latest N".
See ``outcome_windows`` for why: the latest-N shortcut wrote off every window
older than eight hours as having no candles, and then re-reviewed those rows
forever while the real backlog starved.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from typing import Any

import httpx

from tradesync_core.outcomes import (
    DEFAULT_HORIZONS_MINUTES,
    HorizonOutcome,
    OutcomeError,
    measure_opportunity,
)

from .outcome_features import record_entry_features
from .outcome_regime import (
    lookback_margin_s,
    missing_regime_opportunities,
    store_entry_regime,
)
from .outcome_guards import (  # noqa: F401  (re-exported: callers import these from here)
    CANDLE_SECONDS,
    COARSE_CANDLE_INTERVAL,
    COARSE_SECONDS,
    EMPTY_AT_FINE,
    INTERVAL_SECONDS,
    MEASURED_COARSE,
    MIN_HORIZON_FOR_COARSE,
    NO_FINE_HISTORY,
    NOT_FETCHED,
    OUTCOME_CANDLE_INTERVAL,
    fall_back_per_window,
    guard_coarse,
    guard_unrequested,
)
from .outcome_store import pending_opportunities, store_outcome
from .outcome_windows import (
    FetchRange,
    chunk_ranges,
    merge_candles,
    required_span_s,
    window_was_requested,
)

MARKET_DATA_URL = os.getenv("MARKET_DATA_URL", "http://market-data:8005")
OUTCOME_INTERVAL_SECONDS = int(os.getenv("OUTCOME_INTERVAL_SECONDS", "300"))
# Oldest-first with a batch this size drains an 800-row backlog in well under
# an hour while still reaching new rows within a few passes.
OUTCOME_BATCH = int(os.getenv("OUTCOME_BATCH", "120"))
LONGEST_HORIZON = max(DEFAULT_HORIZONS_MINUTES)


async def _fetch_interval(
    symbol: str, span: tuple[int, int], interval: str, client: httpx.AsyncClient
) -> tuple[list[dict[str, Any]], list[FetchRange]]:
    """One interval's candles across the span, chunked to the venue cap.

    A chunk that fails is left out of the returned ranges, so the caller can
    tell an unrequested window from an empty one.
    """
    received: list[FetchRange] = []
    batches: list[list[dict[str, Any]]] = []
    for chunk in chunk_ranges(span[0], span[1], INTERVAL_SECONDS[interval]):
        try:
            response = await client.get(
                f"{MARKET_DATA_URL}/candles/hyperliquid/{symbol}",
                params={"interval": interval, "start_ms": chunk.start_ms, "end_ms": chunk.end_ms},
                timeout=20.0,
            )
            response.raise_for_status()
            batches.append(response.json().get("candles", []))
            received.append(chunk)
        except (httpx.HTTPError, ValueError) as exc:
            # Reported per window below, as "not fetched", never as "empty".
            print(f"[Outcomes] {interval} candles unavailable for {symbol} {chunk}: {exc}")
    return merge_candles(batches), received


# Below this age the venue has been seen to still serve 1m candles (probed
# 2026-09-12: present at 72h, gone at 96h). Older spans also fetch the coarse
# series so a window the fine series no longer covers can fall back per window.
FINE_RETENTION_S = int(os.getenv("OUTCOME_FINE_RETENTION_S", str(60 * 3600)))


@dataclass
class SymbolCandles:
    fine: list[dict[str, Any]]
    fine_ranges: list[FetchRange]
    coarse: list[dict[str, Any]]
    coarse_ranges: list[FetchRange]


async def fetch_candles_for(
    symbol: str, opened_at_s: list[int], client: httpx.AsyncClient, now_s: int
) -> SymbolCandles:
    """Candles for the batch's windows: 1m always, plus 5m when the span is old.

    The coarse series is fetched alongside rather than instead, so a batch that
    straddles the venue's 1m retention boundary can measure its newer windows
    at 1m and its older ones at 5m, window by window, instead of writing the
    older ones off because the batch as a whole had some 1m data.
    """
    span = required_span_s(opened_at_s, LONGEST_HORIZON, CANDLE_SECONDS)
    if span is None:
        return SymbolCandles([], [], [], [])
    # Start an hour earlier: the entry regime is read from the candles that
    # closed before each opportunity fired, out of the same fetch.
    span = (span[0] - lookback_margin_s(CANDLE_SECONDS), span[1])
    fine, fine_ranges = await _fetch_interval(symbol, span, OUTCOME_CANDLE_INTERVAL, client)
    coarse: list[dict[str, Any]] = []
    coarse_ranges: list[FetchRange] = []
    if span[0] < now_s - FINE_RETENTION_S:
        coarse, coarse_ranges = await _fetch_interval(symbol, span, COARSE_CANDLE_INTERVAL, client)
    return SymbolCandles(fine, fine_ranges, coarse, coarse_ranges)


async def run_outcome_pass(conn) -> dict[str, int]:
    """Measure one batch. Returns counts for logging."""
    pending = await pending_opportunities(conn, OUTCOME_BATCH)
    if not pending:
        features = await record_entry_features(conn, OUTCOME_BATCH, int(time.time()))
        return {"opportunities": 0, "measured": 0, "entry_features_present": features["present"]}

    now_s = int(time.time())
    by_symbol: dict[str, list[int]] = {}
    for row in pending:
        by_symbol.setdefault(row["symbol"], []).append(int(row["snapshot_ts"].timestamp()))

    series: dict[str, SymbolCandles] = {}
    async with httpx.AsyncClient() as client:
        for symbol, opened in by_symbol.items():
            series[symbol] = await fetch_candles_for(symbol, opened, client, now_s)

    measured = 0
    for row in pending:
        opened_at_s = int(row["snapshot_ts"].timestamp())
        sc = series.get(row["symbol"]) or SymbolCandles([], [], [], [])

        def measure(candles: list[dict[str, Any]]):
            return measure_opportunity(
                opportunity_id=str(row["id"]),
                symbol=row["symbol"],
                direction=row["dir"],
                opened_at_s=opened_at_s,
                candles=candles,
                now_s=now_s,
            )

        try:
            outcome = measure(sc.fine)
            fine = guard_unrequested(outcome.horizons, sc.fine_ranges, opened_at_s)
            coarse = None
            if sc.coarse_ranges and any(
                h.status == "insufficient_candles" and h.reason == EMPTY_AT_FINE for h in fine
            ):
                coarse = guard_unrequested(measure(sc.coarse).horizons, sc.coarse_ranges, opened_at_s)
        except OutcomeError as exc:
            print(f"[Outcomes] skipping {row['id']}: {exc}")
            continue
        outcome = replace(outcome, horizons=fall_back_per_window(fine, coarse))
        await store_outcome(conn, outcome, row["symbol"], row["dir"])
        measured += sum(1 for h in outcome.horizons if h.status == "measured")
        await _record_regime(conn, row, opened_at_s, sc)

    labelled = await _backfill_regimes(conn, {str(r["id"]) for r in pending}, now_s)
    features = await record_entry_features(conn, OUTCOME_BATCH, now_s)
    return {
        "opportunities": len(pending),
        "measured": measured,
        "regimes_backfilled": labelled,
        "entry_features_present": features["present"],
        "entry_features_absent": features["absent"],
    }


async def _record_regime(conn, row, opened_at_s: int, sc: SymbolCandles) -> None:
    """Label the entry regime from whichever series covers the hour before entry."""
    if any(c["time"] < opened_at_s for c in sc.fine):
        await store_entry_regime(conn, str(row["id"]), row["symbol"], opened_at_s, sc.fine,
                                 CANDLE_SECONDS, OUTCOME_CANDLE_INTERVAL)
    elif sc.coarse:
        await store_entry_regime(conn, str(row["id"]), row["symbol"], opened_at_s, sc.coarse,
                                 COARSE_SECONDS, COARSE_CANDLE_INTERVAL)
    # No candles before entry at either interval: no row, and it is retried
    # by the backfill on a later pass rather than labelled "unknown" now.


async def _backfill_regimes(conn, skip: set[str], now_s: int) -> int:
    """Label opportunities that already have outcomes but no entry regime.

    Their outcomes are not re-measured — only the regime is added — so a fetch
    at a coarser interval today cannot change a result recorded at 1m earlier.
    """
    rows = [r for r in await missing_regime_opportunities(conn, OUTCOME_BATCH) if str(r["id"]) not in skip]
    if not rows:
        return 0
    by_symbol: dict[str, list[int]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], []).append(int(row["snapshot_ts"].timestamp()))
    series: dict[str, SymbolCandles] = {}
    async with httpx.AsyncClient() as client:
        for symbol, opened in by_symbol.items():
            series[symbol] = await fetch_candles_for(symbol, opened, client, now_s)
    labelled = 0
    for row in rows:
        sc = series.get(row["symbol"]) or SymbolCandles([], [], [], [])
        before = await conn.fetchval(
            "SELECT count(*) FROM opportunity_entry_regimes WHERE opportunity_id = $1::uuid", str(row["id"])
        )
        await _record_regime(conn, row, int(row["snapshot_ts"].timestamp()), sc)
        after = await conn.fetchval(
            "SELECT count(*) FROM opportunity_entry_regimes WHERE opportunity_id = $1::uuid", str(row["id"])
        )
        labelled += int(after) - int(before)
    return labelled
