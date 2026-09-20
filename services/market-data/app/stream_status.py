"""The market stream's freshness, as ``/readyz`` and ``/feeds/status`` report it.

The stream being stale does not make the service unready: the poll loops read
REST for every market without a fresh stream reading, so observations keep
arriving, and readiness stays a statement about stored snapshots. It does make
the service *degraded*, which both surfaces say, with the reason and the number
of REST fallbacks the stream's absence has cost in the last hour.

Candles are reported but never degrade the stream: a candle updates only when
its market trades, and nothing scores from them.
"""

from __future__ import annotations

import time
from typing import Any

from .market_stream import HEARTBEAT
from .market_stream_state import BOOK, CONTEXT
from .runtime import MARKET_STREAM_ENABLED, MARKET_STREAM_FRESH_MS, market_stream

SCORING_CHANNELS = (CONTEXT, BOOK)


def stream_report(now_ms: int | None = None) -> dict[str, Any]:
    """Connection state, per-channel freshness, fallbacks, and whether the stream is degraded and why."""
    if not MARKET_STREAM_ENABLED:
        return {"enabled": False, "degraded": False, "reason": "switched off by MARKET_STREAM_ENABLED; every read uses REST"}
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    beat = HEARTBEAT.snapshot(now_ms / 1000)
    freshness = market_stream.freshness(now_ms, MARKET_STREAM_FRESH_MS)
    problems: list[str] = []
    if not beat["connected"]:
        problems.append(f"stream {beat['state'].replace('_', ' ')}")
    markets = len(market_stream.coins)
    for name in SCORING_CHANNELS:
        channel = freshness["channels"][name]
        not_fresh = len(channel["stale"]) + len(channel["missing"])
        if not_fresh:
            problems.append(f"{name}: {not_fresh} of {markets} markets without a fresh reading")
    counts = beat["counts_1h"]
    return {
        "enabled": True,
        "state": beat["state"],
        "connected": beat["connected"],
        "connected_since": beat["connected_since"],
        "reconnects": beat["reconnects"],
        "last_message_age_ms": freshness["last_message_age_ms"],
        "channels": freshness["channels"],
        "rest_fallbacks_1h": {"book": counts.get("book_fallbacks", 0), "context": counts.get("context_fallbacks", 0)},
        "resyncs_1h": counts.get("resyncs", 0),
        "degraded": bool(problems),
        "reason": "; ".join(problems) or None,
        "effect": "markets without a fresh stream reading are read from REST" if problems else None,
    }


def refresh_feed_detail(now_ms: int | None = None) -> None:
    """Write the current freshness onto the stream's heartbeat, just before the heartbeats are served."""
    report = stream_report(now_ms)
    if not report["enabled"]:
        HEARTBEAT.detail.update(enabled=False)
        return
    HEARTBEAT.detail.update(
        enabled=True,
        degraded=report["degraded"],
        reason=report["reason"],
        freshness={
            name: {"fresh": channel["fresh"], "stale": len(channel["stale"]), "missing": len(channel["missing"]),
                   "newest_age_ms": channel["newest_age_ms"], "fresh_after_ms": channel["fresh_after_ms"]}
            for name, channel in report["channels"].items()
        },
    )
