"""Normalize read-only position rows for opportunity-scoring context."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def exposure_snapshot(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return absolute notional by symbol from honest position rows.

    Margin utilization is deliberately absent: the positions endpoint does not
    publish account equity or margin use, and zero would falsely claim it does.
    Malformed rows are ignored rather than converted into invented exposure.
    """
    by_symbol: dict[str, float] = {}
    for row in rows:
        symbol = row.get("symbol")
        notional = row.get("size_usd")
        if not isinstance(symbol, str) or not symbol.strip() or isinstance(notional, bool):
            continue
        try:
            value = abs(float(notional))
        except (TypeError, ValueError, OverflowError):
            continue
        if value != value or value == float("inf"):
            continue
        key = symbol.strip().upper()
        by_symbol[key] = by_symbol.get(key, 0.0) + value
    return {"by_symbol": by_symbol, "gross_exposure_usd": sum(by_symbol.values())}
