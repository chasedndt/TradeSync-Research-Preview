"""Turning Hyperliquid's ``l2Book`` answer into a normalized book.

Moved out of ``providers/hyperliquid.py`` unchanged. Everything here is
displayed resting size at one instant: depth within 1% and 2% of mid, and the
imbalance between the two sides. Orders can be cancelled, so this is what the
venue showed, not what could be executed.
"""

from __future__ import annotations

from typing import Any, Dict, List


def parse_l2_book(venue: str, symbol: str, data: Dict[str, Any], poll_ts: int) -> Dict[str, Any]:
    """Parse one ``l2Book`` response into the normalized order-book shape."""
    # data has 'levels' with [bids, asks]
    levels = data.get("levels", [[], []])
    bids = levels[0] if len(levels) > 0 else []
    asks = levels[1] if len(levels) > 1 else []

    # Parse bids and asks
    parsed_bids: List[Dict[str, Any]] = []
    parsed_asks: List[Dict[str, Any]] = []

    for bid in bids:
        parsed_bids.append({
            "price": float(bid.get("px", 0)),
            "size": float(bid.get("sz", 0)),
            "orders": int(bid.get("n", 0))
        })

    for ask in asks:
        parsed_asks.append({
            "price": float(ask.get("px", 0)),
            "size": float(ask.get("sz", 0)),
            "orders": int(ask.get("n", 0))
        })

    # Calculate spread
    best_bid = parsed_bids[0]["price"] if parsed_bids else 0
    best_ask = parsed_asks[0]["price"] if parsed_asks else 0
    mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
    spread_usd = best_ask - best_bid if best_bid and best_ask else 0
    spread_bps = (spread_usd / mid_price * 10000) if mid_price else 0

    # Calculate depth within 1% and 2% of mid
    depth_1pct = {"bid": 0.0, "ask": 0.0}
    depth_2pct = {"bid": 0.0, "ask": 0.0}

    if mid_price > 0:
        threshold_1pct = mid_price * 0.01
        threshold_2pct = mid_price * 0.02

        for bid in parsed_bids:
            diff = mid_price - bid["price"]
            value = bid["price"] * bid["size"]
            if diff <= threshold_1pct:
                depth_1pct["bid"] += value
            if diff <= threshold_2pct:
                depth_2pct["bid"] += value

        for ask in parsed_asks:
            diff = ask["price"] - mid_price
            value = ask["price"] * ask["size"]
            if diff <= threshold_1pct:
                depth_1pct["ask"] += value
            if diff <= threshold_2pct:
                depth_2pct["ask"] += value

    # Calculate imbalance
    total_1pct = depth_1pct["bid"] + depth_1pct["ask"]
    imbalance_1pct = 0
    if total_1pct > 0:
        imbalance_1pct = (depth_1pct["bid"] - depth_1pct["ask"]) / total_1pct

    return {
        "venue": venue,
        "symbol": symbol,
        "poll_ts": poll_ts,
        "bids": parsed_bids[:10],  # Top 10 only
        "asks": parsed_asks[:10],
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "spread_usd": spread_usd,
        "spread_bps": round(spread_bps, 2),
        "depth": {
            "bid_1pct_usd": depth_1pct["bid"],
            "ask_1pct_usd": depth_1pct["ask"],
            "bid_2pct_usd": depth_2pct["bid"],
            "ask_2pct_usd": depth_2pct["ask"]
        },
        "imbalance_1pct": round(imbalance_1pct, 4),
        "source": "l2Book"
    }
