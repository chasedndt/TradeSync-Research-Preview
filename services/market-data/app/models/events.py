"""Raw and normalized market events, and the alert a regime change raises.

Moved out of ``app/models.py`` unchanged.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .status import MetricStatus, SourceMetadata


class RawMarketEvent(BaseModel):
    """Raw event from provider, before normalization."""
    id: str
    venue: str
    metric_type: str  # "funding", "oi", "orderbook", "volume"
    symbol_raw: str  # Venue-specific symbol
    payload: Dict[str, Any]
    poll_ts: int  # When we polled


class NormalizedMarketEvent(BaseModel):
    """Normalized event, ready for snapshotting."""
    id: str
    venue: str
    symbol: str  # Canonical symbol
    metric_type: str
    ts: int
    data_age_ms: int
    status: MetricStatus
    source: SourceMetadata
    value: Dict[str, Any]


class MarketAlert(BaseModel):
    """Alert for regime changes or extreme values."""
    id: str
    venue: str
    symbol: str
    ts: int
    alert_type: str  # "regime_change", "extreme_value", "stale_data"
    metric: str
    previous_value: Optional[str] = None
    new_value: str
    context: Dict[str, Any] = Field(default_factory=dict)
