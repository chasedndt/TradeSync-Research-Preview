"""
MarketSnapshot models for Phase 3B - Market Data Expansion.

These models implement the contract defined in docs/contracts/MARKET_CONTRACT.md

Split by domain, every declaration moved unchanged: ``status`` (metric standing and source
metadata), ``regimes`` (the legacy regime labels), ``sections`` (the parts of a snapshot),
``snapshot`` (the snapshot itself) and ``events`` (raw and normalized events, alerts). This
module re-exports every name, so ``from app.models import X`` is unchanged for every caller.
"""

from .status import (  # noqa: F401
    MetricStatus,
    MetricAvailability,
    SourceMetadata,
)
from .regimes import (  # noqa: F401
    FundingRegime,
    OIRegime,
    VolumeRegime,
    TrendRegime,
    MarketCondition,
    RegimeSummary,
)
from .sections import (  # noqa: F401
    FundingHorizons,
    FundingSource,
    FundingData,
    PriceData,
    HorizonValue,
    OpenInterestData,
    LiquidationWindow,
    LiquidationData,
    OrderbookDepth,
    BookHeatmapLevel,
    MicrostructureData,
    OrderbookData,
    VolumeData,
)
from .snapshot import (  # noqa: F401
    MarketSnapshot,
)
from .events import (  # noqa: F401
    RawMarketEvent,
    NormalizedMarketEvent,
    MarketAlert,
)

__all__ = [
    "MetricStatus",
    "FundingRegime",
    "OIRegime",
    "VolumeRegime",
    "TrendRegime",
    "MarketCondition",
    "MetricAvailability",
    "FundingHorizons",
    "FundingSource",
    "FundingData",
    "PriceData",
    "HorizonValue",
    "OpenInterestData",
    "LiquidationWindow",
    "LiquidationData",
    "OrderbookDepth",
    "BookHeatmapLevel",
    "MicrostructureData",
    "OrderbookData",
    "VolumeData",
    "RegimeSummary",
    "SourceMetadata",
    "MarketSnapshot",
    "RawMarketEvent",
    "NormalizedMarketEvent",
    "MarketAlert",
]
