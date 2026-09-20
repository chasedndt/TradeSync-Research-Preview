"""An exit taken in parts: what each observation filled, what stays owed, and what they sum to.

A market exit takes the displayed levels its style's depth bound allows
(``paper_depth``). When those cannot take the whole quantity still held, the part that
filled is recorded with its own price, fee, gross result and book snapshot, and the rest
stays owed: the exit fills across observations until nothing is left, and the position
closes at the observation that fills its last part. Profit and loss is the sum of the
parts, never one average applied to the whole size, so a close is exactly what the
observed books took.

Funding follows the same record. A settlement is paid on the quantity held at that hour,
so a part filled before an hour leaves that hour to the quantity that was still on
(``held_quantity``).

Positions opened under earlier rules (``managed-paper-lifecycle-v2``) declare no bound:
they fill whole or stay owed, ``policy`` says so, and their single exit fill is kept in
the shape it has always had.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

# A remainder this far inside the size is the size: a walk's last take is exact to a few ulp.
QUANTITY_TOLERANCE = 1e-12
PARTS_BASIS = "book_walk_parts"


def policy(state: Mapping[str, Any]) -> tuple[float | None, bool]:
    """The style's depth bound and whether its exits fill in parts; v2 positions do neither."""
    rules = state.get("rules") if isinstance(state.get("rules"), Mapping) else {}
    bound = rules.get("max_depth_bps")
    bound = float(bound) if isinstance(bound, (int, float)) and not isinstance(bound, bool) and math.isfinite(bound) else None
    return bound, bound is not None


def parts(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    recorded = state.get("exit_parts")
    return list(recorded) if isinstance(recorded, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def open_quantity(state: Mapping[str, Any]) -> float:
    """The quantity still held: the entry quantity less every part already filled."""
    remaining = _number(state.get("open_quantity"))
    return remaining if remaining is not None else float(state["quantity"])


def held_quantity(state: Mapping[str, Any], at_s: float) -> float:
    """What the position held at ``at_s``: a part filled strictly before it no longer takes part."""
    held = float(state["quantity"])
    for record in parts(state):
        if float(record["at"]) < at_s:
            held = float(record["remaining_after"])
    return held


def sums(state: Mapping[str, Any]) -> dict[str, Any]:
    """The parts filled so far: quantity, gross, fees, cost against the mid, and their weighted price."""
    filled = parts(state)
    quantity = math.fsum(float(p["quantity"]) for p in filled)
    return {"parts": len(filled), "quantity": quantity,
            "gross_usdc": math.fsum(float(p["gross_usdc"]) for p in filled),
            "fees_usdc": math.fsum(float(p["fee_usdc"]) for p in filled),
            "cost_usdc": math.fsum(_number((p.get("fill") or {}).get("cost_usdc")) or 0.0 for p in filled),
            "fill_price": math.fsum(float(p["quantity"]) * float(p["fill_price"]) for p in filled) / quantity if quantity else None}


def append(result: dict[str, Any], *, fill: Mapping[str, Any], observation: Mapping[str, Any], at: float) -> dict[str, Any]:
    """Record what one observation filled of the exit; the quantity still held falls by it."""
    remaining = open_quantity(result)
    quantity = remaining if fill.get("complete", True) else float(fill["quantity"])
    if quantity <= 0:
        raise ValueError("An exit part must fill a positive quantity")
    price = float(fill["fill_price"])
    sign = 1 if result["side"] == "long" else -1
    left = remaining - quantity
    record = {"index": len(parts(result)) + 1, "at": at, "quantity": quantity, "fill_price": price,
              "fee_usdc": float(result["fees"]["rate"]) * price * quantity,
              "gross_usdc": sign * (price - float(result["entry_price"])) * quantity,
              "remaining_after": 0.0 if left <= remaining * QUANTITY_TOLERANCE else left,
              "observation": dict(observation), "fill": dict(fill)}
    result.setdefault("exit_parts", [])
    if not isinstance(result["exit_parts"], list):
        result["exit_parts"] = []
    result["exit_parts"].append(record)
    result["open_quantity"] = record["remaining_after"]
    return record


def exit_fill(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """The exit as one record beside the parts: one part is that part's own fill, several are summed.

    The ledger reads ``cost_usdc`` from it and never subtracts it again; the Cockpit reads
    the price and how many parts it took.
    """
    filled = parts(state)
    if not filled:
        return None
    if len(filled) == 1:
        return dict(filled[0]["fill"])
    totals = sums(state)
    quantity = totals["quantity"]

    def weighted(key: str) -> float | None:
        values = [(float(p["quantity"]), _number((p.get("fill") or {}).get(key))) for p in filled]
        return math.fsum(q * v for q, v in values if v is not None) / quantity if quantity and all(v is not None for _, v in values) else None

    last = filled[-1]["fill"]
    return {"basis": PARTS_BASIS, "model": last.get("model"), "side": last.get("side"), "parts": len(filled),
            "fill_price": totals["fill_price"], "quantity": quantity, "cost_usdc": totals["cost_usdc"],
            "fee_usdc": totals["fees_usdc"], "cost_bps": weighted("cost_bps"), "total_bps": weighted("total_bps"),
            "half_spread_bps": weighted("half_spread_bps"), "depth_bps": weighted("depth_bps"),
            "first_at": filled[0]["at"], "last_at": filled[-1]["at"], "snapshot": last.get("snapshot"),
            "note": "Filled in parts across observations; each part keeps its own price, fee and book."}
