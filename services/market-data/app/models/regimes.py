"""The legacy regime labels and the summary a snapshot carries.

Moved out of ``app/models.py`` unchanged.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class FundingRegime(str, Enum):
    EXTREME_POSITIVE = "extreme_positive"
    ELEVATED_POSITIVE = "elevated_positive"
    NEUTRAL = "neutral"
    ELEVATED_NEGATIVE = "elevated_negative"
    EXTREME_NEGATIVE = "extreme_negative"


class OIRegime(str, Enum):
    BUILD = "build"
    UNWIND = "unwind"
    FLAT = "flat"


class VolumeRegime(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TrendRegime(str, Enum):
    STRONG_TREND = "strong_trend"
    WEAK_TREND = "weak_trend"
    RANGE = "range"


class MarketCondition(str, Enum):
    TRENDING_HEALTHY = "trending_healthy"
    SQUEEZE_RISK = "squeeze_risk"
    CAPITULATION = "capitulation"
    CHOPPY = "choppy"
    UNKNOWN = "unknown"


class RegimeSummary(BaseModel):
    funding: FundingRegime = FundingRegime.NEUTRAL
    oi: OIRegime = OIRegime.FLAT
    volume: VolumeRegime = VolumeRegime.NORMAL
    trend: TrendRegime = TrendRegime.RANGE
    market_condition: MarketCondition = MarketCondition.UNKNOWN
    confidence: str = "low"
    confidence_note: Optional[str] = None
