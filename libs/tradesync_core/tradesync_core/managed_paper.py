"""Managed paper positions: advanced on observations in time order, costs settled as they are known.

The pieces, one responsibility each:

- ``paper_lifecycle_rules``: every parameter, versioned;
- ``paper_observations``: what counts as a usable book or candle;
- ``paper_opening``: the entry fill, the frozen plan and the entry gates;
- ``paper_exits``: which rule an observation fires;
- ``paper_depth``: fills walked through observed books, within the style's depth bound;
- ``paper_exit_fills``: an exit taken in parts across observations, and what they sum to;
- ``paper_funding``: Hyperliquid's settled hourly funding;
- ``paper_excursions``: the most favourable and most adverse exit-side prices seen after entry;
- fees: the published base schedule the rehearsal journal already uses
  (``paper_rehearsal.HYPERLIQUID_BASE_FEES``).

This module advances an open position on a quote or a closed candle and keeps its
accounts. Profit and loss is gross from the fill prices (spread and depth already
inside them), minus the taker fee on both fills, minus settled funding. An exit the
observed book can take only in part fills in parts: each part has its own price, fee and
book snapshot, the rest stays owed, and the position closes at the observation that
fills the last part, with profit and loss the sum of the parts. While open, the quantity
still held is marked by walking the latest book for it, with the exit fee estimated at
that mark. No venue, wallet or approval dependency.

Missed intervals are never reconstructed: a silence between quote observations
longer than the common threshold is latched and disqualifies the position as clean
evidence. Closed candles are a separate, explicit observation kind.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from . import paper_depth as depth
from . import paper_excursions as excursions
from . import paper_exit_fills as fills
from . import paper_exits as exits
from . import paper_funding as funding
from .paper_lifecycle_rules import COMMON, LIFECYCLE_VERSION, RULES
from .paper_observations import atr, candle, finite, quote
from .paper_opening import open_position, open_position_on_candle, order_sides

__all__ = ["VERSION", "PROFILES", "finite", "quote", "atr", "open_position", "open_position_on_candle",
           "advance", "advance_on_candle", "settle_funding"]

VERSION = LIFECYCLE_VERSION
# What an owed exit says about why it fired, kept when a later observation fills it: the
# rule that coincided with a kill switch, and the kill that owed the exit. An exit the
# book held owed must record what an immediate one records.
CARRIED_INTO_EXIT = ("coincided_rule", "kill_switch")
# Interval, holding time and stop parameters per style, in the shape earlier callers read.
PROFILES = {style: {"interval": r.atr_interval, "seconds": r.atr_seconds, "max_hold_s": r.max_hold_s,
                    "stop_atr": r.stop_atr, "reward_risk": r.reward_risk, "min_target_pct": r.min_target_pct}
            for style, r in RULES.items()}


def _trail(result, favourable_price):
    result["trail"] = exits.ratchet(result, favourable_price)
    level, rule = exits.stop_in_force(result)
    result.update(current_stop=level, current_stop_rule=rule)


def _excursion(result, prices):
    """Record this observation's exit-side prices; a position opened before excursions were recorded stays untracked."""
    if isinstance(result.get("excursion"), dict):
        result["excursion"] = excursions.track(result["excursion"], result["side"], result["entry_price"], prices)


def _exit_walk(position, book, source):
    """What an observed book would take of the quantity still held, within the style's depth bound."""
    bound, partial = fills.policy(position)
    try:
        walked = depth.walk(book, order_sides(position["side"])[1], quantity=fills.open_quantity(position),
                            source=source, max_depth_bps=bound, partial=partial)
    except depth.InsufficientDepth as exc:
        return None, str(exc)
    return walked, walked["shortfall"]


def _fill_exit(result, fired, fill, observation, at, unfilled):
    """Take what this observation filled of the exit: a part, then the close or the exit still owed."""
    if fill is None:  # nothing the displayed book can take: no price is assumed and the exit stays owed
        result["pending_exit"] = {**fired, "unfilled": unfilled, "parts": len(fills.parts(result)),
                                  "remaining_quantity": fills.open_quantity(result)}
        return
    part = fills.append(result, fill=fill, observation=observation, at=at)
    if part["remaining_after"] > 0:
        result["pending_exit"] = {**fired, "unfilled": unfilled, "parts": len(fills.parts(result)),
                                  "remaining_quantity": part["remaining_after"]}
    else:
        _close(result, fired, at)


def _close(result, fired, at):
    filled = fills.parts(result)
    totals = fills.sums(result)
    result["fees"].update(exit_usdc=totals["fees_usdc"], exit_estimate_usdc=None)
    result["slippage"]["exit"] = fills.exit_fill(result)
    result["exit"] = {"rule": fired["rule"], "level": fired["level"], "trigger_price": fired["trigger_price"],
                      "gap_fill": fired["gap_fill"], "path": fired.get("path"), "ambiguous_candle": fired.get("ambiguous", False),
                      "trigger_observation": fired["observation"], "fill_observation": filled[-1]["observation"],
                      "fill_price": totals["fill_price"], "at": at, "parts": len(filled),
                      **{key: fired[key] for key in CARRIED_INTO_EXIT if key in fired}}
    result.update(status="closed", exit_reason=fired["rule"], exit_time=at, exit_price=totals["fill_price"], pending_exit=None)


