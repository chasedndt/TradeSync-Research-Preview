"""The evidence a recorded opportunity would have frozen, read as of its own entry.

No managed paper position has been opened yet, so the only population that has
both a measured outcome and evidence from before it is the recorded
opportunities. This reconstructs, for each one, the same readings a live entry
freezes, under the same rule: a row counts only if TradeSync had **observed and
received** it by the opportunity's own snapshot time. The predicates mirror
``paper_entry_rows`` one for one, including the 3-significant-figure book, the
hour of liquidations and its 500-row cap, and the open-interest reading from an
hour earlier.

What cannot be reconstructed, and is therefore absent rather than approximated:

- **the timeframe measurement**: nothing stores one. ``horizon_readings`` keeps
  Hermes's readings of the outlook, and there are none; recomputing the
  measurement now from candles fetched now would be a fact received after the
  entry, which is exactly what the cut-off exists to exclude;
- **settled funding rows**: the venue's history is fetched over HTTP and would
  likewise arrive after the entry. The funding reading used here is the rate
  TradeSync had already recorded with open interest, minute by minute;
- **features, the scorer verdict and the thesis edition**: not part of the
  declared family.

Read-only: three SELECTs, no write path.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.paper_entry_facts import decoded
from app.paper_entry_rows import LIQUIDATION_ROWS, LIQUIDATION_WINDOW_S, RESTING_SIG_FIGS
from tradesync_core import entry_evidence_context as context
from tradesync_core.liquidity_heatmap import walls

# The first moment any of this history exists. Before it, an opportunity simply
# has no evidence to read, and belongs outside the population rather than in it
# with everything missing.
HISTORY_START_SQL = """
SELECT (SELECT min(recorded_at) FROM market_depth_snapshots) AS books,
       (SELECT min(recorded_at) FROM market_open_interest) AS open_interest,
       (SELECT min(received_at) FROM market_liquidation_events) AS liquidations
"""

OUTCOMES_SQL = """
SELECT x.opportunity_id, x.symbol, x.direction, x.horizon_minutes, x.opened_at, x.signed_return_pct
FROM opportunity_outcomes x
WHERE x.status = 'measured' AND x.signed_return_pct IS NOT NULL
  AND x.direction IN ('LONG', 'SHORT')
  AND x.opened_at >= $1 AND x.opened_at > now() - make_interval(days => $2)
"""

# One row per opportunity: every reading bounded by that opportunity's own entry time.
CONTEXT_SQL = f"""
WITH calls AS (
    SELECT DISTINCT x.opportunity_id, x.symbol, x.opened_at
    FROM opportunity_outcomes x
    WHERE x.status = 'measured' AND x.signed_return_pct IS NOT NULL
      AND x.direction IN ('LONG', 'SHORT')
      AND x.opened_at >= $1 AND x.opened_at > now() - make_interval(days => $2)
)
SELECT c.opportunity_id, c.symbol,
       book.mid_price, book.bids, book.asks,
       latest.open_interest_usd AS open_interest_latest, latest.funding_rate,
       earlier.open_interest_usd AS open_interest_earlier,
       liquidations.long_usd, liquidations.short_usd, liquidations.events
FROM calls c
LEFT JOIN LATERAL (
    SELECT d.mid_price, d.bids, d.asks
    FROM market_depth_snapshots d
    WHERE d.symbol = c.symbol AND d.n_sig_figs = {RESTING_SIG_FIGS}
      AND d.recorded_at <= c.opened_at AND d.observed_at <= c.opened_at
    ORDER BY d.observed_at DESC LIMIT 1
) book ON true
LEFT JOIN LATERAL (
    SELECT o.open_interest_usd, o.funding_rate, o.observed_at
    FROM market_open_interest o
    WHERE o.symbol = c.symbol AND o.recorded_at <= c.opened_at AND o.observed_at <= c.opened_at
    ORDER BY o.observed_at DESC LIMIT 1
) latest ON true
LEFT JOIN LATERAL (
    SELECT o.open_interest_usd
    FROM market_open_interest o
    WHERE o.symbol = c.symbol AND o.recorded_at <= c.opened_at
      AND o.observed_at <= latest.observed_at - interval '1 hour'
    ORDER BY o.observed_at DESC LIMIT 1
) earlier ON true
LEFT JOIN LATERAL (
    SELECT sum(e.notional_usd) FILTER (WHERE e.position_side = 'long') AS long_usd,
           sum(e.notional_usd) FILTER (WHERE e.position_side = 'short') AS short_usd,
           count(*) AS events
    FROM (
        SELECT l.position_side, l.notional_usd
        FROM market_liquidation_events l
        WHERE l.symbol = c.symbol
          AND l.event_time >= c.opened_at - make_interval(secs => {LIQUIDATION_WINDOW_S})
          AND l.event_time <= c.opened_at AND l.received_at <= c.opened_at
        ORDER BY l.event_time DESC LIMIT {LIQUIDATION_ROWS}
    ) e
) liquidations ON true
"""

SIDES = {"LONG": "long", "SHORT": "short"}

SOURCES = {
    "book_imbalance": "market_depth_snapshots recorded before the entry, 3 significant figures",
    "wall_asymmetry": "market_depth_snapshots recorded before the entry, 3 significant figures",
    "liquidation_skew": f"market_liquidation_events received in the {LIQUIDATION_WINDOW_S // 3600} h before the entry",
    "open_interest_change_1h_pct": "market_open_interest recorded before the entry, and an hour earlier",
    "funding_received_bps_hour": "market_open_interest: the rate recorded with the latest reading before the entry",
    "horizon_lean": "not stored for a past entry; only a live entry freezes one",
}


def book_walls(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """The walls reading from a recorded book, or None when no book was recorded before the entry."""
    mid, bids, asks = row.get("mid_price"), decoded(row.get("bids")), decoded(row.get("asks"))
    if not mid or not isinstance(bids, list) or not isinstance(asks, list):
        return None
    try:
        return walls(bids, asks, float(mid))
    except (TypeError, ValueError):  # a malformed recorded book reads as no book, never as a zero
        return None


def readings(rows: Sequence[Mapping[str, Any]], sides: Mapping[str, str]) -> dict[str, dict[str, float | None]]:
    """One set of context variables per opportunity, from rows bounded at its entry."""
    out: dict[str, dict[str, float | None]] = {}
    for row in rows:
        key = str(row["opportunity_id"])
        side = sides.get(key)
        if side is None:
            continue
        events = row.get("events") or 0
        out[key] = context.from_parts(
            walls=book_walls(row),
            # No liquidation received in the hour is "nothing received", never "nothing happened".
            liquidations=(row.get("long_usd") or 0.0, row.get("short_usd") or 0.0) if events else None,
            open_interest_latest=row.get("open_interest_latest"),
            open_interest_earlier=row.get("open_interest_earlier"),
            funding_rate=row.get("funding_rate"),
            lean=None,
            side=side,
        )
    return out


def coverage(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Why each reading was missing, counted, so a thin variable is visible as thin."""
    total = len(rows)
    no_book = sum(1 for row in rows if book_walls(row) is None)
    no_interest = sum(1 for row in rows if row.get("open_interest_latest") is None
                      or row.get("open_interest_earlier") is None)
    no_liquidations = sum(1 for row in rows if not (row.get("events") or 0))
    return {
        "opportunities": total,
        "no_recorded_book": no_book,
        "no_open_interest_pair": no_interest,
        "no_liquidation_received": no_liquidations,
        "no_timeframe_measurement": total,
        "sources": SOURCES,
    }
