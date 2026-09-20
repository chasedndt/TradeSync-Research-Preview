"""The evidence checks behind a paper-signal decision.

Moved out of ``paper_signal.py`` unchanged. Each check is pure and returns
reasons rather than raising, because a refusal is a first-class result: which
features carried the score, whether any reading is stale or timestamped in the
future, and whether any came from a provenance that may never set a direction.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .paper_signal_policy import INADMISSIBLE_PROVENANCE, AdmissionPolicy


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _collect_contributing_features(
    feature_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return the features that actually carried the score, newest field first."""

    contributing = []
    for result in feature_results:
        if not isinstance(result, Mapping) or not result.get("scoring_allowed"):
            continue
        contributing.append(
            {
                "feature_id": str(result.get("feature_id", "")),
                "block": result.get("block"),
                "score": _number(result.get("score")),
                "data_quality": _number(result.get("data_quality")),
                "provenance": result.get("provenance"),
                "observed_at_ms": result.get("observed_at_ms"),
                "history_count": result.get("history_count"),
            }
        )
    contributing.sort(key=lambda item: item["feature_id"])
    return contributing


def _evidence_age_reasons(
    contributing: Sequence[Mapping[str, Any]],
    evaluated_at_ms: int,
    policy: AdmissionPolicy,
) -> list[dict[str, str]]:
    """Reject evidence that is stale, or timestamped in the future."""

    reasons = []
    for item in contributing:
        observed_at = item.get("observed_at_ms")
        if not isinstance(observed_at, int) or isinstance(observed_at, bool):
            continue
        age_ms = evaluated_at_ms - observed_at
        if age_ms < 0:
            reasons.append(
                {
                    "code": "evidence_timestamped_in_future",
                    "feature_id": str(item.get("feature_id")),
                    "detail": (
                        f"observed_at is {abs(age_ms)} ms ahead of the evaluation "
                        "time, so the reading cannot be trusted"
                    ),
                }
            )
        elif age_ms > policy.maximum_evidence_age_ms:
            reasons.append(
                {
                    "code": "evidence_stale",
                    "feature_id": str(item.get("feature_id")),
                    "detail": (
                        f"observed_at is {age_ms} ms old, beyond the "
                        f"{policy.maximum_evidence_age_ms} ms admission bound"
                    ),
                }
            )
    return reasons


def _provenance_reasons(
    contributing: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    reasons = []
    for item in contributing:
        provenance = item.get("provenance")
        if provenance in INADMISSIBLE_PROVENANCE:
            reasons.append(
                {
                    "code": "inadmissible_provenance",
                    "feature_id": str(item.get("feature_id")),
                    "detail": (
                        f"provenance '{provenance}' may inform a human but may "
                        "never contribute to a generic directional score"
                    ),
                }
            )
    return reasons
