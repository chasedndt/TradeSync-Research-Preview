"""Configuration and the process-wide state the pollers and the routes share.

Moved out of ``app/main.py`` unchanged: the same objects, defined once, so the
polling loops and the read routes can each import what they need without
importing one another. The mutable containers here (``providers``,
``background_tasks`` and the three reference dictionaries) are shared by
reference, which is what lets the lifespan fill them while routes read them.

The logger keeps the name ``app.main`` so existing log lines are unchanged.
"""

import asyncio
import logging
import os
import time
from typing import List

from .depth_books import DepthBooks
from .feature_extractor import load_sampling_intervals
from .market_stream_state import MarketStreamState
from .open_interest_history import OpenInterestHistory
from .processors import MarketNormalizer, MarketSnapshotter
from .trade_flow import CVD_WINDOW_MS, TradeFlowTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("app.main")

# Configuration
SYMBOLS = os.getenv("MARKET_SYMBOLS", "BTC-PERP,ETH-PERP,SOL-PERP").split(",")
ENABLE_HYPERLIQUID = os.getenv("ENABLE_HYPERLIQUID", "true").lower() == "true"

# Polling intervals (ms)
POLL_INTERVAL_CONTEXT = int(os.getenv("POLL_INTERVAL_CONTEXT", "5000"))
POLL_INTERVAL_ORDERBOOK = int(os.getenv("POLL_INTERVAL_ORDERBOOK", "3000"))
POLL_INTERVAL_FUNDING_HISTORY = int(os.getenv("POLL_INTERVAL_FUNDING_HISTORY", "300000"))  # 5 min
FUNDING_HISTORY_LOOKBACK_SECONDS = int(
    os.getenv("FUNDING_HISTORY_LOOKBACK_SECONDS", str(7 * 24 * 60 * 60))
)

# Global state
providers = []
normalizer = MarketNormalizer()
snapshotter = MarketSnapshotter()
background_tasks: List[asyncio.Task] = []
feature_sampling_intervals = load_sampling_intervals()
# Venue coin names, which is what the trade stream carries.
# Latest Coinbase spot mid per symbol: {symbol: (mid, observed_at_ms)}.
# Context only — an external reference venue, not the trading venue.
spot_reference: dict = {}
# Must be comfortably shorter than the premium's 10s alignment bound, or
# most snapshots find the spot reading already too old and the premium goes
# missing from the current snapshot while still accumulating history.
SPOT_POLL_INTERVAL_MS = int(os.getenv('SPOT_POLL_INTERVAL_MS', '3000'))

trade_flow = TradeFlowTracker(
    [s.replace('-PERP', '') for s in SYMBOLS], window_ms=CVD_WINDOW_MS
)
# Aggregated order books for the liquidity heatmap (one websocket per aggregation)
# and Binance open-interest history for the estimated liquidation map.
depth_books = DepthBooks()
open_interest_history = OpenInterestHistory()

# The Hyperliquid market stream (app/market_stream.py): asset contexts, the
# full-precision book and candles per market. "false" returns every read to REST.
MARKET_STREAM_ENABLED = os.getenv("MARKET_STREAM_ENABLED", "true").lower() == "true"
# A stream reading older than this is not used and REST answers instead. It is the
# normalizer's own staleness bound for a book and a mark price, so a reading taken
# from the stream is never older than a poll would have been allowed to be.
MARKET_STREAM_FRESH_MS = int(os.getenv("MARKET_STREAM_FRESH_MS", "5000"))
MARKET_STREAM_CANDLE_INTERVALS = [
    i.strip() for i in os.getenv("MARKET_STREAM_CANDLE_INTERVALS", "1m").split(",") if i.strip()
]
MARKET_STREAM_CANDLE_KEEP = int(os.getenv("MARKET_STREAM_CANDLE_KEEP", "300"))
market_stream = MarketStreamState(
    [s.replace('-PERP', '') for s in SYMBOLS], MARKET_STREAM_CANDLE_INTERVALS, MARKET_STREAM_CANDLE_KEEP
)

# Latest Binance funding and open interest per symbol. External reference
# venue, context only; see cross_venue.py.
cross_venue_reference: dict = {}
CROSS_VENUE_POLL_INTERVAL_S = int(os.getenv("CROSS_VENUE_POLL_INTERVAL_S", "60"))
CROSS_VENUE_STALE_AFTER_MS = int(os.getenv("CROSS_VENUE_STALE_AFTER_MS", "600000"))

# Latest GDELT news tone per symbol. Context only; see news_tone.py.
news_tone_reference: dict = {}
NEWS_TONE_POLL_INTERVAL_S = int(os.getenv("NEWS_TONE_POLL_INTERVAL_S", "900"))
NEWS_TONE_STALE_AFTER_MS = int(os.getenv("NEWS_TONE_STALE_AFTER_MS", "3600000"))
NEWS_TONE_STARTUP_DELAY_S = int(os.getenv("NEWS_TONE_STARTUP_DELAY_S", "180"))

# A snapshot older than this means the pollers have stopped doing their job,
# whatever the HTTP server reports. Generous relative to the 5s context poll so
# a single slow cycle does not flap the container state.
SNAPSHOT_STALE_AFTER_SECONDS = int(os.getenv("SNAPSHOT_STALE_AFTER_SECONDS", "90"))
# Grace after startup, before any poll has completed.
READINESS_GRACE_SECONDS = int(os.getenv("READINESS_GRACE_SECONDS", "120"))
_started_at = time.time()
