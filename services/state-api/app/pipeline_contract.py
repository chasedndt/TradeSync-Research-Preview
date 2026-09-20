"""The integration pipeline's shared vocabulary.

Moved out of ``app/integration_pipeline.py`` unchanged: what a node and a
recovery action look like in the contract, which states count as healthy, and
what counts as fresh evidence. ``app.integration_pipeline`` re-exports every
name here, so existing imports keep working.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


HEALTHY_STATES = {"live", "healthy"}


def _freshness_evidence(readiness: dict[str, Any]) -> str:
    """One line describing whether observations are actually arriving."""
    symbols = readiness.get("symbols") or []
    if not symbols:
        return "Snapshot freshness: not reported by market-data"
    ages = [
        f"{item.get('symbol')} {item.get('age_seconds')}s"
        for item in symbols
        if item.get("age_seconds") is not None
    ]
    state = "fresh" if readiness.get("ready") else readiness.get("reason", "not ready")
    return f"Snapshot freshness ({state}): " + (", ".join(ages) or "no timestamps")

# How recent a stored signal or opportunity must be to count as live evidence.
RECORD_FRESHNESS_SECONDS = int(os.getenv("PIPELINE_RECORD_FRESHNESS_SECONDS", "900"))


def _is_recent(iso_timestamp: str | None) -> bool:
    """Return whether an ISO timestamp is inside the freshness window."""
    if not iso_timestamp:
        return False
    try:
        recorded = datetime.fromisoformat(iso_timestamp)
    except ValueError:
        return False
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - recorded).total_seconds()
    return 0 <= age <= RECORD_FRESHNESS_SECONDS


def _recovery(
    kind: str,
    label: str,
    target: str,
    command: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "label": label,
        "target": target,
        "command": command,
    }


def _node(
    *,
    node_id: str,
    label: str,
    owner: str,
    tier: str,
    stage: str,
    status: str,
    required_for_tier_a: bool,
    authority: str,
    summary: str,
    evidence: list[str],
    missing: list[str],
    impact: str,
    recovery: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "owner": owner,
        "tier": tier,
        "stage": stage,
        "status": status,
        "required_for_tier_a": required_for_tier_a,
        "authority": authority,
        "summary": summary,
        "evidence": evidence,
        "missing": missing,
        "impact": impact,
        "recovery": recovery,
    }
