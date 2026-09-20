"""The paper plan behind an opportunity: invalidation, stop, target, and the risk and reward it was sized to.

A plan exists only once a managed paper position is opened from the opportunity.
Its stop and target are set at that moment from the entry fill and the average
true range (``paper_opening``), frozen into ``managed_paper_positions.initial_plan``
and never rewritten. An opportunity that never opened a position therefore has no
stop, no target and no risk figure, and this module says exactly that rather than
inventing levels from a price that was never filled. What it can show instead is
the versioned rules a plan would be set under.

The net reward-to-risk restates the entry gate's own ratio on the plan's stored
totals — the reward less the declared cost budget, over the planned risk — so it
is the figure the gate actually admitted, not a new estimate.
"""

from __future__ import annotations

from typing import Any, Mapping

from .opportunity_entry import number
from .paper_lifecycle_rules import COMMON, LIFECYCLE_VERSION, RULES

NO_PLAN = (
    "No paper position was opened from this opportunity, so no stop, target or risk was ever set. "
    "A plan is fixed only at entry, from the entry fill and the average true range."
)


def rules_at_entry() -> dict[str, Any]:
    """The versioned rules a plan would be set under, per holding style, and the caps every entry shares."""
    return {
        "version": LIFECYCLE_VERSION,
        "styles": {
            style: {"stop_atr": r.stop_atr, "atr_interval": r.atr_interval, "reward_risk": r.reward_risk,
                    "min_target_pct": r.min_target_pct, "max_hold_s": r.max_hold_s}
            for style, r in RULES.items()
        },
        "max_planned_risk_usdc": COMMON.max_planned_risk_usdc,
        "min_net_reward_risk": COMMON.min_net_reward_risk,
        "max_opportunity_age_s": COMMON.max_opportunity_age_s,
    }


def net_reward_risk(plan: Mapping[str, Any]) -> float | None:
    """(reward − cost budget) ÷ planned risk, on the plan's stored totals: the ratio the entry gate admitted."""
    planning = plan.get("planning") or {}
    reward, budget = number(planning.get("reward_usdc")), number(planning.get("cost_budget_usdc"))
    risk = number(plan.get("planned_risk_usdc"))
    if reward is None or budget is None or risk is None or risk <= 0:
        return None
    return round((reward - budget) / risk, 4)


def _exit(state: Mapping[str, Any]) -> dict[str, Any] | None:
    record = state.get("exit")
    if state.get("status") != "closed" or not isinstance(record, Mapping):
        return None
    return {"rule": record.get("rule"), "price": number(record.get("fill_price")), "at_s": number(record.get("at")),
            "net_estimate_usdc": number(state.get("net_estimate_usdc"))}


def plan_view(position: Mapping[str, Any] | None) -> dict[str, Any]:
    """The plan fixed at entry, with where the position stands now; or why there is none."""
    if position is None:
        return {"status": "none", "detail": NO_PLAN, "rules_at_entry": rules_at_entry()}
    plan = position.get("initial_plan") or {}
    state = position.get("position_state") or {}
    rules = plan.get("rules") or {}
    reward_risk = number(rules.get("reward_risk"))
    stop = number(plan.get("stop"))
    return {
        "status": str(state.get("status") or plan.get("status") or "unknown"),
        "detail": "Fixed when the paper position opened and never rewritten; the current stop can only tighten.",
        "position_id": position.get("id"),
        "opened_at_s": number(position.get("opened_at_s")),
        "entry_evidence_sha256": position.get("evidence_sha256"),
        "side": plan.get("side"),
        "style": plan.get("style"),
        "rules_version": rules.get("version") or plan.get("version"),
        "entry_price": number(plan.get("entry_price")),
        "quantity": number(plan.get("quantity")),
        "notional_usdc": number(plan.get("notional")),
        "invalidation": {
            "level": stop,
            "rule": "The stop: an exit-side price through it closes the paper position.",
            "current_stop": number(state.get("current_stop")),
            "current_stop_rule": state.get("current_stop_rule"),
        },
        "stop": stop,
        "stop_distance": number((plan.get("planning") or {}).get("stop_distance")),
        "atr": number(plan.get("atr")),
        "targets": [{
            "level": number(plan.get("target")),
            "basis": f"{reward_risk:g} × the stop distance beyond entry" if reward_risk is not None else "as stored",
        }],
        "expiry_s": number(plan.get("expiry")),
        "estimated_risk_usdc": number(plan.get("planned_risk_usdc")),
        "estimated_reward_usdc": number((plan.get("planning") or {}).get("reward_usdc")),
        "cost_budget_usdc": number((plan.get("planning") or {}).get("cost_budget_usdc")),
        "net_reward_risk": net_reward_risk(plan),
        "risk_basis": "Planned risk is the stop distance plus the declared cost budget, times quantity. A gap can exceed it.",
        "exit": _exit(state),
    }
