"""Reading an order book: level accessors, depth within a distance, and the walk.

Moved out of ``processors/microstructure.py`` unchanged. This is displayed
resting size, not executable depth — orders can be cancelled — so everything
here is an estimate from what the venue showed at that moment.
"""

from __future__ import annotations

from typing import Dict, List

from .microstructure_types import ImpactEstimate


def price_of(level: Dict) -> float:
    """Extract price from a level dict, handling various formats."""
    if isinstance(level, dict):
        return float(level.get("price", 0) or level.get("px", 0) or 0)
    return 0


def level_usd(level: Dict) -> float:
    """Extract USD size from a level dict, handling various formats."""
    if isinstance(level, dict):
        # Try direct size_usd first
        if "size_usd" in level:
            return float(level["size_usd"] or 0)

        # Otherwise compute from price * size
        price = price_of(level)
        size = float(level.get("size", 0) or level.get("sz", 0) or 0)
        return price * size
    return 0


def compute_depth_slices(
    bids: List[Dict],
    asks: List[Dict],
    mid_price: float,
    thresholds_bps: List[int],
) -> Dict[str, float]:
    """
    Compute depth in USD at various BPS thresholds from mid price.

    For each threshold (10bp, 25bp, 50bp), sum the USD depth on both sides
    of the book within that distance from mid.
    """
    depth_usd = {}

    for threshold_bps in thresholds_bps:
        threshold_ratio = threshold_bps / 10000  # Convert bps to ratio

        bid_threshold = mid_price * (1 - threshold_ratio)
        ask_threshold = mid_price * (1 + threshold_ratio)

        # Sum bid depth (prices >= bid_threshold)
        bid_depth = sum(
            level_usd(level)
            for level in bids
            if price_of(level) >= bid_threshold
        )

        # Sum ask depth (prices <= ask_threshold)
        ask_depth = sum(
            level_usd(level)
            for level in asks
            if price_of(level) <= ask_threshold
        )

        depth_usd[f"{threshold_bps}bp"] = round(bid_depth + ask_depth, 2)

    return depth_usd


def compute_impact_estimates(
    asks: List[Dict],
    mid_price: float,
    sizes_usd: List[int],
) -> Dict[str, float]:
    """
    Estimate price impact in BPS for various order sizes.

    Uses a book walk: for a buy order, walk up the asks until
    cumulative size >= order size, then compute VWAP slippage.
    """
    impact_est_bps = {}

    for size_usd in sizes_usd:
        impact = walk_book_for_impact(asks, mid_price, size_usd)
        impact_est_bps[str(size_usd)] = round(impact.slippage_bps, 2)

    return impact_est_bps


def walk_book_for_impact(
    asks: List[Dict],
    mid_price: float,
    size_usd: float,
) -> ImpactEstimate:
    """
    Walk the ask side of the book to estimate price impact.

    Returns ImpactEstimate with:
    - Number of levels consumed
    - Average fill price (VWAP)
    - Slippage from mid in BPS
    """
    if not asks or mid_price <= 0:
        return ImpactEstimate(size_usd=size_usd, slippage_bps=0)

    remaining_usd = size_usd
    total_cost = 0.0
    total_filled_usd = 0.0
    levels_consumed = 0

    # Sort asks by price ascending
    sorted_asks = sorted(asks, key=price_of)

    for level in sorted_asks:
        price = price_of(level)
        this_level_usd = level_usd(level)

        if this_level_usd <= 0 or price <= 0:
            continue

        levels_consumed += 1

        if this_level_usd >= remaining_usd:
            # Partial fill of this level
            total_cost += remaining_usd
            total_filled_usd += remaining_usd
            remaining_usd = 0
            break
        else:
            # Full fill of this level
            total_cost += this_level_usd
            total_filled_usd += this_level_usd
            remaining_usd -= this_level_usd

    if total_filled_usd <= 0:
        return ImpactEstimate(size_usd=size_usd, slippage_bps=0)

    # Calculate weighted average fill price
    # For simplicity, approximate as proportional walk through prices
    avg_fill_price = calculate_vwap(sorted_asks, total_filled_usd)

    if avg_fill_price <= 0:
        avg_fill_price = price_of(sorted_asks[0]) if sorted_asks else mid_price

    # Calculate slippage from mid
    slippage_bps = ((avg_fill_price - mid_price) / mid_price) * 10000

    return ImpactEstimate(
        size_usd=size_usd,
        slippage_bps=max(0, slippage_bps),  # Slippage should be positive for buys
        fill_levels=levels_consumed,
        avg_fill_price=avg_fill_price
    )


def calculate_vwap(
    levels: List[Dict],
    target_usd: float,
) -> float:
    """Calculate volume-weighted average price for target fill size."""
    remaining = target_usd
    weighted_sum = 0.0
    total_weight = 0.0

    for level in levels:
        price = price_of(level)
        this_level_usd = level_usd(level)

        if this_level_usd <= 0 or price <= 0:
            continue

        fill_amount = min(this_level_usd, remaining)
        weighted_sum += price * fill_amount
        total_weight += fill_amount
        remaining -= fill_amount

        if remaining <= 0:
            break

    return weighted_sum / total_weight if total_weight > 0 else 0
