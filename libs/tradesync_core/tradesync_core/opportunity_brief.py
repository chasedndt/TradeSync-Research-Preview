"""One paper opportunity, stated in full from what was stored when it was scored.

The Opportunities pages computed a "strength" percentage in the browser (tanh of
the stored bias), printed a hard-coded "Risk confidence: VERIFIED", described
"multi-venue confluence" on a single-venue system, and drew an empty trade plan
of dashes. None of that came from evidence.

A brief is assembled here instead, from stored records only:

- the opportunity row: its side, timeframe and times, and the paper-signal
  decision stored with it (``opportunity_entry``);
- the regime recorded before its entry (``opportunity_entry_regimes``);
- the managed paper position opened from it, if one was, with the plan frozen at
  entry (``opportunity_plan``);
- the opening price the outcome job measured from (``opportunity_outcomes``);
- the paper entry pause and the execution gate, read and never changed.

Pure: the state API fetches the rows and passes them in with the clock, so
nothing in a brief is recalculated from a live price.
"""

from __future__ import annotations

from typing import Any, Mapping

from .opportunity_entry import entry_view, number, regime_fit, stored_decision
from .opportunity_plan import plan_view
from .paper_eligibility import opportunity_refusal

SCHEMA_VERSION = "opportunity_brief_v1"
SCORER = "regime_paper_scorer"
AUTHORITY = "paper_only"
NOTE = (
    "Assembled from stored records only; nothing here is recalculated from a live price. "
    "Paper research: it carries no approval, wallet or execution authority."
)


def _provenance(opportunity: Mapping[str, Any], decision: Mapping[str, Any] | None,
                position: Mapping[str, Any] | None, entry_reference_price: Any) -> dict[str, Any]:
    evidence = (decision or {}).get("evidence") or {}
    links = opportunity.get("links") or {}
    return {
        "signal_id": opportunity.get("signal_id") or links.get("signal_id"),
        "scorer": SCORER if decision else None,
        "decision_schema": (decision or {}).get("schema_version"),
        "evidence_digest": (decision or {}).get("evidence_digest") or links.get("evidence_digest"),
        "evaluated_at_ms": number(evidence.get("evaluated_at_ms")),
        "rulebook": {"id": evidence.get("rulebook_id"), "version": evidence.get("rulebook_version"),
                     "digest": evidence.get("rulebook_digest")},
        "catalog": {"id": evidence.get("catalog_id"), "version": evidence.get("catalog_version"),
                    "digest": evidence.get("catalog_digest")},
        "entry_evidence_sha256": (position or {}).get("evidence_sha256"),
        "entry_reference_price": number(entry_reference_price),
        "entry_reference_basis": "the opening price the outcome job measured every horizon from",
    }


