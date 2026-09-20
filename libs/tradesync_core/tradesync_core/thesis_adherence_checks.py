"""The five checks thesis adherence is scored from, and the verdicts they share.

Moved out of ``thesis_adherence`` unchanged, to keep each file to one
responsibility: that module carries the notation, the worked example, the score
and the cohort summary; this one carries the checks. Each check reads only the
plan frozen at entry and the lifecycle's own record, never a market.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .paper_exits import RULE_ORDER

# Every rule a position may legitimately exit under. ``kill_switch`` is not one
# of the lifecycle's price rules but it is a declared operator control, so an
# exit under it is planned behaviour, not an unplanned exit.
DECLARED_EXIT_RULES = frozenset(RULE_ORDER) | {"kill_switch"}

# The rules that mean "the stop fired". A gap fill under one of these is worse
# than the stop by design and is not a breach of the plan.
STOP_RULES = frozenset({"stop", "trailing_stop"})

CHECK_NAMES = ("entry_in_zone", "stop_respected", "target_respected", "time_respected", "exit_rule_declared")

PASS, FAIL, ABSENT = "pass", "fail", "absent"


@dataclass(frozen=True)
class Check:
    """One check, its verdict, and enough of the arithmetic to argue with it."""

    name: str
    verdict: str
    detail: str
    observed: float | None = None
    allowed: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict, "detail": self.detail,
                "observed": self.observed, "allowed": self.allowed}


def _number(value: Any) -> float | None:
    """A finite number, or None. ``True`` is not 1.0 here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _sign(side: Any) -> int | None:
    return 1 if side == "long" else -1 if side == "short" else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _absent(name: str, missing: str) -> Check:
    return Check(name, ABSENT, f"not scored: {missing}")


def _entry_in_zone(plan: Mapping[str, Any]) -> Check:
    """The entry filled inside the half spread plus the style's depth bound."""
    fill = _mapping(_mapping(plan.get("slippage")).get("entry"))
    mid = _number(fill.get("mid"))
    filled = _number(fill.get("fill_price"))
    half_spread = _number(fill.get("half_spread_bps"))
    bound = _number(_mapping(plan.get("rules")).get("max_depth_bps"))
    if mid is None or mid <= 0 or filled is None:
        return _absent("entry_in_zone", "the entry fill did not record a mid and a fill price")
    if half_spread is None or bound is None:
        # A position opened under lifecycle v2 declares no depth bound. There is
        # no zone to test it against, and inventing today's bound would judge an
        # old entry by a rule it was never opened under.
        return _absent("entry_in_zone", "the plan declares no half spread and depth bound to bound the entry")
    deviation = abs(filled - mid) / mid * 10000.0
    allowed = half_spread + bound
    inside = deviation <= allowed
    return Check(
        "entry_in_zone", PASS if inside else FAIL,
        f"entry filled {deviation:.4g} bps from the mid against {allowed:.4g} bps allowed"
        + ("" if inside else "; outside the zone the plan permitted"),
        observed=round(deviation, 6), allowed=round(allowed, 6),
    )


def _stop_respected(plan: Mapping[str, Any], state: Mapping[str, Any], sign: int) -> Check:
    """The position did not trade past its stop and then exit for another reason."""
    stop = _number(plan.get("stop"))
    record = _mapping(state.get("exit"))
    price = _number(record.get("fill_price") or state.get("exit_price"))
    rule = record.get("rule") or state.get("exit_reason")
    if state.get("status") != "closed" or price is None or not rule:
        return _absent("stop_respected", "the position has not closed, so no exit price exists yet")
    if stop is None:
        return _absent("stop_respected", "the plan records no stop")
    past = sign * (price - stop) < 0
    if past and rule not in STOP_RULES:
        return Check("stop_respected", FAIL,
                     f"exit filled at {price:.10g}, past the planned stop {stop:.10g}, under rule {rule!r} "
                     "rather than the stop",
                     observed=price, allowed=stop)
    detail = (f"the stop fired at {price:.10g} under rule {rule!r}" if rule in STOP_RULES
              else f"exit at {price:.10g} never passed the planned stop {stop:.10g}")
    return Check("stop_respected", PASS, detail, observed=price, allowed=stop)


def _target_respected(plan: Mapping[str, Any], state: Mapping[str, Any], sign: int) -> Check:
    """A target exit actually reached the target."""
    target = _number(plan.get("target"))
    record = _mapping(state.get("exit"))
    price = _number(record.get("fill_price") or state.get("exit_price"))
    rule = record.get("rule") or state.get("exit_reason")
    if state.get("status") != "closed" or price is None or not rule:
        return _absent("target_respected", "the position has not closed, so no exit price exists yet")
    if target is None:
        return _absent("target_respected", "the plan records no target")
    if rule != "target":
        return Check("target_respected", PASS, f"no target exit was claimed; the exit fired under rule {rule!r}",
                     observed=price, allowed=target)
    reached = sign * (price - target) >= 0
    return Check(
        "target_respected", PASS if reached else FAIL,
        f"target exit filled at {price:.10g} against a target of {target:.10g}"
        + ("" if reached else "; the record claims a target the price never reached"),
        observed=price, allowed=target,
    )


def _time_respected(plan: Mapping[str, Any], state: Mapping[str, Any]) -> Check:
    """The position was not held past its expiry under some other rule."""
    expiry = _number(plan.get("expiry"))
    record = _mapping(state.get("exit"))
    at = _number(record.get("at") or state.get("exit_time"))
    rule = record.get("rule") or state.get("exit_reason")
    if state.get("status") != "closed" or at is None or not rule:
        return _absent("time_respected", "the position has not closed, so no exit time exists yet")
    if expiry is None:
        return _absent("time_respected", "the plan records no time expiry")
    late = at > expiry
    if late and rule != "time_expiry":
        return Check("time_respected", FAIL,
                     f"exit at {at:.10g} is {at - expiry:.10g}s past the planned expiry {expiry:.10g}, "
                     f"under rule {rule!r} rather than the time expiry",
                     observed=at, allowed=expiry)
    return Check("time_respected", PASS,
                 f"exit at {at:.10g} within the planned expiry {expiry:.10g}" if not late
                 else f"the time expiry fired at {at:.10g}",
                 observed=at, allowed=expiry)


def _exit_rule_declared(state: Mapping[str, Any]) -> Check:
    """The exit fired under a rule the lifecycle declares."""
    record = _mapping(state.get("exit"))
    rule = record.get("rule") or state.get("exit_reason")
    if state.get("status") != "closed" or not rule:
        return _absent("exit_rule_declared", "the position has not closed, so no exit rule exists yet")
    declared = rule in DECLARED_EXIT_RULES
    return Check("exit_rule_declared", PASS if declared else FAIL,
                 f"exit rule {rule!r} is " + ("declared by the lifecycle" if declared
                                              else "not one of the lifecycle's declared rules"))
