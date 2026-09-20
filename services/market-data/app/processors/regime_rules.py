"""Regime classification: the thresholds, and what confidence the inputs justify.

Moved out of ``processors/snapshotter.py`` unchanged. These are the legacy
classifier's own rules, kept in one file so a threshold change is visible as a
threshold change rather than buried in snapshot assembly.

The confidence rule is the load-bearing part: it requires coverage of every input
this classifier uses, not merely that the fields which happen to be present are
REAL, and it names what was missing, proxied or derived.
"""

from __future__ import annotations

from typing import List, Optional

from ..models import (
    FundingData,
    FundingRegime,
    MarketCondition,
    MetricAvailability,
    MetricStatus,
    OIRegime,
    OpenInterestData,
    RegimeSummary,
    TrendRegime,
    VolumeData,
    VolumeRegime,
)


def classify_funding_regime(annualized_rate: float) -> FundingRegime:
    """Classify funding regime from annualized rate."""
    if annualized_rate > 0.50:
        return FundingRegime.EXTREME_POSITIVE
    elif annualized_rate > 0.20:
        return FundingRegime.ELEVATED_POSITIVE
    elif annualized_rate < -0.50:
        return FundingRegime.EXTREME_NEGATIVE
    elif annualized_rate < -0.20:
        return FundingRegime.ELEVATED_NEGATIVE
    else:
        return FundingRegime.NEUTRAL


def classify_oi_regime(delta_24h_pct: float, delta_4h_pct: float) -> OIRegime:
    """Classify OI regime from deltas."""
    if delta_24h_pct > 3.0 and delta_4h_pct > 0:
        return OIRegime.BUILD
    elif delta_24h_pct < -3.0 and delta_4h_pct < 0:
        return OIRegime.UNWIND
    else:
        return OIRegime.FLAT


def classify_volume_regime(vol_24h: float, avg_7d: float) -> VolumeRegime:
    """Classify volume regime."""
    if avg_7d <= 0:
        return VolumeRegime.NORMAL

    ratio = vol_24h / avg_7d

    if ratio > 2.0:
        return VolumeRegime.HIGH
    elif ratio < 0.5:
        return VolumeRegime.LOW
    else:
        return VolumeRegime.NORMAL


def compute_regimes(
    funding: Optional[FundingData],
    oi: Optional[OpenInterestData],
    volume: Optional[VolumeData],
    available_metrics: List[MetricAvailability],
) -> RegimeSummary:
    """Compute overall regime summary."""
    funding_regime = funding.regime if funding else FundingRegime.NEUTRAL
    oi_regime = oi.regime if oi else OIRegime.FLAT
    volume_regime = volume.regime if volume else VolumeRegime.NORMAL

    required_values = {
        "funding": funding,
        "oi": oi,
        "volume": volume,
    }
    status_by_metric = {
        metric.metric: metric.status for metric in available_metrics
    }
    present_statuses = {
        MetricStatus.REAL,
        MetricStatus.DERIVED,
        MetricStatus.PROXY,
    }
    usable_statuses = {MetricStatus.REAL, MetricStatus.DERIVED}
    present_metrics = {
        name
        for name, value in required_values.items()
        if value is not None and status_by_metric.get(name) in present_statuses
    }
    usable_metrics = {
        name
        for name, value in required_values.items()
        if value is not None and status_by_metric.get(name) in usable_statuses
    }

    # Simple trend detection based on OI and volume
    trend_regime = TrendRegime.RANGE
    if (
        {"oi", "volume"}.issubset(usable_metrics)
        and oi_regime == OIRegime.BUILD
        and volume_regime in [VolumeRegime.HIGH, VolumeRegime.NORMAL]
    ):
        trend_regime = TrendRegime.STRONG_TREND
    elif "oi" in usable_metrics and oi_regime == OIRegime.BUILD:
        trend_regime = TrendRegime.WEAK_TREND

    # Market condition
    condition = MarketCondition.UNKNOWN

    # Check for squeeze risk: extreme funding + OI build
    if (
        {"funding", "oi"}.issubset(usable_metrics)
        and funding_regime
        in [FundingRegime.EXTREME_POSITIVE, FundingRegime.EXTREME_NEGATIVE]
    ):
        if oi_regime == OIRegime.BUILD:
            condition = MarketCondition.SQUEEZE_RISK

    # Check for capitulation: OI unwind + high volume
    elif (
        {"oi", "volume"}.issubset(usable_metrics)
        and oi_regime == OIRegime.UNWIND
        and volume_regime == VolumeRegime.HIGH
    ):
        condition = MarketCondition.CAPITULATION

    # Trending healthy
    elif (
        {"funding", "oi", "volume"}.issubset(usable_metrics)
        and trend_regime in [TrendRegime.STRONG_TREND, TrendRegime.WEAK_TREND]
    ):
        if funding_regime == FundingRegime.NEUTRAL:
            condition = MarketCondition.TRENDING_HEALTHY

    # Choppy
    elif (
        {"oi", "volume"}.issubset(usable_metrics)
        and oi_regime == OIRegime.FLAT
        and volume_regime == VolumeRegime.LOW
    ):
        condition = MarketCondition.CHOPPY

    # Confidence requires coverage of all inputs used by this legacy regime
    # classifier, not merely that every currently-present field is REAL.
    required_names = set(required_values)
    missing = sorted(required_names - present_metrics)
    proxy = sorted(
        name
        for name in required_names
        if status_by_metric.get(name) == MetricStatus.PROXY
    )
    derived = sorted(
        name
        for name in required_names
        if status_by_metric.get(name) == MetricStatus.DERIVED
    )

    if not missing and not proxy and not derived:
        confidence = "high"
        confidence_note = None
    elif len(present_metrics) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    note_parts = []
    if missing:
        note_parts.append(f"Missing required inputs: {', '.join(missing)}")
    if proxy:
        note_parts.append(f"Proxy inputs: {', '.join(proxy)}")
    if derived:
        note_parts.append(f"Derived inputs: {', '.join(derived)}")
    confidence_note = "; ".join(note_parts) or None

    return RegimeSummary(
        funding=funding_regime,
        oi=oi_regime,
        volume=volume_regime,
        trend=trend_regime,
        market_condition=condition,
        confidence=confidence,
        confidence_note=confidence_note
    )
