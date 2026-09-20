"""Order book, derived microstructure and liquidation sections of a snapshot.

Moved out of ``processors/snapshotter.py`` unchanged. The liquidation section is
the one to read carefully: it is a **proxy** estimated from open-interest
changes, and it says so on every row it produces. Nothing here turns it into an
observed fact.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..models import (
    BookHeatmapLevel,
    LiquidationData,
    LiquidationWindow,
    MetricAvailability,
    MetricStatus,
    MicrostructureData,
    OrderbookData,
    OrderbookDepth,
)


def build_orderbook(
    data: List[Dict],
    now: int,
) -> tuple[OrderbookData, List[MetricAvailability], int]:
    """Build orderbook data."""
    latest = data[-1]
    value = latest["value"]
    data_age = now - latest.get("ts", now)

    depth = value.get("depth", {})

    orderbook_data = OrderbookData(
        spread_bps=value.get("spread_bps", 0),
        spread_usd=value.get("spread_usd", 0),
        depth=OrderbookDepth(
            bid_1pct_usd=depth.get("bid_1pct_usd", 0),
            ask_1pct_usd=depth.get("ask_1pct_usd", 0),
            bid_2pct_usd=depth.get("bid_2pct_usd", 0),
            ask_2pct_usd=depth.get("ask_2pct_usd", 0)
        ),
        imbalance_1pct=value.get("imbalance_1pct", 0),
        best_bid=value.get("best_bid", 0),
        best_ask=value.get("best_ask", 0),
        mid_price=value.get("mid_price", 0),
        book_age_ms=data_age
    )

    status = MetricStatus(latest.get("status", "REAL"))
    metrics = [MetricAvailability(
        metric="orderbook",
        status=status,
        source=latest.get("source", {}).get("provider"),
        last_updated=latest.get("ts")
    )]

    return orderbook_data, metrics, data_age


def build_microstructure(
    orderbook_data_list: List[Dict],
    orderbook: Optional[OrderbookData],
    deriver,
) -> tuple[Optional[MicrostructureData], List[MetricAvailability]]:
    """
    Build microstructure data from orderbook (Phase 3C).

    Derives:
    - Depth at 10/25/50 bps thresholds
    - Price impact estimates for 1k/5k/10k orders
    - Liquidity score
    - Heatmap visualization data
    """
    if not orderbook_data_list or not orderbook:
        return None, []

    latest = orderbook_data_list[-1]
    value = latest.get("value", {})

    # Get raw bids/asks if available in the window data
    bids = value.get("bids", [])
    asks = value.get("asks", [])

    # Build input for microstructure deriver
    orderbook_input = {
        "best_bid": orderbook.best_bid,
        "best_ask": orderbook.best_ask,
        "mid_price": orderbook.mid_price,
        "spread_bps": orderbook.spread_bps,
        "bids": bids,
        "asks": asks
    }

    # Derive microstructure
    result = deriver.derive(orderbook_input)

    if not result.available:
        return None, [MetricAvailability(
            metric="microstructure",
            status=MetricStatus.UNAVAILABLE,
            note=result.note or "Microstructure derivation unavailable"
        )]

    # Convert to Pydantic models
    heatmap_levels = [
        BookHeatmapLevel(
            price=level.price,
            side=level.side,
            size_usd=level.size_usd
        )
        for level in result.book_heatmap
    ]

    microstructure = MicrostructureData(
        spread_bps=result.spread_bps,
        mid_price=result.mid_price,
        depth_usd=result.depth_usd,
        impact_est_bps=result.impact_est_bps,
        liquidity_score=result.liquidity_score,
        book_heatmap=heatmap_levels
    )

    metrics = [MetricAvailability(
        metric="microstructure",
        status=MetricStatus.DERIVED,
        source="orderbook_derived",
        note="Derived from orderbook data",
        last_updated=latest.get("ts")
    )]

    return microstructure, metrics


def build_liquidations(
    data: List[Dict],
    now: int,
    windows: Dict[str, int],
) -> tuple[LiquidationData, List[MetricAvailability], int]:
    """Build liquidation data (typically proxy)."""
    latest = data[-1]
    value = latest["value"]
    data_age = now - latest.get("ts", now)

    # Build horizon windows from accumulated data
    horizons = {}
    for window_name in ["5m", "1h", "4h", "24h"]:
        window_ms = windows.get(window_name, 0)
        cutoff = now - window_ms
        window_data = [d for d in data if d.get("ts", 0) > cutoff]

        total = sum(d["value"].get("estimated_total_usd", 0) for d in window_data)
        horizons[window_name] = LiquidationWindow(
            longs_usd=total * 0.5,  # Rough split
            shorts_usd=total * 0.5,
            total_usd=total,
            dominant_side="balanced"
        )

    liq_data = LiquidationData(
        horizons=horizons,
        source_note=value.get("note", "PROXY: estimated from OI deltas"),
        method=value.get("method", "oi_delta_proxy")
    )

    metrics = [MetricAvailability(
        metric="liquidations",
        status=MetricStatus.PROXY,
        note="Estimated from OI changes. Real liquidation feed unavailable.",
        last_updated=latest.get("ts")
    )]

    return liq_data, metrics, data_age
