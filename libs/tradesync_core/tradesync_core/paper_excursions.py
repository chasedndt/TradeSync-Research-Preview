"""How far a managed paper position went in its favour, and against it, while it was held.

Measured on the price the lifecycle itself acts on: the exit-side price, the bid a long sells into and the
ask a short buys back from, against the entry fill. Nothing here reads a market; the lifecycle records the
extremes as it observes (``track``), and a position's own lifecycle events can recompute them
(``recompute``), so the stored figures can be checked against the record they came from.

Notation
--------

=======  ================================================  ======
Symbol   Meaning                                           Unit
=======  ================================================  ======
``d``    side: ``+1`` long, ``-1`` short                   --
``p``    entry fill price                                  USDC
``q``    entry quantity                                    base
``e_i``  exit-side price at observation ``i``              USDC
=======  ================================================  ======

The move at observation ``i`` is ``m_i = d * (e_i - p)``: positive in the position's favour. The entry fill
is the zero point, so both excursions are at least zero::

    MFE = max(0, max_i m_i)        MAE = max(0, max_i -m_i)

Each is reported as a price distance, in basis points of the entry fill (``distance / p * 10000``) and in
USDC on the entry quantity (``distance * q``), with the exit-side price and time of the extreme, which is
kept even when the distance is zero (a long whose best bid never reached its fill has an MFE of 0 and says
what the best bid was).

What counts as an observation
-----------------------------

- a quote: its exit-side touch, at its observed time;
- a closed candle that fired no exit: its high and its low, dated at its open, the earliest instant either
  could have happened (for a long the high is the favourable extreme, for a short the low);
- a closed candle that fired or filled an exit: only its open and the price the exit fired at. Inside a
  candle the order of its high and low is unknown, so its range beyond the exit is not a price the
  position is known to have held through.

The entry's own observation is not counted: its book filled the entry.

Worked example, by hand
-----------------------

A long, ``p = 100.00``, ``q = 2``. Quotes with bids 100.30, 99.60 and 100.80, then an exit whose bid is
99.90. The moves are +0.30, -0.40, +0.80 and -0.10, so MFE = 0.80 (80 bps, 1.60 USDC, at the third quote)
and MAE = 0.40 (40 bps, 0.80 USDC, at the second).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

MODEL = "exit_side_excursion_v1"
BASIS = "exit-side price (bid for a long, ask for a short) against the entry fill; the entry fill is zero"
NOT_TRACKED = ("this position was opened before excursions were recorded; its reconstruction recomputes them "
               "from its lifecycle events")


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _sign(side: Any) -> int:
    if side == "long":
        return 1
    if side == "short":
        return -1
    raise ValueError("An excursion needs a long or short side")


def start() -> dict[str, Any]:
    """The record a new position carries: nothing observed after entry yet."""
    return {"model": MODEL, "observations": 0, "first_at": None, "last_at": None, "favourable": None, "adverse": None}


def track(record: Mapping[str, Any], side: str, entry_price: float, prices: Iterable[tuple[float, float]]) -> dict[str, Any]:
    """The record with one more observation: its ``prices`` (exit-side price, time), keeping the two extremes.

    A tie keeps the earlier extreme, so the record is the same whichever way the observations are replayed
    in time order.
    """
    sign = _sign(side)
    entry = _finite(entry_price)
    if entry is None or entry <= 0:
        raise ValueError("An excursion needs a positive entry price")
    out = dict(record)
    seen = [(_finite(price), _finite(at)) for price, at in prices]
    if not seen or any(value is None or value <= 0 or when is None for value, when in seen):
        raise ValueError("An excursion observation needs at least one positive price with a time")
    for value, when in seen:
        move = sign * (value - entry)
        best, worst = out.get("favourable"), out.get("adverse")
        if best is None or move > sign * (best["price"] - entry):
            out["favourable"] = {"price": value, "at": when}
        if worst is None or move < sign * (worst["price"] - entry):
            out["adverse"] = {"price": value, "at": when}
        out["first_at"] = when if out.get("first_at") is None else min(out["first_at"], when)
        out["last_at"] = when if out.get("last_at") is None else max(out["last_at"], when)
    out["observations"] = int(out.get("observations") or 0) + 1
    return out


def quote_prices(side: str, observed_at: float, bid: float, ask: float) -> list[tuple[float, float]]:
    """A quote's one exit-side price."""
    return [(bid if _sign(side) == 1 else ask, observed_at)]


def candle_prices(side: str, bar: Mapping[str, Any], *, exit_price: float | None = None) -> list[tuple[float, float]]:
    """A closed candle's prices: its high and low, or its open and the exit price when the candle held an exit."""
    at = bar["time"]
    if exit_price is not None:
        return [(bar["open"], at), (exit_price, at)]
    return [(bar["high"], at), (bar["low"], at)]


def _extreme(point: Mapping[str, Any] | None, sign: int, entry: float, quantity: float, favourable: bool) -> dict[str, Any] | None:
    if point is None:
        return None
    move = sign * (point["price"] - entry)
    distance = max(0.0, move if favourable else -move)
    return {"distance": distance, "bps": distance / entry * 10_000, "usdc": distance * quantity,
            "price": point["price"], "at": point["at"]}


def summary(state: Mapping[str, Any]) -> dict[str, Any]:
    """MFE and MAE of a position from the record it carries, or why they cannot be stated."""
    record = state.get("excursion")
    if not isinstance(record, Mapping):
        return {"model": MODEL, "status": "not_tracked", "reason": NOT_TRACKED, "basis": BASIS,
                "observations": None, "favourable": None, "adverse": None}
    return describe(record, state.get("side"), state.get("entry_price"), state.get("quantity"))


def describe(record: Mapping[str, Any], side: Any, entry_price: Any, quantity: Any) -> dict[str, Any]:
    """MFE and MAE from an excursion record and the entry it is measured against."""
    sign, entry, size = _sign(side), _finite(entry_price), _finite(quantity)
    if entry is None or entry <= 0 or size is None or size <= 0:
        raise ValueError("An excursion needs a positive entry price and quantity")
    observations = int(record.get("observations") or 0)
    base = {"model": MODEL, "basis": BASIS, "observations": observations,
            "first_at": record.get("first_at"), "last_at": record.get("last_at")}
    if observations == 0:
        return {**base, "status": "no_observation", "reason": "no price has been observed since entry",
                "favourable": None, "adverse": None}
    return {**base, "status": "measured", "reason": None,
            "favourable": _extreme(record.get("favourable"), sign, entry, size, True),
            "adverse": _extreme(record.get("adverse"), sign, entry, size, False)}


def recompute(state: Mapping[str, Any], observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The excursion record rebuilt from a position's own stored observations.

    ``observations`` are the quotes its lifecycle events recorded (``observed_at``, ``best_bid``,
    ``best_ask``), in any order. Only those after the entry observation and no later than the exit (or the
    last evaluation of an open position) count, exactly as ``track`` counted them.
    """
    entry_seen = _finite(state.get("entry_quote_time"))
    through = _finite(state.get("exit_time")) if state.get("status") == "closed" else _finite(state.get("evaluated_through"))
    record = start()
    for item in sorted(observations, key=lambda o: _finite(o.get("observed_at")) or 0.0):
        at = _finite(item.get("observed_at"))
        if at is None or (entry_seen is not None and at <= entry_seen) or (through is not None and at > through):
            continue
        record = track(record, state["side"], state["entry_price"],
                       quote_prices(state["side"], at, item.get("best_bid"), item.get("best_ask")))
    return record
