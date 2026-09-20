"""Turning one Hyperliquid asset context into the provider's context entry.

Moved out of ``providers/hyperliquid.py``, so the REST poll (``metaAndAssetCtxs``)
and the market stream (``activeAssetCtx``) build the entry the normalizer reads
from the same fields, rather than two copies that could disagree. ``source`` names
the endpoint the context arrived on; the REST poll alone carries asset metadata.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

REST_SOURCE = "metaAndAssetCtxs"
STREAM_SOURCE = "ws:activeAssetCtx"


def context_entry(
    venue: str,
    canonical: str,
    venue_symbol: str,
    ctx: Dict[str, Any],
    poll_ts: int,
    asset_info: Optional[Dict[str, Any]],
    source: str = REST_SOURCE,
) -> Dict[str, Any]:
    """One symbol's funding, open interest, volume and price from an asset context."""
    entry = {
        "venue": venue,
        "symbol": canonical,
        "symbol_raw": venue_symbol,
        "poll_ts": poll_ts,
        "funding": {
            "rate": float(ctx.get("funding", 0)),
            "source": source
        },
        "oi": {
            "value": float(ctx.get("openInterest", 0)),
            "unit": "asset",  # HL reports in asset units
            "source": source
        },
        "volume": {
            "value_24h": float(ctx.get("dayNtlVlm", 0)),
            "unit": "usd",
            "source": source
        },
        "price": {
            "mark": float(ctx.get("markPx", 0)),
            "oracle": float(ctx.get("oraclePx", 0)),
            "premium": float(ctx.get("premium", 0)),
            # Venue-published reference for the previous day, from
            # the same response as the mark. The 24h change is
            # derived from these two together, never guessed.
            "prev_day": float(ctx.get("prevDayPx", 0) or 0),
        },
    }
    if asset_info is not None:
        entry["meta"] = {
            "max_leverage": asset_info.get("maxLeverage", 50),
            "sz_decimals": asset_info.get("szDecimals", 5)
        }
    return entry
