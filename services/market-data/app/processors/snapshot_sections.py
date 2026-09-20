"""Price, funding, open interest and volume sections of a market snapshot.

Moved out of ``processors/snapshotter.py`` unchanged. Each builder takes the
rolling window it reads and the window configuration it needs, so the arithmetic
is testable without assembling a snapshotter, and returns the section, the
metric availability rows it justifies, and the age of the data it used.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..models import (
    FundingData,
    FundingHorizons,
    FundingSource,
    HorizonValue,
    MetricAvailability,
    MetricStatus,
    OpenInterestData,
    PriceData,
    VolumeData,
)
from .regime_rules import (
    classify_funding_regime,
    classify_oi_regime,
    classify_volume_regime,
)


def build_price(
    data: List[Dict],
    now: int,
) -> tuple[Optional[PriceData], List[MetricAvailability], int]:
    """The authoritative mark/oracle pair the venue already publishes.

    Order-book midpoint is never substituted for it, and a reading without both
    a mark and an oracle price yields no section at all rather than a partial one.
    """
    latest_price = data[-1]
    price_value = latest_price.get("value", {})
    mark_price = float(price_value.get("mark", 0))
    oracle_price = float(price_value.get("oracle", 0))
    if not (mark_price > 0 and oracle_price > 0):
        return None, [], 0

    # The venue publishes its own previous-day reference alongside
    # the mark, so the 24h change is a transparent derivation of
    # two authoritative values rather than a reconstruction from
    # stored history.
    prev_day = float(price_value.get("prev_day", 0) or 0)
    change_24h = (
        ((mark_price - prev_day) / prev_day) * 100
        if prev_day > 0
        else None
    )
    price_data = PriceData(
        mark_price_usd=mark_price,
        oracle_price_usd=oracle_price,
        oracle_premium_bps=((mark_price - oracle_price) / oracle_price) * 10000,
        prev_day_price_usd=prev_day if prev_day > 0 else None,
        change_24h_pct=change_24h,
    )
    metrics = [
        MetricAvailability(
            metric="price",
            status=MetricStatus(latest_price.get("status", "REAL")),
            source=latest_price.get("source", {}).get("provider"),
            last_updated=latest_price.get("ts"),
        )
    ]
    return price_data, metrics, now - latest_price.get("ts", now)


def build_funding(
    data: List[Dict],
    now: int,
    funding_windows: Dict[str, int],
) -> tuple[FundingData, List[MetricAvailability], int]:
    """Build funding data with multi-horizon averages."""
    latest = data[-1]
    latest_value = latest["value"]
    current_rate = latest_value.get("rate", 0)
    data_age = now - latest.get("ts", now)

    # Calculate horizon averages
    horizons = FundingHorizons(now=current_rate)

    for window_name, window_ms in funding_windows.items():
        cutoff = now - window_ms
        window_data = [d for d in data if d.get("ts", 0) > cutoff]

        if window_data:
            avg = sum(d["value"].get("rate", 0) for d in window_data) / len(window_data)
            if window_name == "8h":
                horizons.h8 = avg
            elif window_name == "24h":
                horizons.h24 = avg
            elif window_name == "3d":
                horizons.d3 = avg
            elif window_name == "7d":
                horizons.d7 = avg

    # Hyperliquid funding is paid hourly. h24 is the mean hourly rate over
    # the available 24-hour window, so simple annualization uses 24 hours
    # per day and 365 days per year.
    annualized = horizons.h24 * 24 * 365

    # Determine regime
    regime = classify_funding_regime(annualized)

    funding_data = FundingData(
        horizons=horizons,
        annualized_24h=annualized,
        regime=regime,
        source=FundingSource(
            provider=latest.get("source", {}).get("provider", "unknown"),
            endpoint=latest.get("source", {}).get("endpoint", "unknown"),
            raw_rate=current_rate
        )
    )

    status = MetricStatus(latest.get("status", "REAL"))
    metrics = [MetricAvailability(
        metric="funding",
        status=status,
        source=latest.get("source", {}).get("provider"),
        last_updated=latest.get("ts")
    )]

    return funding_data, metrics, data_age


def build_oi(
    data: List[Dict],
    now: int,
    windows: Dict[str, int],
) -> tuple[OpenInterestData, List[MetricAvailability], int]:
    """Build OI data with delta calculations."""
    latest = data[-1]
    current_oi = latest["value"].get("value_usd", 0)
    data_age = now - latest.get("ts", now)

    horizons = {}

    for window_name, window_ms in windows.items():
        if window_name in ["5m", "15m", "1h", "4h", "24h"]:
            cutoff = now - window_ms
            window_data = [d for d in data if d.get("ts", 0) > cutoff]

            if window_data and len(window_data) >= 2:
                first_val = window_data[0]["value"].get("value_usd", current_oi)
                delta_usd = current_oi - first_val
                delta_pct = (delta_usd / first_val * 100) if first_val else 0

                horizons[window_name] = HorizonValue(
                    value=first_val,
                    delta_pct=round(delta_pct, 2),
                    delta_usd=delta_usd
                )
            else:
                horizons[window_name] = HorizonValue(value=current_oi)

    # Determine regime
    delta_24h = horizons.get("24h", HorizonValue()).delta_pct
    delta_4h = horizons.get("4h", HorizonValue()).delta_pct
    regime = classify_oi_regime(delta_24h, delta_4h)

    oi_data = OpenInterestData(
        horizons=horizons,
        current_usd=current_oi,
        regime=regime
    )

    status = MetricStatus(latest.get("status", "REAL"))
    metrics = [MetricAvailability(
        metric="oi",
        status=status,
        source=latest.get("source", {}).get("provider"),
        last_updated=latest.get("ts")
    )]

    return oi_data, metrics, data_age


def build_volume(
    data: List[Dict],
    now: int,
    windows: Dict[str, int],
) -> tuple[VolumeData, List[MetricAvailability], int]:
    """Build volume data."""
    latest = data[-1]
    vol_24h = latest["value"].get("value_24h", 0)
    data_age = now - latest.get("ts", now)

    # Build horizon dict (for 24h we have the value, others are estimated)
    horizons = {
        "24h": vol_24h,
        "5m": vol_24h / (24 * 12) if vol_24h else 0,  # Rough estimate
        "1h": vol_24h / 24 if vol_24h else 0,
        "4h": vol_24h / 6 if vol_24h else 0,
    }

    # Calculate 7d average (from historical data if available)
    week_cutoff = now - windows["7d"]
    week_data = [d for d in data if d.get("ts", 0) > week_cutoff]
    avg_7d = vol_24h  # Default to current
    if len(week_data) >= 7:
        avg_7d = sum(d["value"].get("value_24h", 0) for d in week_data) / len(week_data)

    # Determine regime
    regime = classify_volume_regime(vol_24h, avg_7d)

    volume_data = VolumeData(
        horizons=horizons,
        avg_7d_daily=avg_7d,
        regime=regime
    )

    status = MetricStatus(latest.get("status", "REAL"))
    metrics = [MetricAvailability(
        metric="volume",
        status=status,
        source=latest.get("source", {}).get("provider"),
        last_updated=latest.get("ts")
    )]

    return volume_data, metrics, data_age
