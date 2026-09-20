"""Did a paper position follow the plan it was opened under?

Profit and loss says whether a position made money. It does not say whether the
position was the one the operator approved. A trade that blew through its stop
and was closed by hand two hours after its expiry can still show a profit; a
trade that followed its plan exactly can still lose. Keeping those apart is the
whole point of this measurement, and it is why nothing here reads a price feed:
adherence is scored from the plan frozen at entry and the lifecycle's own record
of what happened, never from a fresh look at the market. A later observation
cannot change whether an exit obeyed its rule at the time.

Notation
--------

For one position, with ``d`` the side (``d = +1`` for long, ``d = -1`` for short):

===================  ========================================  ======
Symbol               Meaning                                   Unit
===================  ========================================  ======
``m``                mid price at the entry observation        USDC
``p``                price the entry actually filled at        USDC
``h``                half spread recorded on the entry fill    bps
``b``                the style's fill depth bound              bps
``s``                planned stop                              USDC
``g``                planned target                            USDC
``x``                planned time expiry                       epoch s
``p_x``              price the exit actually filled at         USDC
``t_x``              time the exit filled                      epoch s
``r``                the rule the exit fired under             --
===================  ========================================  ======

One basis point (bps) is 1e-4, so a deviation in bps is
``(p - m) / m * 10000``.

The five checks
---------------

Each returns ``pass``, ``fail`` or ``absent``. ``absent`` means an input the
check needs was not recorded; it is counted and reported, and it is never
scored as a zero, because "we cannot tell" and "it broke the plan" are
different facts with different remedies.

1. ``entry_in_zone`` -- the entry filled inside the zone the plan allowed:
   ``|p - m| / m * 10000 <= h + b``. The plan permits the half spread every
   taker pays plus the style's depth bound, and nothing further.
2. ``stop_respected`` -- the position did not trade past its stop and exit for
   some other reason. It **fails** when the exit price is worse than the
   planned stop (``d * (p_x - s) < 0``) while ``r`` is not a stop rule. A stop
   or trailing stop that fires -- including a gap that fills worse than the
   stop, which the lifecycle records deliberately -- passes: the stop did its
   job.
3. ``target_respected`` -- a target exit was actually reached. It **fails**
   when ``r`` is ``target`` but the price never got there
   (``d * (p_x - g) < 0``). The record claiming a target it did not reach is
   the thing worth catching.
4. ``time_respected`` -- the position was not held past its expiry by some
   other rule: it **fails** when ``t_x > x`` and ``r`` is not ``time_expiry``.
5. ``exit_rule_declared`` -- ``r`` is one of the rules the lifecycle declares
   (``paper_exits.RULE_ORDER`` plus ``kill_switch``). An exit by anything else
   is an unplanned exit.

The score
---------

``adherence = passes / (passes + fails)``, a dimensionless ratio in [0, 1].
Abstentions are excluded from both parts and reported as ``abstained``. When
no check could be evaluated the score is ``None`` with the reason, never 0.0.

Worked example, by hand
-----------------------

A long scalp. Plan: entry mid ``m = 100.00``, fill ``p = 100.02``, half spread
``h = 1.0`` bps, depth bound ``b = 5.0`` bps, stop ``s = 98.50``, target
``g = 103.00``, entry at 1000 s with a 3600 s hold, so expiry ``x = 4600``.

It is closed by the operator: ``r = operator_close``, ``p_x = 98.20`` at
``t_x = 5000``.

1. entry: ``(100.02 - 100.00) / 100.00 * 10000 = 2.0`` bps against a bound of
   ``1.0 + 5.0 = 6.0`` bps. ``2.0 <= 6.0`` -> **pass**.
2. stop: ``d * (98.20 - 98.50) = -0.30 < 0``, so the price is past the stop,
   and ``operator_close`` is not a stop rule -> **fail**.
3. target: ``r`` is not ``target``, so nothing was claimed -> **pass**.
4. time: ``5000 > 4600`` and ``r`` is not ``time_expiry`` -> **fail**.
5. rule: ``operator_close`` is declared -> **pass**.

Three passes, two fails, nothing absent:
``adherence = 3 / (3 + 2) = 0.6``.

That 0.6 is the useful number. The position may well have closed for a good
reason, but it left its plan twice, and the record says exactly where.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .thesis_adherence_checks import (  # noqa: F401  Check, DECLARED_EXIT_RULES and STOP_RULES are re-exported
    ABSENT,
    CHECK_NAMES,
    DECLARED_EXIT_RULES,
    FAIL,
    PASS,
    STOP_RULES,
    Check,
    _absent,
    _entry_in_zone,
    _exit_rule_declared,
    _sign,
    _stop_respected,
    _target_respected,
    _time_respected,
)

SCHEMA_VERSION = "thesis_adherence_v1"


def score(plan: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Score one position against the plan it was opened under.

    ``plan`` is the immutable ``initial_plan`` frozen at entry; ``state`` is the
    position's latest lifecycle state. Nothing here reads a market.
    """
    if not isinstance(plan, Mapping) or not isinstance(state, Mapping):
        raise TypeError("thesis adherence needs the stored plan and lifecycle state as mappings")
    sign = _sign(plan.get("side") or state.get("side"))
    if sign is None:
        checks = [_absent(name, "the position records no side, so no level has a direction") for name in CHECK_NAMES]
    else:
        checks = [
            _entry_in_zone(plan),
            _stop_respected(plan, state, sign),
            _target_respected(plan, state, sign),
            _time_respected(plan, state),
            _exit_rule_declared(state),
        ]
    passes = sum(1 for check in checks if check.verdict == PASS)
    fails = sum(1 for check in checks if check.verdict == FAIL)
    abstained = sum(1 for check in checks if check.verdict == ABSENT)
    judged = passes + fails
    return {
        "schema_version": SCHEMA_VERSION,
        "adherence": round(passes / judged, 6) if judged else None,
        "passed": passes,
        "failed": fails,
        # Counted, never scored as a zero: a missing input is not a broken plan.
        "abstained": abstained,
        "checks_judged": judged,
        "checks": [check.to_dict() for check in checks],
        "departures": [check.name for check in checks if check.verdict == FAIL],
        "reason": None if judged else "no check could be evaluated from the stored plan and lifecycle state",
        "basis": "the plan frozen at entry and the lifecycle's own record; no market was re-read",
    }


