"""The conditions a paper opportunity cleared, and how its side sat against the regime, read from what was stored.

An opportunity is admitted by ``paper_signal.decide_paper_signal``, and the whole
decision — the verdict, the measured values and the policy it was judged under —
is stored with the opportunity (``opportunities.confluence``). This module reads
that record back as entry conditions an operator can check, restating each
comparison the gate makes on the values it stored:

- evidence coverage must reach the policy's floor;
- directional coverage must reach its floor;
- the directional score must clear the entry threshold to establish a side, or
  only the lower hold threshold to keep a side already held (hysteresis);
- no contributing reading may be older than the evidence age bound.

Nothing here re-decides an admission. ``admitted`` and ``rejection_reasons`` are
the gate's own; the per-condition ``met`` flags restate its comparisons, and a
test holds them to agreement with the gate on decisions the gate produced.

The regime fit is descriptive: the trailing move before entry, labelled from
closed candles, compared with the side taken. It says nothing about where price
goes next.
"""

from __future__ import annotations

from typing import Any, Mapping

PAPER_SIGNAL_SCHEMA = "paper_signal_v1"
SIDES = ("LONG", "SHORT")


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def stored_decision(confluence: Any) -> Mapping[str, Any] | None:
    """The paper-signal decision stored with an opportunity, or None for an opportunity recorded before that schema."""
    if isinstance(confluence, Mapping) and confluence.get("schema_version") == PAPER_SIGNAL_SCHEMA:
        return confluence
    return None


def _condition(code: str, label: str, measured: float | None, required: float | None, comparator: str,
               unit: str, basis: str) -> dict[str, Any]:
    met = None
    if measured is not None and required is not None:
        met = measured >= required if comparator == ">=" else measured <= required
    return {"code": code, "label": label, "measured": measured, "required": required, "comparator": comparator,
            "unit": unit, "met": met, "basis": basis}


def oldest_reading_age_ms(decision: Mapping[str, Any]) -> float | None:
    """How old the oldest contributing reading was when the decision was evaluated."""
    evaluated = number((decision.get("evidence") or {}).get("evaluated_at_ms"))
    if evaluated is None:
        return None
    ages = [evaluated - observed for item in decision.get("contributing_features") or []
            if isinstance(item, Mapping) and (observed := number(item.get("observed_at_ms"))) is not None]
    return max(ages) if ages else None


def entry_conditions(decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Each admission condition with the value measured, the value required and whether it was met."""
    evidence = decision.get("evidence") or {}
    policy = evidence.get("policy") or {}
    direction = decision.get("direction")
    previous = evidence.get("previous_direction")
    holding = previous in SIDES and previous == direction
    score = number(decision.get("directional_score"))
    threshold_key = "direction_deadband" if holding else "direction_enter_threshold"
    return [
        _condition(
            "evidence_coverage", "Evidence coverage",
            number(decision.get("data_coverage")), number(policy.get("minimum_coverage_to_emit")), ">=", "share",
            "The share of the rulebook's weight that had admissible evidence behind it.",
        ),
        _condition(
            "directional_coverage", "Directional coverage",
            number(decision.get("directional_coverage")), number(policy.get("minimum_directional_coverage")), ">=", "share",
            "The share of the features able to set a side that had a usable reading.",
        ),
        _condition(
            "direction_strength", "Directional score, either side of zero",
            None if score is None else abs(score), number(policy.get(threshold_key)), ">=", "score",
            ("The side was already held, so only the hold threshold applied."
             if holding else "A new side, so the higher entry threshold applied."),
        ),
        _condition(
            "evidence_age", "Oldest contributing reading",
            oldest_reading_age_ms(decision), number(policy.get("maximum_evidence_age_ms")), "<=", "ms",
            "No reading behind the decision may be older than the evidence age bound.",
        ),
    ]


def entry_view(confluence: Any) -> dict[str, Any]:
    """The admission as stored: verdict, conditions, and the policy note, or a statement that none was stored."""
    decision = stored_decision(confluence)
    if decision is None:
        return {
            "schema": "legacy",
            "admitted": None,
            "conditions": [],
            "conditions_met": 0,
            "conditions_checked": 0,
            "rejection_reasons": [],
            "policy_note": None,
            "detail": "Recorded before the paper signal schema, so the conditions it cleared were not stored with it.",
        }
    conditions = entry_conditions(decision)
    checked = [c for c in conditions if c["met"] is not None]
    return {
        "schema": PAPER_SIGNAL_SCHEMA,
        "admitted": bool(decision.get("admitted")),
        "conditions": conditions,
        "conditions_met": sum(1 for c in checked if c["met"]),
        "conditions_checked": len(checked),
        "rejection_reasons": list(decision.get("rejection_reasons") or []),
        "policy_note": ((decision.get("evidence") or {}).get("policy") or {}).get("note"),
        "detail": "Read from the decision stored with the opportunity; nothing is recalculated.",
    }


def regime_fit(direction: Any, regime: Mapping[str, Any] | None) -> dict[str, Any]:
    """How the side sat against the regime recorded before entry: with it, against it, flat, or unlabelled."""
    side = str(direction or "").upper()
    label = (regime or {}).get("regime")
    reason = (regime or {}).get("reason") or None
    if not regime or not label:
        fit = "unlabelled"
        detail = "No regime is recorded for this opportunity yet. It is labelled once the candles before its entry have closed."
    elif label == "unknown":
        fit = "unlabelled"
        detail = f"The regime before entry could not be labelled: {reason or 'no reason was recorded'}."
    elif label == "flat":
        fit = "flat"
        detail = "The hour before entry was flat, so the side neither followed nor opposed a move."
    elif side not in SIDES:
        fit = "unlabelled"
        detail = "This opportunity carries no side to compare with the regime."
    elif (side, label) in (("LONG", "rising"), ("SHORT", "falling")):
        fit = "with"
        detail = f"A {side.lower()} taken after a {label} hour: the side followed the move before entry."
    else:
        fit = "against"
        detail = f"A {side.lower()} taken after a {label} hour: the side opposed the move before entry."
    return {
        "fit": fit,
        "regime": label,
        "trailing_return_pct": number((regime or {}).get("trailing_return_pct")),
        "lookback_minutes": (regime or {}).get("lookback_minutes"),
        "computed_at_s": number((regime or {}).get("computed_at_s")),
        "reason": reason,
        "detail": detail,
        "basis": "the trailing move from candles closed before entry; a description, not a forecast",
    }
