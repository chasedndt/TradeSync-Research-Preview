"""The liquidation estimate, and the reason it is only ever a proxy.

Moved out of ``processors/normalizer.py`` unchanged. Hyperliquid publishes no
liquidation feed, so this infers pressure from a fall in open interest. Every
event it produces carries ``MetricStatus.PROXY``, a ``method`` naming the
heuristic and a note saying the real feed is unavailable — the point being that
nothing downstream can mistake it for an observed fact.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from ..models import MetricStatus, NormalizedMarketEvent, SourceMetadata


def create_proxy_liquidations(
    venue: str,
    symbol: str,
    oi_current: float,
    oi_previous: float,
    volume: float,
    ts: int,
) -> Optional[NormalizedMarketEvent]:
    """
    Create proxy liquidation estimate from OI delta.

    When OI drops without corresponding volume, it suggests liquidations.
    """
    oi_delta = oi_current - oi_previous

    if oi_delta >= 0:
        # OI increased or flat, no liquidations to estimate
        return None

    # Rough heuristic: OI drop without matching volume = liqs
    # This is a PROXY, not real data
    estimated_liqs = abs(oi_delta) * 0.5  # Conservative

    now = int(time.time() * 1000)
    data_age = now - ts

    return NormalizedMarketEvent(
        id=str(uuid.uuid4()),
        venue=venue,
        symbol=symbol,
        metric_type="liquidations",
        ts=ts,
        data_age_ms=data_age,
        status=MetricStatus.PROXY,
        source=SourceMetadata(
            provider=venue,
            endpoint="oi_delta_proxy",
            fetched_at=now,
            metrics_provided=["liquidations"]
        ),
        value={
            "estimated_total_usd": estimated_liqs,
            "oi_delta": oi_delta,
            "method": "oi_delta_proxy",
            "confidence": "low",
            "note": "Estimated from OI changes. Real liquidation feed unavailable."
        }
    )
