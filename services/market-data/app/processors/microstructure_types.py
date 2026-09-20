"""The shapes a microstructure derivation returns.

Moved out of ``processors/microstructure.py`` unchanged, so the derivation, the
book-walking arithmetic and these results can each be read on their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class DepthSlice:
    """Depth at a specific BPS distance from mid price."""
    bid_usd: float = 0.0
    ask_usd: float = 0.0
    total_usd: float = 0.0


@dataclass
class ImpactEstimate:
    """Estimated price impact for a given order size."""
    size_usd: float = 0.0
    slippage_bps: float = 0.0
    fill_levels: int = 0
    avg_fill_price: float = 0.0


@dataclass
class HeatmapLevel:
    """Single level in the book heatmap."""
    price: float
    side: str  # "bid" or "ask"
    size_usd: float


@dataclass
class MicrostructureResult:
    """Complete microstructure derivation result."""
    spread_bps: float
    mid_price: float
    depth_usd: Dict[str, float]  # {"10bp": x, "25bp": y, "50bp": z}
    impact_est_bps: Dict[str, float]  # {"1000": x, "5000": y, "10000": z}
    liquidity_score: float
    book_heatmap: List[HeatmapLevel]
    available: bool = True
    note: Optional[str] = None
