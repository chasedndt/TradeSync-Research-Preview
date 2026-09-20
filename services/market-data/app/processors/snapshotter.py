"""
Market data snapshotter.

Aggregates normalized events into MarketSnapshot with:
- Multi-horizon windows
- Regime classifications
- Alert generation on regime changes

This module keeps the rolling windows and assembles a snapshot from them. The
work each section does lives beside it, one responsibility per file:
``snapshot_sections`` (funding, open interest, volume), ``snapshot_book``
(order book, derived microstructure, proxy liquidations) and ``regime_rules``
(classification thresholds and the confidence rule).
"""

import time
import uuid
import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict

from ..models import (
    MarketSnapshot,
    RegimeSummary,
    SourceMetadata,
    MarketAlert,
    NormalizedMarketEvent,
)
from .microstructure import MicrostructureDeriver
from .regime_rules import compute_regimes
from .snapshot_book import build_liquidations, build_microstructure, build_orderbook
from .snapshot_sections import build_funding, build_oi, build_price, build_volume

logger = logging.getLogger(__name__)


class MarketSnapshotter:
    """Builds MarketSnapshot from normalized events."""

    def __init__(self):
        # Rolling window storage: {venue: {symbol: {metric: [values]}}}
        self._windows: Dict[str, Dict[str, Dict[str, List]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

        # Previous regimes for alert detection
        self._prev_regimes: Dict[str, Dict[str, RegimeSummary]] = defaultdict(dict)

        # Phase 3C: Microstructure deriver
        self._microstructure_deriver = MicrostructureDeriver()

        # Window sizes in ms
        self.windows = {
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "24h": 24 * 60 * 60 * 1000,
            "7d": 7 * 24 * 60 * 60 * 1000,
        }

        # Funding specific windows
        self.funding_windows = {
            "8h": 8 * 60 * 60 * 1000,
            "24h": 24 * 60 * 60 * 1000,
            "3d": 3 * 24 * 60 * 60 * 1000,
            "7d": 7 * 24 * 60 * 60 * 1000,
        }

    def process_event(
        self,
        event: NormalizedMarketEvent
    ) -> Optional[MarketSnapshot]:
        """
        Process a normalized event and update rolling windows.

        Returns updated snapshot if enough data, None otherwise.
        """
        venue = event.venue
        symbol = event.symbol
        # Historical funding keeps a distinct event type but contributes to the
        # same rolling window used for the funding horizons.
        metric = "funding" if event.metric_type == "funding_history" else event.metric_type

        # Add to rolling window
        self._add_to_window(venue, symbol, metric, {
            "ts": event.ts,
            "value": event.value,
            "status": event.status,
            "source": event.source.model_dump() if event.source else {}
        })

        # Build snapshot from current windows
        return self.build_snapshot(venue, symbol)

    def build_snapshot(
        self,
        venue: str,
        symbol: str
    ) -> MarketSnapshot:
        """
        Build a complete MarketSnapshot from current window data.
        """
        now = int(time.time() * 1000)
        windows = self._windows[venue][symbol]

        # Track available metrics and max data age
        available_metrics = []
        max_data_age = 0
        sources = []

        # Build funding data
        funding_data = None
        if "funding" in windows and windows["funding"]:
            funding_data, funding_metrics, funding_age = build_funding(
                windows["funding"], now, self.funding_windows
            )
            available_metrics.extend(funding_metrics)
            max_data_age = max(max_data_age, funding_age)

        # Build the authoritative mark/oracle pair already supplied by the
        # Hyperliquid context endpoint. Order-book midpoint is not substituted.
        price_data = None
        if "price" in windows and windows["price"]:
            price_data, price_metrics, price_age = build_price(windows["price"], now)
            available_metrics.extend(price_metrics)
            max_data_age = max(max_data_age, price_age)

        # Build OI data
        oi_data = None
        if "oi" in windows and windows["oi"]:
            oi_data, oi_metrics, oi_age = build_oi(windows["oi"], now, self.windows)
            available_metrics.extend(oi_metrics)
            max_data_age = max(max_data_age, oi_age)

        # Build volume data
        volume_data = None
        if "volume" in windows and windows["volume"]:
            volume_data, vol_metrics, vol_age = build_volume(
                windows["volume"], now, self.windows
            )
            available_metrics.extend(vol_metrics)
            max_data_age = max(max_data_age, vol_age)

        # Build orderbook data
        orderbook_data = None
        microstructure_data = None
        if "orderbook" in windows and windows["orderbook"]:
            orderbook_data, ob_metrics, ob_age = build_orderbook(windows["orderbook"], now)
            available_metrics.extend(ob_metrics)
            max_data_age = max(max_data_age, ob_age)

            # Phase 3C: Derive microstructure from orderbook
            microstructure_data, micro_metrics = build_microstructure(
                windows["orderbook"], orderbook_data, self._microstructure_deriver
            )
            available_metrics.extend(micro_metrics)

        # Build liquidation data (proxy)
        liq_data = None
        if "liquidations" in windows and windows["liquidations"]:
            liq_data, liq_metrics, liq_age = build_liquidations(
                windows["liquidations"], now, self.windows
            )
            available_metrics.extend(liq_metrics)
            max_data_age = max(max_data_age, liq_age)

        # Compute regimes
        regimes = compute_regimes(funding_data, oi_data, volume_data, available_metrics)

        # Collect sources
        for metric_data in [
            windows.get(m, [])
            for m in ["funding", "price", "oi", "volume", "orderbook"]
        ]:
            if metric_data:
                latest = metric_data[-1]
                if "source" in latest:
                    sources.append(SourceMetadata(**latest["source"]))

        # Dedupe sources
        seen = set()
        unique_sources = []
        for s in sources:
            key = (s.provider, s.endpoint)
            if key not in seen:
                seen.add(key)
                unique_sources.append(s)

        snapshot = MarketSnapshot(
            venue=venue,
            symbol=symbol,
            ts=now,
            data_age_ms=max_data_age,
            available_metrics=available_metrics,
            funding=funding_data,
            price=price_data,
            oi=oi_data,
            volume=volume_data,
            orderbook=orderbook_data,
            microstructure=microstructure_data,  # Phase 3C
            liquidations=liq_data,
            regimes=regimes,
            sources=unique_sources
        )

        return snapshot

    def check_regime_change(
        self,
        venue: str,
        symbol: str,
        new_regimes: RegimeSummary
    ) -> List[MarketAlert]:
        """Check if any regimes changed and generate alerts."""
        alerts = []
        key = f"{venue}:{symbol}"

        if key not in self._prev_regimes:
            self._prev_regimes[key] = new_regimes
            return alerts

        prev = self._prev_regimes[key]
        now = int(time.time() * 1000)

        # Check each regime type
        regime_checks = [
            ("funding", prev.funding, new_regimes.funding),
            ("oi", prev.oi, new_regimes.oi),
            ("volume", prev.volume, new_regimes.volume),
            ("trend", prev.trend, new_regimes.trend),
        ]

        for metric, prev_val, new_val in regime_checks:
            if prev_val != new_val:
                alerts.append(MarketAlert(
                    id=str(uuid.uuid4()),
                    venue=venue,
                    symbol=symbol,
                    ts=now,
                    alert_type="regime_change",
                    metric=metric,
                    previous_value=prev_val.value if hasattr(prev_val, 'value') else str(prev_val),
                    new_value=new_val.value if hasattr(new_val, 'value') else str(new_val),
                    context={
                        "message": f"{metric.upper()} regime changed: {prev_val} -> {new_val}"
                    }
                ))

        self._prev_regimes[key] = new_regimes
        return alerts

    def _add_to_window(
        self,
        venue: str,
        symbol: str,
        metric: str,
        data: Dict[str, Any]
    ):
        """Add data point to rolling window."""
        window = self._windows[venue][symbol][metric]
        window.append(data)

        # Prune old entries, replace repeated provider timestamps, and keep the
        # window ordered. Funding backfills can arrive after a newer live poll.
        now = int(time.time() * 1000)
        cutoff = now - self.windows["7d"]
        by_timestamp = {
            int(item.get("ts", 0)): item
            for item in window
            if int(item.get("ts", 0)) > cutoff
        }
        self._windows[venue][symbol][metric] = [
            by_timestamp[ts] for ts in sorted(by_timestamp)
        ]
