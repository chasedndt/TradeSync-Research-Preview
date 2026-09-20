"""How a metric stands (real, derived, proxy, unavailable, stale) and where a reading came from.

Moved out of ``app/models.py`` unchanged.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class MetricStatus(str, Enum):
    REAL = "REAL"
    DERIVED = "DERIVED"
    PROXY = "PROXY"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"


class MetricAvailability(BaseModel):
    metric: str
    status: MetricStatus
    source: Optional[str] = None
    last_updated: Optional[int] = None
    note: Optional[str] = None


class SourceMetadata(BaseModel):
    provider: str
    endpoint: str
    fetched_at: int
    metrics_provided: List[str]
