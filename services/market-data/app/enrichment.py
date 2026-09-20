"""What is attached to a snapshot before it is stored, and how it is stored.

Moved out of ``app/main.py`` unchanged. Every attachment here is context: a
missing value stays absent rather than becoming zero, because zero is a
different claim from having made no observation.
"""

from tradesync_core.liquidation_map import Bar as MapBar

from . import liquidity_context
from .candles import normalize_candles
from .cross_venue import attach_cross_venue
from .feature_extractor import (
    RETURN_1H_ANCHOR_TOLERANCE_MS,
    RETURN_1H_WINDOW_MS,
    attach_derived_features,
    extract_feature_observations,
)
from .news_tone import attach_news_tone
from .redis_client import redis_client
from .runtime import (
    CROSS_VENUE_STALE_AFTER_MS,
    NEWS_TONE_STALE_AFTER_MS,
    cross_venue_reference,
    depth_books,
    feature_sampling_intervals,
    logger,
    news_tone_reference,
    open_interest_history,
    providers,
    spot_reference,
    trade_flow,
)
from .spot_premium import premium_bps
from .trade_flow import CVD_WINDOW_MS


async def fetch_map_bars(symbol: str) -> list:
    """Hourly Binance open interest joined to Hyperliquid hourly candles, for the estimated liquidation map."""
    rows = (await open_interest_history.get(symbol, "1h", 500))["rows"]
    provider = next((p for p in providers if p.venue == "hyperliquid" and p.enabled), None)
    if not rows or provider is None:
        return []
    start_ms, end_ms = rows[0]["time"] * 1000, (rows[-1]["time"] + 3600) * 1000
    candles = {int(c["time"]): c for c in normalize_candles(await provider.fetch_candles(symbol, "1h", start_ms, end_ms))}
    return [MapBar(int(c["time"]), float(c["high"]), float(c["low"]), float(c["close"]), float(r["oi_usd"]))
            for r in rows if (c := candles.get(int(r["time"]) // 3600 * 3600))]


def attach_spot_premium(payload: dict) -> dict:
    """Attach the spot-versus-perp premium when both sides are aligned.

    Absent when no recent spot reading exists or the two venues were sampled too
    far apart. A missing premium is absent, never zero.
    """
    symbol = str(payload.get("symbol") or "")
    reference = spot_reference.get(symbol)
    mark = (payload.get("price") or {}).get("mark_price_usd")
    perp_ts = payload.get("ts")
    if not reference or not mark or not isinstance(perp_ts, int):
        return payload

    spot_price, spot_ts = reference
    result = premium_bps(spot_price, float(mark), spot_ts, perp_ts)
    if result is None:
        return payload
    payload.setdefault("derived", {})["coinbase_premium_bps"] = result
    return payload


def attach_trade_flow(payload: dict) -> dict:
    """Attach observed taker flow to the snapshot.

    Absent when no trade has been seen for this symbol yet. Zero would read as
    balanced flow, which is a different claim from having no observation.
    """
    symbol = str(payload.get("symbol") or "")
    coin = symbol.replace("-PERP", "")
    value = trade_flow.value(coin)
    if value is None:
        return payload
    derived = payload.setdefault("derived", {})
    derived["cvd_window_usd"] = {
        "value": value,
        "window_ms": CVD_WINDOW_MS,
        "trades_observed": trade_flow.observed(coin),
    }
    return payload


async def resolve_derived_features(payload) -> dict:
    """Attach history-backed derivations to a snapshot before it is stored."""
    venue = str(payload.get("venue") or "")
    symbol = str(payload.get("symbol") or "")
    if not venue or not symbol:
        return payload
    try:
        mark_history = await redis_client.get_feature_timeseries(
            venue,
            symbol,
            "hl_mark_price_usd",
            RETURN_1H_WINDOW_MS + RETURN_1H_ANCHOR_TOLERANCE_MS + 60_000,
        )
    except Exception as exc:  # pragma: no cover - transport failure path
        logger.warning(f"mark-price history unavailable for {symbol}: {exc}")
        return payload
    enriched = attach_news_tone(
        attach_spot_premium(
            attach_trade_flow(attach_derived_features(payload, mark_history))
        ),
        news_tone_reference,
        NEWS_TONE_STALE_AFTER_MS,
    )
    enriched = attach_cross_venue(enriched, cross_venue_reference, CROSS_VENUE_STALE_AFTER_MS)
    return liquidity_context.attach(enriched, depth_books.latest(symbol.replace('-PERP', '')))


async def store_snapshot_and_features(snapshot):
    """Store the latest snapshot and its cadence-governed feature history."""
    payload = await resolve_derived_features(snapshot.model_dump())
    await redis_client.store_snapshot(snapshot.venue, snapshot.symbol, payload)
    for observation in extract_feature_observations(payload):
        interval = feature_sampling_intervals.get(observation["feature_id"], 0)
        if interval:
            await redis_client.append_feature_timeseries(
                observation["venue"],
                observation["symbol"],
                observation["feature_id"],
                observation["value"],
                observation["observed_at_ms"],
                interval,
            )