def _evidence(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    evidence = (decision or {}).get("evidence") or {}
    directional = evidence.get("directional") or {}
    return {
        "contributing_features": list((decision or {}).get("contributing_features") or []),
        "directional_contributors": list(directional.get("contributors") or []),
        "missing_blocks": list(evidence.get("missing_blocks") or []),
        "risk_caps_applied": list(evidence.get("risk_caps_applied") or []),
        "paper_risk_multiplier": number((decision or {}).get("paper_risk_multiplier")),
    }


def paper_state(*, opportunity: Mapping[str, Any], position: Mapping[str, Any] | None,
                entries_paused: bool | None, execution_enabled: bool, now_s: float) -> dict[str, Any]:
    """Paper or live, and whether this opportunity has, could, or could not open a paper position."""
    refusal = opportunity_refusal(
        {"dir": opportunity.get("dir"), "snapshot_ts": number(opportunity.get("snapshot_ts_s"))}, now_s)
    held = str(((position or {}).get("position_state") or {}).get("status") or "unknown") if position else "none"
    if held == "open":
        label, detail = "Paper position open", "A managed paper position was opened from this opportunity and is still open."
    elif held == "closed":
        label, detail = "Paper position closed", "A managed paper position was opened from this opportunity and has closed."
    elif refusal:
        label, detail = "Paper research only", f"No paper position can open from it now: {refusal[1]}."
    elif entries_paused is True:
        label, detail = "Paper entries paused", "It is recent and directional, but new paper entries are paused."
    elif entries_paused is None:
        label, detail = "Paper entry state unknown", "Whether new paper entries are admitted could not be read."
    else:
        label, detail = ("Open to a paper entry",
                         "Recent and directional, with paper entries admitted; the entry's own gates still apply.")
    return {
        "label": label,
        "detail": detail,
        "position": held,
        "entries_paused": entries_paused,
        "entry_refusal": refusal[1] if refusal else None,
        "execution_enabled": bool(execution_enabled),
        "execution_authority": False,
        "mode": "live execution enabled" if execution_enabled else "paper",
    }


def build_brief(*, opportunity: Mapping[str, Any], regime: Mapping[str, Any] | None, position: Mapping[str, Any] | None,
                entry_reference_price: Any, entries_paused: bool | None, execution_enabled: bool,
                now_s: float) -> dict[str, Any]:
    """Every field an operator needs to judge one paper opportunity, each from a stored record."""
    decision = stored_decision(opportunity.get("confluence"))
    opened = number(opportunity.get("snapshot_ts_s"))
    return {
        "schema_version": SCHEMA_VERSION,
        "id": str(opportunity.get("id")),
        "symbol": opportunity.get("symbol"),
        "timeframe": opportunity.get("timeframe"),
        "side": opportunity.get("dir"),
        "status": opportunity.get("status"),
        "opened_at_s": opened,
        "expires_at_s": number(opportunity.get("expires_at_s")),
        "read_at_s": now_s,
        "age_s": None if opened is None else max(0.0, now_s - opened),
        "stored_scores": {
            "directional_score": number(opportunity.get("bias")),
            "evidence_coverage_pct": number(opportunity.get("quality")),
            "basis": "Stored when the opportunity was scored: the directional score, and evidence coverage as a "
                     "percentage. Neither is a probability of winning.",
        },
        "regime_fit": regime_fit(opportunity.get("dir"), regime),
        "entry": entry_view(opportunity.get("confluence")),
        "plan": plan_view(position),
        "evidence": _evidence(decision),
        "provenance": _provenance(opportunity, decision, position, entry_reference_price),
        "state": paper_state(opportunity=opportunity, position=position, entries_paused=entries_paused,
                             execution_enabled=execution_enabled, now_s=now_s),
        "authority": AUTHORITY,
        "note": NOTE,
    }


LIST_FIELDS = ("schema_version", "id", "symbol", "timeframe", "side", "status", "opened_at_s", "expires_at_s",
               "read_at_s", "age_s", "stored_scores", "authority")
LIST_PLAN_FIELDS = ("status", "detail", "stop", "targets", "invalidation", "estimated_risk_usdc",
                    "estimated_reward_usdc", "net_reward_risk", "expiry_s")


def compact(brief: Mapping[str, Any]) -> dict[str, Any]:
    """What a list card shows. The full brief, with its evidence and provenance, is one request away."""
    return {
        **{field: brief[field] for field in LIST_FIELDS},
        "regime_fit": {k: brief["regime_fit"][k] for k in ("fit", "regime", "detail")},
        "entry": {k: brief["entry"][k] for k in ("schema", "admitted", "conditions_met", "conditions_checked")},
        "plan": {k: brief["plan"].get(k) for k in LIST_PLAN_FIELDS},
        "provenance": {k: brief["provenance"][k] for k in ("signal_id", "evidence_digest", "evaluated_at_ms")},
        "state": {k: brief["state"][k] for k in ("label", "detail", "position", "entries_paused", "execution_enabled", "mode")},
    }
