"""The context variables read from the evidence frozen at an entry.

``paper_entry_evidence`` freezes nine items at every managed paper entry and
proves that none of them was observed or received afterwards. Until now only one
of them was ever measured against what happened next (the Hyperliquid
book-history sample, in ``source_comparison``). These are the rest, reduced to
one number each:

- **resting liquidity**: the displayed bid/ask balance near price, and the size
  of the single largest resting level on each side;
- **liquidations received**: which side was being forced out in the hour before
  the entry;
- **open interest**: how much it changed in the hour before the entry;
- **funding**: the rate the position would pay or receive, per hour;
- **timeframe measurement**: whether the measured lean agrees with the call.

Each variable is computed from plain inputs, so the same definition serves a
frozen evidence document and a reading reconstructed from TradeSync's recorded
history at a past entry time. Nothing here reads a live source: a value exists
only where the frozen or recorded evidence holds one, and is ``None`` otherwise.

**Alignment.** A variable marked aligned is signed by the call's own direction,
so positive always means "this context points the way the call did". A raw
variable has no direction of its own (open interest rises whoever is buying) and
is left unsigned; its declaration says which sign it is testing.

Nothing here scores, weights or promotes anything.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "entry-evidence-context-v1"

LONG, SHORT = "long", "short"


def _side_sign(side: Any) -> int | None:
    """+1 for a long, -1 for a short; None for anything else, which measures nothing."""
    if isinstance(side, str):
        lowered = side.strip().lower()
        if lowered in (LONG, "buy"):
            return 1
        if lowered in (SHORT, "sell"):
            return -1
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return float(value)


def book_imbalance(walls: Mapping[str, Any] | None, side: Any) -> float | None:
    """Displayed bid notional minus ask notional over their sum, near price, signed by the call.

    ``walls`` is the reading ``liquidity_heatmap.walls`` produces and the entry
    evidence stores: totals within 5% of mid from one aggregated book. Displayed
    orders can be cancelled, so this is advertised depth, not executable depth.
    """
    sign = _side_sign(side)
    if sign is None or not isinstance(walls, Mapping):
        return None
    imbalance = _number(walls.get("imbalance"))
    return None if imbalance is None else imbalance * sign


def wall_asymmetry(walls: Mapping[str, Any] | None, side: Any) -> float | None:
    """The largest single resting level behind the call minus the one in front of it, over their sum.

    The imbalance above totals every level near price; this asks a narrower
    question: is the biggest wall supporting the trade or standing in its way.
    """
    sign = _side_sign(side)
    if sign is None or not isinstance(walls, Mapping):
        return None
    below, above = walls.get("below"), walls.get("above")
    support = _number(below.get("usd")) if isinstance(below, Mapping) else None
    resistance = _number(above.get("usd")) if isinstance(above, Mapping) else None
    if support is None or resistance is None or support < 0 or resistance < 0:
        return None
    total = support + resistance
    if total <= 0:
        return None
    return (support - resistance) / total * sign


def liquidation_skew(long_usd: Any, short_usd: Any, side: Any) -> float | None:
    """Forced selling minus forced buying over their sum, signed by the call.

    A liquidated long is a forced sale, so a positive raw skew is selling
    pressure. Aligned, it reads positive when the side being forced out was
    pushing price the way the call was pointing. Coverage is other venues'
    feeds: Hyperliquid publishes no market-wide liquidation stream, so an empty
    hour is "nothing received", never "nothing happened".
    """
    sign = _side_sign(side)
    longs, shorts = _number(long_usd), _number(short_usd)
    if sign is None or longs is None or shorts is None or longs < 0 or shorts < 0:
        return None
    total = longs + shorts
    if total <= 0:
        return None
    # Forced selling (liquidated longs) points down, so it aligns with a short.
    return (longs - shorts) / total * -sign


def open_interest_change_pct(latest: Any, earlier: Any) -> float | None:
    """Percentage change in open interest over the hour before the entry.

    Raw, not aligned: open interest rises when positions are opened on either
    side. The declaration says which sign it is testing.
    """
    now, before = _number(latest), _number(earlier)
    if now is None or before is None or before <= 0:
        return None
    return (now - before) / before * 100.0


def funding_received_bps_hour(rate: Any, side: Any) -> float | None:
    """Basis points an hour the position would receive; negative when it pays.

    Hyperliquid's hourly rate is positive when longs pay shorts. This is the
    rate known at the entry, not what was settled afterwards.
    """
    sign = _side_sign(side)
    hourly = _number(rate)
    if sign is None or hourly is None:
        return None
    return -hourly * sign * 10_000.0


LEANS = {"long": 1, "bullish": 1, "up": 1, "short": -1, "bearish": -1, "down": -1, "flat": 0, "neutral": 0, "none": 0}


def horizon_lean_alignment(lean: Any, side: Any) -> float | None:
    """+1 when the measured timeframe lean agrees with the call, -1 when it opposes, 0 when flat."""
    sign = _side_sign(side)
    if sign is None or not isinstance(lean, str):
        return None
    reading = LEANS.get(lean.strip().lower())
    return None if reading is None else float(reading * sign)


def _records(document: Mapping[str, Any], item: str) -> list[Mapping[str, Any]]:
    items = document.get("items") if isinstance(document, Mapping) else None
    entry = items.get(item) if isinstance(items, Mapping) else None
    records = entry.get("records") if isinstance(entry, Mapping) else None
    return [record for record in records or [] if isinstance(record, Mapping)]


def liquidation_totals(records: Iterable[Mapping[str, Any]]) -> tuple[float, float]:
    """Notional liquidated on each side, as (long, short); unusable rows are left out."""
    totals = {LONG: 0.0, SHORT: 0.0}
    for record in records:
        side, notional = record.get("side") or record.get("position_side"), _number(record.get("notional_usd"))
        if side in totals and notional is not None and notional > 0:
            totals[side] += notional
    return totals[LONG], totals[SHORT]


def from_document(document: Mapping[str, Any], side: Any) -> dict[str, float | None]:
    """Every context variable read from one frozen entry-evidence document.

    Only records the document kept are read: anything observed or received after
    the entry was already excluded when the document was built, and an item that
    never arrived is a missing marker, which reads here as an absent value.
    """
    resting = _records(document, "resting_liquidity")
    # The recorded book is the one both populations have; the entry book exists
    # only for a live entry, so the recorded reading is the comparable one.
    recorded = next((record for record in resting if record.get("id") == "recorded_book"), None)
    walls = (recorded or (resting[0] if resting else {})).get("walls")
    interest = {record.get("reading"): record for record in _records(document, "open_interest")}
    latest, earlier = interest.get("latest"), interest.get("an hour earlier")
    horizons = [
        horizon
        for record in _records(document, "horizon_measurement")
        for horizon in record.get("horizons") or []
        if isinstance(horizon, Mapping)
    ]
    return from_parts(
        walls=walls if isinstance(walls, Mapping) else None,
        liquidations=liquidation_totals(_records(document, "liquidations")),
        open_interest_latest=(latest or {}).get("open_interest_usd"),
        open_interest_earlier=(earlier or {}).get("open_interest_usd"),
        funding_rate=(latest or {}).get("predicted_funding_rate"),
        lean=next((horizon.get("lean") for horizon in horizons if isinstance(horizon.get("lean"), str)), None),
        side=side,
    )


def from_parts(
    *,
    walls: Mapping[str, Any] | None,
    liquidations: tuple[float, float] | None,
    open_interest_latest: Any,
    open_interest_earlier: Any,
    funding_rate: Any,
    lean: Any,
    side: Any,
) -> dict[str, float | None]:
    """Every context variable from already-gathered parts: one definition, two input paths."""
    longs, shorts = liquidations if liquidations is not None else (None, None)
    return {
        "book_imbalance": book_imbalance(walls, side),
        "wall_asymmetry": wall_asymmetry(walls, side),
        "liquidation_skew": liquidation_skew(longs, shorts, side),
        "open_interest_change_1h_pct": open_interest_change_pct(open_interest_latest, open_interest_earlier),
        "funding_received_bps_hour": funding_received_bps_hour(funding_rate, side),
        "horizon_lean": horizon_lean_alignment(lean, side),
    }
