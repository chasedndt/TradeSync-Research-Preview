"""Where a read stands: anchor levels, what would invalidate it, and what confirms it.

Moved out of ``thesis.py`` unchanged. Missing coverage is reported, never padded
— a 24h high from six hours of candles is not a 24h high — and each confirming
input carries what the evidence cards say it has earned. ``thesis`` re-exports
every public name here.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def anchor_levels(candles: Sequence[Mapping[str, Any]], bucket_s: int) -> dict[str, Any]:
    """24h, 4h and 1h highs and lows from closed candles, newest last.

    ``candles`` are venue OHLCV rows ``{time, open, high, low, close}`` with
    ``time`` as the bucket open in seconds. Missing coverage is reported, not
    padded: a 24h high from six hours of candles is not a 24h high.
    """
    rows = sorted((c for c in candles if _finite(c.get("high")) and _finite(c.get("low"))), key=lambda c: c["time"])
    out: dict[str, Any] = {"source": "hyperliquid candles", "bucket_s": bucket_s, "candles": len(rows)}
    if not rows:
        out["note"] = "no candles; anchors unavailable"
        return out
    last = rows[-1]
    out["last_close"] = float(last["close"]) if _finite(last.get("close")) else None
    out["last_open"] = float(last["open"]) if _finite(last.get("open")) else None
    for label, hours in (("1h", 1), ("4h", 4), ("24h", 24)):
        need = max(1, hours * 3600 // bucket_s)
        window = rows[-need:]
        out[f"high_{label}"] = max(float(c["high"]) for c in window)
        out[f"low_{label}"] = min(float(c["low"]) for c in window)
        out[f"covered_{label}"] = len(window) >= need
    return out


def invalidation(direction: str, anchors: Mapping[str, Any], regime: str) -> dict[str, Any]:
    """The level that would falsify the read, and the rule that says so.

    A SHORT read in a falling hour is wrong once price reclaims the hour's
    high; a LONG read is wrong once it loses the hour's low. With no
    direction there is nothing to invalidate.
    """
    if direction not in ("LONG", "SHORT"):
        return {"level": None, "rule": "no directional read; nothing to invalidate"}
    key = "high_1h" if direction == "SHORT" else "low_1h"
    level = anchors.get(key)
    verb = "reclaims" if direction == "SHORT" else "loses"
    return {
        "level": level,
        "rule": f"{direction} read is invalid once price {verb} the trailing 1h {'high' if direction == 'SHORT' else 'low'}"
        + (f" ({regime} entry regime)" if regime and regime != "unknown" else ""),
        "source": anchors.get("source"),
    }


def confirmation_stack(
    contributors: Sequence[Mapping[str, Any]],
    cards_by_feature: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Each scoring contributor with what the evidence cards say it has earned."""
    stack = []
    for c in contributors:
        fid = str(c.get("feature_id"))
        card = cards_by_feature.get(fid, {})
        score = c.get("score")
        stack.append(
            {
                "feature_id": fid,
                "score": score,
                "reads": "LONG" if isinstance(score, (int, float)) and score > 0 else "SHORT" if isinstance(score, (int, float)) and score < 0 else "flat",
                "quality": c.get("quality"),
                "standing": card.get("standing", "unknown"),
                "earned": bool(card.get("earned", False)),
                "earned_by": list(card.get("earned_by", [])),
                "entries_with_reading": card.get("entries_with_reading"),
            }
        )
    return stack


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")