def summarise(results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Adherence across a cohort, with abstentions kept out of the ratio.

    The mean is over positions that had at least one check to judge. A position
    that could not be judged at all is counted in ``unscored`` rather than
    dragging the mean towards zero.
    """
    rows = list(results)
    scored = [row for row in rows if row.get("adherence") is not None]
    passes = sum(int(row.get("passed") or 0) for row in rows)
    fails = sum(int(row.get("failed") or 0) for row in rows)
    by_check: dict[str, dict[str, int]] = {
        name: {PASS: 0, FAIL: 0, ABSENT: 0} for name in CHECK_NAMES
    }
    for row in rows:
        for check in row.get("checks") or []:
            counts = by_check.get(str(check.get("name")))
            if counts is not None and check.get("verdict") in counts:
                counts[str(check["verdict"])] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "positions": len(rows),
        "positions_scored": len(scored),
        "unscored": len(rows) - len(scored),
        "mean_adherence": round(sum(float(row["adherence"]) for row in scored) / len(scored), 6) if scored else None,
        "checks_passed": passes,
        "checks_failed": fails,
        "checks_abstained": sum(int(row.get("abstained") or 0) for row in rows),
        "by_check": by_check,
        "note": (
            "Adherence is whether a position followed its own plan, not whether it made money. "
            "Abstentions are counted apart and never scored as zero."
        ),
    }
