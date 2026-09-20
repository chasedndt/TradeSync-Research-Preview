"""The sections of a market snapshot: funding, price, open interest, liquidations, book, microstructure, volume.

Moved out of ``app/models.py`` unchanged.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .regimes import FundingRegime, OIRegime, VolumeRegime


class FundingHorizons(BaseModel):
    now: float = 0.0
    h8: float = 0.0   # 8h average
    h24: float = 0.0  # 24h average
    d3: float = 0.0   # 3d average
    d7: float = 0.0   # 7d average


class FundingSource(BaseModel):
    provider: str
    endpoint: str
    raw_rate: float


class FundingData(BaseModel):
    horizons: FundingHorizons
    annualized_24h: float = 0.0
    regime: FundingRegime = FundingRegime.NEUTRAL
    source: FundingSource


class PriceData(BaseModel):
    """Authoritative Hyperliquid mark/oracle pair from one context poll."""

    mark_price_usd: float
    oracle_price_usd: float
    oracle_premium_bps: float
    # Both stay None when the venue does not publish a usable previous-day
    # reference. A missing 24h change is displayed as unavailable rather than
    # substituted from another venue or inferred from stored history.
    prev_day_price_usd: Optional[float] = None
    change_24h_pct: Optional[float] = None


class HorizonValue(BaseModel):
    value: float = 0.0
    delta_pct: float = 0.0
    delta_usd: float = 0.0


class OpenInterestData(BaseModel):
    horizons: Dict[str, HorizonValue] = Field(default_factory=dict)
    current_usd: float = 0.0
    regime: OIRegime = OIRegime.FLAT


class LiquidationWindow(BaseModel):
    longs_usd: float = 0.0
    shorts_usd: float = 0.0
    total_usd: float = 0.0
    dominant_side: str = "balanced"


class LiquidationData(BaseModel):
    horizons: Dict[str, LiquidationWindow] = Field(default_factory=dict)
    source_note: Optional[str] = None
    method: str = "real"


class OrderbookDepth(BaseModel):
    bid_1pct_usd: float = 0.0
    ask_1pct_usd: float = 0.0
    bid_2pct_usd: float = 0.0
    ask_2pct_usd: float = 0.0


class BookHeatmapLevel(BaseModel):
    """Single level in the book heatmap visualization."""
    price: float
    side: str  # "bid" or "ask"
    size_usd: float


class MicrostructureData(BaseModel):
    """
    Derived microstructure metrics for liquidity analysis (Phase 3C).

    These fields are computed from raw orderbook data to enable:
    - Liquidity heatmap visualization
    - Slippage/impact estimation for position sizing
    - Execution risk assessment
    """
    spread_bps: float = 0.0
    mid_price: float = 0.0

    # Depth in USD at various BPS thresholds from mid
    depth_usd: Dict[str, float] = Field(default_factory=dict)  # {"10bp": x, "25bp": y, "50bp": z}

    # Estimated price impact in BPS for various order sizes
    impact_est_bps: Dict[str, float] = Field(default_factory=dict)  # {"1000": x, "5000": y, "10000": z}

    # Composite liquidity score 0-1 (higher = more liquid)
    liquidity_score: float = 0.0

    # Compact heatmap for visualization (top N levels per side)
    book_heatmap: List[BookHeatmapLevel] = Field(default_factory=list)


class OrderbookData(BaseModel):
    spread_bps: float = 0.0
    spread_usd: float = 0.0
    depth: OrderbookDepth = Field(default_factory=OrderbookDepth)
    imbalance_1pct: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    mid_price: float = 0.0
    book_age_ms: int = 0


class VolumeData(BaseModel):
    horizons: Dict[str, float] = Field(default_factory=dict)
    cvd: Optional[Dict[str, float]] = None
    cvd_method: Optional[str] = None
    avg_7d_daily: float = 0.0
    regime: VolumeRegime = VolumeRegime.NORMAL
