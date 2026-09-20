"""The canonical market snapshot for one venue and symbol.

Moved out of ``app/models.py`` unchanged.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from .regimes import RegimeSummary
from .sections import (
    FundingData,
    LiquidationData,
    MicrostructureData,
    OpenInterestData,
    OrderbookData,
    PriceData,
    VolumeData,
)
from .status import MetricAvailability, SourceMetadata


class MarketSnapshot(BaseModel):
    """
    The canonical market snapshot for a venue/symbol pair.
    Implements the contract from docs/contracts/MARKET_CONTRACT.md
    """
    venue: str
    symbol: str  # Canonical format: "BTC-PERP"
    ts: int  # Unix timestamp (ms)
    data_age_ms: int = 0

    available_metrics: List[MetricAvailability] = Field(default_factory=list)

    funding: Optional[FundingData] = None
    price: Optional[PriceData] = None
    oi: Optional[OpenInterestData] = None
    liquidations: Optional[LiquidationData] = None
    volume: Optional[VolumeData] = None
    orderbook: Optional[OrderbookData] = None

    # Phase 3C: Derived microstructure data
    microstructure: Optional[MicrostructureData] = None

    regimes: RegimeSummary = Field(default_factory=RegimeSummary)
    sources: List[SourceMetadata] = Field(default_factory=list)
