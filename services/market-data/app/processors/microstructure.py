"""
Microstructure derivation module for Phase 3C.

Computes derived market microstructure metrics from raw orderbook data:
- Spread in basis points
- Depth at various BPS thresholds (10bp, 25bp, 50bp)
- Price impact estimates for different order sizes
- Liquidity score
- Compact book heatmap for visualization

The arithmetic that reads a book lives in ``book_walk``; the shapes returned
live in ``microstructure_types``. This module holds the thresholds, the scoring
weights, and the derivation that puts them together.
"""

import logging
from typing import Any, Dict, List

from .book_walk import compute_depth_slices, compute_impact_estimates, level_usd, price_of
from .microstructure_types import (
    DepthSlice,
    HeatmapLevel,
    ImpactEstimate,
    MicrostructureResult,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DepthSlice",
    "HeatmapLevel",
    "ImpactEstimate",
    "MicrostructureDeriver",
    "MicrostructureResult",
    "derive_microstructure",
]


class MicrostructureDeriver:
    """
    Derives microstructure metrics from raw orderbook data.

    Input: Raw orderbook with bids/asks array and basic computed metrics
    Output: MicrostructureResult with derived depth, impact, liquidity metrics
    """

    # Depth thresholds in basis points
    DEPTH_THRESHOLDS_BPS = [10, 25, 50]

    # Order sizes in USD for impact estimation
    IMPACT_SIZES_USD = [1000, 5000, 10000]

    # Max levels to include in heatmap (per side)
    HEATMAP_MAX_LEVELS = 50

    # Liquidity score weights
    SPREAD_WEIGHT = 0.4
    DEPTH_WEIGHT = 0.6

    # Reference values for score normalization
    MAX_SPREAD_BPS = 5.0  # Spread >= this gives 0 spread score
    REFERENCE_DEPTH_USD = 3_000_000  # Depth at 25bp for 100% depth score

    def derive(
        self,
        orderbook_data: Dict[str, Any]
    ) -> MicrostructureResult:
        """
        Derive microstructure metrics from orderbook data.

        Args:
            orderbook_data: Dict containing:
                - best_bid: float
                - best_ask: float
                - mid_price: float
                - spread_bps: float
                - bids: List[Dict] with {price, size, size_usd}
                - asks: List[Dict] with {price, size, size_usd}

        Returns:
            MicrostructureResult with derived metrics
        """
        try:
            # Extract basic fields
            best_bid = orderbook_data.get("best_bid", 0)
            best_ask = orderbook_data.get("best_ask", 0)
            mid_price = orderbook_data.get("mid_price", 0)
            spread_bps = orderbook_data.get("spread_bps", 0)

            bids = orderbook_data.get("bids", [])
            asks = orderbook_data.get("asks", [])

            if not mid_price or mid_price <= 0:
                return MicrostructureResult(
                    spread_bps=0,
                    mid_price=0,
                    depth_usd={},
                    impact_est_bps={},
                    liquidity_score=0,
                    book_heatmap=[],
                    available=False,
                    note="No mid price available"
                )

            # Compute depth at various thresholds
            depth_usd = compute_depth_slices(
                bids, asks, mid_price, self.DEPTH_THRESHOLDS_BPS
            )

            # Compute impact estimates
            impact_est_bps = compute_impact_estimates(
                asks, mid_price, self.IMPACT_SIZES_USD
            )

            # Compute liquidity score
            liquidity_score = self._compute_liquidity_score(
                spread_bps,
                depth_usd.get("25bp", 0)
            )

            # Build heatmap
            book_heatmap = self._build_heatmap(bids, asks)

            return MicrostructureResult(
                spread_bps=spread_bps,
                mid_price=mid_price,
                depth_usd=depth_usd,
                impact_est_bps=impact_est_bps,
                liquidity_score=liquidity_score,
                book_heatmap=book_heatmap,
                available=True
            )

        except Exception as e:
            logger.error(f"Microstructure derivation failed: {e}")
            return MicrostructureResult(
                spread_bps=0,
                mid_price=0,
                depth_usd={},
                impact_est_bps={},
                liquidity_score=0,
                book_heatmap=[],
                available=False,
                note=f"Derivation error: {str(e)}"
            )

    def _compute_liquidity_score(
        self,
        spread_bps: float,
        depth_25bp_usd: float
    ) -> float:
        """
        Compute a composite liquidity score from 0 to 1.

        Formula: 0.4 * spread_score + 0.6 * depth_score

        spread_score = 1 - min(spread_bps / MAX_SPREAD_BPS, 1.0)
        depth_score = min(depth_25bp_usd / REFERENCE_DEPTH_USD, 1.0)
        """
        # Spread score: lower spread = higher score
        spread_score = 1.0 - min(spread_bps / self.MAX_SPREAD_BPS, 1.0)

        # Depth score: higher depth = higher score
        depth_score = min(depth_25bp_usd / self.REFERENCE_DEPTH_USD, 1.0)

        liquidity_score = (
            self.SPREAD_WEIGHT * spread_score +
            self.DEPTH_WEIGHT * depth_score
        )

        return round(liquidity_score, 3)

    def _build_heatmap(
        self,
        bids: List[Dict],
        asks: List[Dict]
    ) -> List[HeatmapLevel]:
        """
        Build a compact heatmap of top N levels per side.

        Returns list of HeatmapLevel sorted by price distance from mid.
        """
        heatmap = []

        # Add top N bids (sorted by price descending = closest to mid first)
        sorted_bids = sorted(bids, key=price_of, reverse=True)
        for level in sorted_bids[:self.HEATMAP_MAX_LEVELS]:
            price = price_of(level)
            if price > 0:
                heatmap.append(HeatmapLevel(
                    price=price,
                    side="bid",
                    size_usd=round(level_usd(level), 2)
                ))

        # Add top N asks (sorted by price ascending = closest to mid first)
        sorted_asks = sorted(asks, key=price_of)
        for level in sorted_asks[:self.HEATMAP_MAX_LEVELS]:
            price = price_of(level)
            if price > 0:
                heatmap.append(HeatmapLevel(
                    price=price,
                    side="ask",
                    size_usd=round(level_usd(level), 2)
                ))

        return heatmap


# Convenience function for direct usage
def derive_microstructure(orderbook_data: Dict[str, Any]) -> MicrostructureResult:
    """
    Convenience function to derive microstructure from orderbook data.

    Args:
        orderbook_data: Dict containing orderbook with bids/asks

    Returns:
        MicrostructureResult with derived metrics
    """
    deriver = MicrostructureDeriver()
    return deriver.derive(orderbook_data)
