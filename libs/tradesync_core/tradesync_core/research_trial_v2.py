"""Forward research specification v2: the configured universe, settled funding, lifecycle rules v2.

v1 (``research_trial``) is frozen and stays byte for byte what it was, fingerprints
included. It is also, now, a description of something that no longer exists: its
text names BTC, ETH and SOL and "scenario funding", while a managed paper position
is opened for any market the API reports as tracked and settles Hyperliquid's own
hourly funding, hour by hour. A frozen specification is never edited to catch up,
so this is a second version beside it.

What v2 freezes when a trial is registered:

- **the universe as the API reported it**, never a list written in code. The
  symbols are frozen into the specification, so the trial's population cannot
  drift when the configured universe changes, and an unreadable universe
  registers nothing;
- **the lifecycle rules** a position must have opened under, by version *and* by
  the digest of every parameter in them, so a later revision cannot quietly admit
  positions run under different stops and targets;
- **costs**: the frozen fee schedule, the observed book walk, and settled hourly
  funding. A closed position whose settlements are not all stored yet stays
  pending instead of being counted with funding missing;
- **the entry-evidence schema** and the pre-declared context family the evidence
  is compared under, by version and digest.

Registration starts nothing: no job, no position, no weight, no permission.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .entry_evidence_family import FAMILY_VERSION, cells as family_cells, digest as family_digest
from .paper_depth import MODEL as FILL_MODEL
from .paper_entry_evidence import SCHEMA_VERSION as EVIDENCE_SCHEMA, digest as evidence_digest
from .paper_funding import MODEL as FUNDING_MODEL
from .paper_lifecycle_rules import LIFECYCLE_VERSION
from .research_trial import fingerprint  # one canonical-JSON fingerprint for every version
from .source_comparison import THRESHOLD, VERSION as CANDIDATE, compare, numeric

SCHEMA = "research-trial-v2"
STYLES = ("scalp", "intraday", "swing")
SYMBOL = re.compile(r"^[A-Z0-9]{1,15}-PERP$")

# The rules a v2 trial's positions must have opened under, frozen by digest as well
# as by name: a parameter changed without a new version would keep the name and
# change the experiment. ``test_research_trial_v2`` fails if they ever disagree.
#
# Re-frozen on 16 September 2026, when the lifecycle reached v3: a fill-depth bound
# and exits that fill in parts. No trial had been registered under v2 rules, so no
# experiment was disturbed; a v2-schema trial admits positions opened under the rules
# named here, which are now v3.
LIFECYCLE_RULES = {
    "version": LIFECYCLE_VERSION,
    "sha256": "a9b3a18738d6db13b96ba7e0296dd03f15c963a113cbd16538f8706cb0392017",
}

# The day the funding observer keeps retrying a closed position's last settlements.
FUNDING_SETTLEMENT_GRACE_S = 86_400


def universe(symbols: Sequence[str] | None) -> list[str]:
    """The configured universe, checked and sorted; an unreadable one registers nothing."""
    if not isinstance(symbols, Sequence) or isinstance(symbols, (str, bytes)):
        raise ValueError("The configured symbol universe must be read from the API before registering")
    seen = {symbol.strip().upper() for symbol in symbols if isinstance(symbol, str) and symbol.strip()}
    if not seen or any(not SYMBOL.fullmatch(symbol) for symbol in seen):
        raise ValueError("The configured symbol universe must be a non-empty list of markets such as BTC-PERP")
    return sorted(seen)


def specification(style: str, symbols: Sequence[str] | None) -> dict[str, Any]:
    """The frozen protocol for one holding style over the universe the API reported."""
    if style not in STYLES:
        raise ValueError("Unsupported holding style")
    return {
        "schema": SCHEMA,
        "style": style,
        "candidate": CANDIDATE,
        "threshold": THRESHOLD,
        "universe": universe(symbols),
        "universe_source": "The Hyperliquid markets market-data reported as tracked when this trial was registered",
        "lifecycle_rules": dict(LIFECYCLE_RULES),
        "entry_evidence_schema": EVIDENCE_SCHEMA,
        "context_family": {"version": FAMILY_VERSION, "sha256": family_digest(), "cells": len(family_cells())},
        "population": (
            "Operator-selected managed-paper entries strictly after registration, in the frozen universe, "
            "opened under the named lifecycle rules with entry evidence of the named schema"
        ),
        "window_days": 30,
        "evaluation": "After the entry window, once every admitted position has closed and its funding has settled",
        "primary_metric": "Mean paired net bps difference per original clean eligible entry",
        "context_comparisons": (
            "Every cell of the pre-declared context family, corrected together; reported beside the primary "
            "metric and never in place of it"
        ),
        "missing_context_policy": "Abstain and report missing coverage separately",
        "observation_gap_policy": "Exclude and report, never repair unseen crossings",
        "funding_policy": (
            "Hyperliquid settled hourly funding, stored per settlement. A closed position with an unsettled hour "
            "stays pending for a day and is then excluded and counted; no rate is ever estimated"
        ),
        "costs": f"Frozen fee schedule, {FILL_MODEL} fills and {FUNDING_MODEL} funding; not settled account costs",
        "minimum_clean_entries_for_review": 100,
        "sample_gate_note": "Operational review floor, not a power calculation or significance guarantee",
        "promotion": "Never automatic; no live execution authority",
        "selection_bias": "Operator selection and overlapping positions remain; not a randomized causal trial",
    }


def _population_reason(spec: Mapping[str, Any], row: Mapping[str, Any], state: Mapping[str, Any],
                       entry_at: Any, registered_at: float, end: float, now: float) -> str | None:
    """Why a record is outside this trial's population, or None when it is inside."""
    if not numeric(entry_at) or not registered_at < entry_at <= min(now, end):
        return "outside_entry_window"
    if state.get("style") != spec["style"]:
        return "other_holding_style"
    if row.get("symbol") not in spec["universe"]:
        return "outside_frozen_universe"
    rules = state.get("rules") if isinstance(state.get("rules"), Mapping) else {}
    if state.get("version") != spec["lifecycle_rules"]["version"] or rules.get("version") != spec["lifecycle_rules"]["version"]:
        return "other_lifecycle_rules"
    evidence = row.get("entry_evidence")
    if not isinstance(evidence, Mapping) or evidence.get("schema_version") != spec["entry_evidence_schema"]:
        return "other_entry_evidence_schema"
    return None


