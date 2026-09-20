"""Deterministic horizon gate for managed-paper holding styles.

An intraday opportunity is not made actionable merely because a one-minute
producer emitted it.  The direction must agree with the measured horizon used
by the selected holding style, and that horizon's ordinary implied move must be
large enough to contain the style's minimum target.  These are admission rules,
not profitability claims.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping

STYLE_HORIZONS = {"scalp": "1h", "intraday": "8h", "swing": "3d"}
MAX_MEASUREMENT_AGE_S = 15 * 60
MAX_MEASUREMENT_FUTURE_S = 5


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return None


def assess_style_alignment(
    page: Mapping[str, Any],
    *,
    style: str,
    direction: str,
    minimum_move_pct: float,
    now_s: float,
) -> dict[str, Any]:
    """Return a serialisable, explained pass/refusal for one style."""
    horizon_key = STYLE_HORIZONS.get(style)
    if horizon_key is None:
        raise ValueError(f"Unknown managed-paper style: {style}")
    expected_lean = {"long": "up", "short": "down"}.get(direction.lower())
    if expected_lean is None:
        raise ValueError("Direction must be long or short")

    outlook = page.get("outlook") if isinstance(page.get("outlook"), Mapping) else {}
    horizons = outlook.get("horizons") if isinstance(outlook.get("horizons"), list) else []
    horizon = next((row for row in horizons if isinstance(row, Mapping) and row.get("key") == horizon_key), None)
    band = horizon.get("band") if horizon else None
    measured_part = "short" if band == "short" else "long"
    measured_at = (page.get("computed_at") or {}).get(measured_part) if isinstance(page.get("computed_at"), Mapping) else None
    measured_epoch = _epoch(measured_at)
    age_s = now_s - measured_epoch if measured_epoch is not None else None
    lean = horizon.get("lean") if horizon else None
    implied = horizon.get("implied_range") if horizon and isinstance(horizon.get("implied_range"), Mapping) else {}
    sigma = implied.get("sigma_pct")
    sigma_ok = isinstance(sigma, (int, float)) and not isinstance(sigma, bool) and math.isfinite(float(sigma))
    move_ok = sigma_ok and float(sigma) >= minimum_move_pct

    checks = [
        {"code": "measurement_available", "passed": bool(outlook.get("available") and horizon and horizon.get("available"))},
        # The horizon request can finish a fraction after the caller captured
        # ``now_s``. Permit bounded transport/clock skew, never an unbounded
        # future timestamp.
        {"code": "measurement_fresh", "passed": age_s is not None and -MAX_MEASUREMENT_FUTURE_S <= age_s <= MAX_MEASUREMENT_AGE_S},
        {"code": "direction_aligned", "passed": lean == expected_lean},
        {"code": "range_supports_target", "passed": move_ok},
    ]
    reasons: list[str] = []
    if not checks[0]["passed"]:
        reasons.append(f"{horizon_key} measurement unavailable")
    if not checks[1]["passed"]:
        reasons.append(f"{horizon_key} measurement older than {MAX_MEASUREMENT_AGE_S // 60} minutes or undated")
    if not checks[2]["passed"]:
        reasons.append(f"{horizon_key} lean is {lean or 'unavailable'}, not {expected_lean}")
    if not checks[3]["passed"]:
        shown = f"{float(sigma):.2f}%" if sigma_ok else "unavailable"
        reasons.append(f"{horizon_key} implied move {shown} is below the {minimum_move_pct:.2f}% {style} target floor")

    return {
        "policy": "paper-style-alignment-v1",
        "style": style,
        "horizon": horizon_key,
        "direction": direction.lower(),
        "expected_lean": expected_lean,
        "observed_lean": lean,
        "implied_move_pct": float(sigma) if sigma_ok else None,
        "minimum_move_pct": minimum_move_pct,
        "measured_at": measured_at,
        "measurement_age_s": age_s,
        "checks": checks,
        "eligible": all(check["passed"] for check in checks),
        "reasons": reasons,
        "meaning": "Style/horizon admission gate; not a forecast or proof of edge.",
    }