def _account(result, mark_price, funding_rows):
    sign = 1 if result["side"] == "long" else -1
    closed = result["status"] == "closed"
    recorded, totals = fills.parts(result), fills.sums(result)
    held = fills.open_quantity(result)
    if closed and not recorded:  # a position closed under the earlier single-fill model
        gross = sign * (mark_price - result["entry_price"]) * result["quantity"]
        exit_fee = result["fees"]["exit_usdc"]
    elif closed:
        gross, exit_fee = totals["gross_usdc"], totals["fees_usdc"]
    else:
        gross = totals["gross_usdc"] + sign * (mark_price - result["entry_price"]) * held
        exit_fee = totals["fees_usdc"] + result["fees"]["rate"] * mark_price * held
        result["fees"]["exit_estimate_usdc"] = exit_fee
    settled = funding.summary(result["entry_time"], result["exit_time"] if closed else result["evaluated_through"], funding_rows)
    fees = result["fees"]["entry_usdc"] + exit_fee
    result.update(funding=settled, mark_exit_price=mark_price, gross_pnl_usdc=gross, fees_usdc=fees,
                  funding_usdc=settled["accrued_usdc"], net_estimate_usdc=gross - fees - settled["accrued_usdc"])
    return result


def advance(position, book, now_s, *, manual_close=False, funding_rows: Sequence[Mapping[str, Any]] | None = None):
    """Advance on one observed book: gap latch, exit rules, part fills, the trailing stop, mark and costs."""
    if position["status"] != "open":
        return copy.deepcopy(position)
    at, bid, ask = quote(book, now_s)
    if at <= position["evaluated_through"]:
        raise ValueError("Duplicate or out-of-order observation")
    result = copy.deepcopy(position)
    gap = at - position["last_quote_time"]
    result.update(last_quote_time=at, evaluated_through=at, observations=position["observations"] + 1,
                  observation_gap=position["observation_gap"] or gap > COMMON.observation_gap_s,
                  max_observation_gap_s=max(position["max_observation_gap_s"], gap))
    touch = bid if position["side"] == "long" else ask
    _excursion(result, excursions.quote_prices(position["side"], at, bid, ask))
    observation = {"kind": "quote", "observed_at": at, "received_at": now_s, "best_bid": bid, "best_ask": ask, "touch": touch}
    source = depth.snapshot(book, observed_at=at, received_at=now_s)
    walked, unfilled = _exit_walk(result, book, source)
    pending = position.get("pending_exit")
    fired = pending or exits.on_quote(result, touch, at, operator_close=manual_close)
    if fired:
        _fill_exit(result, fired if pending else {**fired, "observation": observation},
                   depth.book_fill(walked) if walked else None, observation, at, unfilled)
    else:
        _trail(result, touch)
    mark = result["exit_price"] if result["status"] == "closed" else walked["mark_price"] if walked else touch
    return _account(result, mark, funding_rows)


def advance_on_candle(position, bar, interval_s, cost_book, now_s, *, cost_source=None,
                      funding_rows: Sequence[Mapping[str, Any]] | None = None):
    """Advance on one closed candle: a gap at the open, the stop before the target inside it, the trail after it."""
    if position["status"] != "open":
        return copy.deepcopy(position)
    candle(bar)
    open_time, interval = bar["time"], finite(interval_s, True)
    if open_time + interval > now_s:
        raise ValueError("Candle not closed")
    if open_time < position["evaluated_through"]:
        raise ValueError("Candle overlaps evaluated observations or is out of order")
    result = copy.deepcopy(position)
    observation = {"kind": "candle", "interval_s": interval, "open_time": open_time, "close_time": open_time + interval,
                   "open": bar["open"], "high": bar["high"], "low": bar["low"], "close": bar["close"], "received_at": now_s}
    result.update(candles=position.get("candles", 0) + 1, evaluated_through=open_time + interval)
    bound, partial = fills.policy(result)
    try:
        walked = depth.walk(cost_book, order_sides(position["side"])[1], quantity=fills.open_quantity(result),
                            source=cost_source, max_depth_bps=bound, partial=partial)
    except depth.InsufficientDepth as exc:
        raise ValueError(f"Recorded book cannot price the exit: {exc}") from None
    pending = result.get("pending_exit")
    # An exit already owed fills at the open, the candle's first observed instant.
    fired = pending or exits.on_candle(result, bar, interval)
    # A candle that held an exit exposed the position only to its open and the exit's price, not its whole range.
    exit_price = (bar["open"] if pending else fired["trigger_price"]) if fired else None
    _excursion(result, excursions.candle_prices(position["side"], bar, exit_price=exit_price))
    if fired:
        reference, at = (bar["open"], open_time) if pending else (fired["trigger_price"], fired["at"])
        quantity = fills.open_quantity(result) if walked["complete"] else walked["quantity"]
        _fill_exit(result, {"observation": observation, **fired}, depth.reference_fill(walked, reference, quantity),
                   observation, at, walked["shortfall"])
    else:
        _trail(result, exits.favourable_extreme(result, bar))
    mark = result["exit_price"] if result["status"] == "closed" else depth.priced(bar["close"], walked, basis="mark_bps")
    return _account(result, mark, funding_rows)


def settle_funding(position, funding_rows: Sequence[Mapping[str, Any]] | None):
    """The position with settled funding brought up to date: through its exit when closed, its last observation when open."""
    result = copy.deepcopy(position)
    mark = result["exit_price"] if result["status"] == "closed" else result.get("mark_exit_price")
    if mark is None:
        result["funding"] = funding.summary(result["entry_time"], result["evaluated_through"], funding_rows)
        result["funding_usdc"] = result["funding"]["accrued_usdc"]
        return result
    return _account(result, mark, funding_rows)