def evaluate(spec: Mapping[str, Any], registered_at: float, now: float, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The forward cohort as it stands: admitted, pending, outside, and what was excluded."""
    if not numeric(registered_at) or not numeric(now) or registered_at <= 0 or now < registered_at:
        raise ValueError("Invalid evaluation clock")
    # Never silently run a changed implementation against an older definition. The
    # universe comes from the stored specification: it was frozen at registration.
    if spec != specification(spec.get("style"), spec.get("universe")):
        raise ValueError("Stored specification needs its matching evaluator version")
    end = registered_at + spec["window_days"] * 86400
    admitted: list[Mapping[str, Any]] = []
    outside: dict[str, int] = {}
    excluded: dict[str, int] = {}
    pending_reasons: dict[str, int] = {}

    for row in rows:
        state = row.get("position_state") if isinstance(row, Mapping) else None
        if not isinstance(state, Mapping):
            excluded["invalid_record"] = excluded.get("invalid_record", 0) + 1
            continue
        reason = _population_reason(spec, row, state, state.get("entry_time"), registered_at, end, now)
        if reason:
            outside[reason] = outside.get(reason, 0) + 1
            continue
        stored = row.get("evidence_sha256")
        if isinstance(stored, str) and stored and evidence_digest(row["entry_evidence"]) != stored:
            excluded["entry_evidence_digest_mismatch"] = excluded.get("entry_evidence_digest_mismatch", 0) + 1
            continue
        if state.get("status") != "closed":
            pending_reasons["open"] = pending_reasons.get("open", 0) + 1
            continue
        exit_at = state.get("exit_time")
        if not numeric(exit_at) or not state["entry_time"] <= exit_at <= now:
            pending_reasons["unresolved_exit"] = pending_reasons.get("unresolved_exit", 0) + 1
            continue
        funding = state.get("funding") if isinstance(state.get("funding"), Mapping) else {}
        if funding.get("status") != "complete":
            if exit_at + FUNDING_SETTLEMENT_GRACE_S <= now:
                excluded["funding_never_settled"] = excluded.get("funding_never_settled", 0) + 1
            else:
                pending_reasons["awaiting_settled_funding"] = pending_reasons.get("awaiting_settled_funding", 0) + 1
            continue
        admitted.append(row)

    result = compare(admitted)
    pending = sum(pending_reasons.values())
    state_name = (
        "collecting" if now <= end
        else "awaiting_outcomes" if pending
        else "insufficient_clean_sample" if result["eligible"] < spec["minimum_clean_entries_for_review"]
        else "ready_for_manual_review"
    )
    return {
        "schema": SCHEMA,
        "state": state_name,
        "entry_window_ends_at": end,
        "pending_outcomes": pending,
        "pending_reasons": pending_reasons,
        "outside_population": sum(outside.values()),
        "outside_reasons": outside,
        "excluded": excluded,
        "comparison": result,
        "promotion_allowed": False,
        "note": (
            "Descriptive interim results are not final evidence. Manual review readiness is not statistical "
            "significance or trading permission. Funding that has not settled keeps a position pending rather "
            "than counting it with an hour missing."
        ),
    }
