"""Turn regime block evidence into an admitted paper signal, or a refusal.

This module is deliberately pure. The live producer and any replay or backtest
run must reach the same verdict from the same evidence, so nothing here reads a
clock, a database, or a network socket.

A refusal is a first-class result, not an error. When the evidence cannot
support a paper opportunity the caller still receives the full reasoning, so an
empty opportunity panel can explain itself instead of looking broken.

Vocabulary used below, in ordinary language:

``weighted_score``
    The rulebook's quality-weighted blend of block scores, between -1 and +1.
    Positive leans long, negative leans short. It is a suitability score, not a
    probability that a trade wins.
``data_coverage``
    How much of the rulebook's total block weight actually had admissible
    evidence behind it. 1.0 means every block reported; 0.0 means none did. It
    describes evidence availability, never confidence in an outcome.
``paper_risk_multiplier``
    A policy cap on paper position size. A reduction is a rule we chose, not a
    prediction about the market.
``deadband``
    A band around zero inside which a score is treated as no direction at all,
    so noise near zero cannot manufacture a long or short.

The policy and the decision's shape live in ``paper_signal_policy``, and the
evidence checks in ``paper_signal_checks``; this module is the decision itself
and the stable import surface for all three.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .paper_signal_checks import (
    _canonical_digest,
    _collect_contributing_features,
    _evidence_age_reasons,
    _number,
    _provenance_reasons,
)
from .paper_signal_policy import (
    DEFAULT_DIRECTION_DEADBAND,
    DEFAULT_DIRECTION_ENTER_THRESHOLD,
    DEFAULT_MAXIMUM_EVIDENCE_AGE_MS,
    DEFAULT_MINIMUM_COVERAGE_TO_EMIT,
    DEFAULT_MINIMUM_DIRECTIONAL_COVERAGE,
    INADMISSIBLE_PROVENANCE,
    SCHEMA_VERSION,
    AdmissionPolicy,
    PaperSignalDecision,
    PaperSignalError,
)

__all__ = [
    "DEFAULT_DIRECTION_DEADBAND",
    "DEFAULT_DIRECTION_ENTER_THRESHOLD",
    "DEFAULT_MAXIMUM_EVIDENCE_AGE_MS",
    "DEFAULT_MINIMUM_COVERAGE_TO_EMIT",
    "DEFAULT_MINIMUM_DIRECTIONAL_COVERAGE",
    "INADMISSIBLE_PROVENANCE",
    "SCHEMA_VERSION",
    "AdmissionPolicy",
    "PaperSignalDecision",
    "PaperSignalError",
    "decide_paper_signal",
]


def decide_paper_signal(
    symbol: str,
    evaluation: Mapping[str, Any],
    feature_results: Sequence[Mapping[str, Any]],
    catalog_summary: Mapping[str, Any],
    evaluated_at_ms: int,
    policy: AdmissionPolicy | None = None,
    directional: Mapping[str, Any] | None = None,
    previous_direction: str | None = None,
) -> PaperSignalDecision:
    """Decide whether the evidence supports one paper signal for ``symbol``.

    ``evaluation`` is the output of ``regime_weights.evaluate_blocks``, which
    scores playbook **suitability** — how tradeable conditions are.

    ``directional`` is ``aggregate_directional_evidence(...).to_dict()`` and is
    the only thing permitted to set LONG or SHORT. Passing ``None`` means no
    directional evidence was supplied, and no direction can be admitted:
    suitability alone never implies a side.
    """

    if not symbol:
        raise PaperSignalError("symbol is required")
    if not isinstance(evaluation, Mapping):
        raise PaperSignalError("evaluation must be a mapping")
    if not isinstance(evaluated_at_ms, int) or isinstance(evaluated_at_ms, bool):
        raise PaperSignalError("evaluated_at_ms must be an integer")

    policy = policy or AdmissionPolicy()

    weighted_score = _number(evaluation.get("weighted_score"))
    data_coverage = _number(evaluation.get("data_coverage"))
    risk_multiplier = _number(evaluation.get("paper_risk_multiplier"))
    if weighted_score is None or data_coverage is None or risk_multiplier is None:
        raise PaperSignalError(
            "evaluation must carry numeric weighted_score, data_coverage and "
            "paper_risk_multiplier"
        )

    contributing = _collect_contributing_features(feature_results)

    reasons: list[dict[str, str]] = []
    reasons.extend(_provenance_reasons(contributing))
    reasons.extend(_evidence_age_reasons(contributing, evaluated_at_ms, policy))

    if not contributing:
        reasons.append(
            {
                "code": "no_admitted_evidence",
                "feature_id": "",
                "detail": (
                    "no feature was admitted for scoring, so there is nothing "
                    "for a paper opportunity to rest on"
                ),
            }
        )

    if data_coverage < policy.minimum_coverage_to_emit:
        reasons.append(
            {
                "code": "coverage_below_emit_floor",
                "feature_id": "",
                "detail": (
                    f"data coverage {data_coverage:.4f} is below the "
                    f"{policy.minimum_coverage_to_emit} floor; missing blocks: "
                    + (", ".join(evaluation.get("missing_blocks") or []) or "none")
                ),
            }
        )

    # Direction is decided ONLY by directional evidence. The blended rulebook
    # score measures suitability: deep two-sided books and tight spreads make a
    # market tradeable, they do not make it a buy.
    directional = directional or {}
    directional_score = _number(directional.get("score"))
    directional_coverage = _number(directional.get("coverage")) or 0.0

    if directional_score is None:
        reasons.append(
            {
                "code": "no_directional_evidence",
                "feature_id": "",
                "detail": (
                    "no feature marked directional in the catalog was ready, so "
                    "no side can be established; suitability alone never implies "
                    "a direction"
                ),
            }
        )
    else:
        # Holding an existing side needs only the exit threshold; establishing
        # a new one needs the higher entry threshold.
        candidate = "LONG" if directional_score > 0 else "SHORT"
        holding = previous_direction in {"LONG", "SHORT"} and previous_direction == candidate
        required = (
            policy.direction_deadband if holding else policy.direction_enter_threshold
        )
        if abs(directional_score) < required:
            reasons.append(
                {
                    "code": "score_inside_deadband",
                    "feature_id": "",
                    "detail": (
                        f"directional score {directional_score:.6f} did not reach the "
                        f"{'±%s hold' % policy.direction_deadband if holding else '±%s entry' % policy.direction_enter_threshold} "
                        f"threshold; treated as no direction rather than a weak one"
                    ),
                }
            )

    if directional_coverage < policy.minimum_directional_coverage:
        admitted_ids = ", ".join(directional.get("admitted_feature_ids") or []) or "none"
        reasons.append(
            {
                "code": "directional_coverage_below_floor",
                "feature_id": "",
                "detail": (
                    f"directional coverage {directional_coverage:.4f} is below the "
                    f"{policy.minimum_directional_coverage} floor; features able to "
                    f"set a direction: {admitted_ids}"
                ),
            }
        )

    if risk_multiplier <= 0:
        reasons.append(
            {
                "code": "paper_risk_fully_capped",
                "feature_id": "",
                "detail": (
                    "the paper risk cap resolved to zero, so no paper position "
                    "size is permitted under this rulebook"
                ),
            }
        )

    admitted = not reasons
    if not admitted or directional_score is None:
        direction = "NONE"
    elif directional_score > 0:
        direction = "LONG"
    else:
        direction = "SHORT"

    evidence = {
        "rulebook_id": evaluation.get("rulebook_id"),
        "rulebook_version": evaluation.get("rulebook_version"),
        "rulebook_digest": evaluation.get("config_digest"),
        "catalog_id": catalog_summary.get("catalog_id"),
        "catalog_version": catalog_summary.get("version"),
        "catalog_digest": catalog_summary.get("digest"),
        "evaluated_at_ms": evaluated_at_ms,
        "contributions": evaluation.get("contributions"),
        "missing_blocks": evaluation.get("missing_blocks"),
        "risk_caps_applied": evaluation.get("risk_caps_applied"),
        "calculation": evaluation.get("calculation"),
        "suitability_note": (
            "weighted_score measures playbook suitability, not direction. "
            "Direction comes only from catalog-directional features."
        ),
        "directional": dict(directional) if directional else None,
        "previous_direction": previous_direction,
        "policy": policy.to_dict(),
    }

    # The digest binds the verdict to the exact evidence and configuration that
    # produced it, so replaying the same window is idempotent rather than
    # creating a second opportunity.
    digest = _canonical_digest(
        {
            "schema_version": SCHEMA_VERSION,
            "symbol": symbol,
            "rulebook_digest": evaluation.get("config_digest"),
            "catalog_digest": catalog_summary.get("digest"),
            "policy": policy.to_dict(),
            "directional": directional.get("contributors") if directional else None,
            "previous_direction": previous_direction,
            "features": [
                {
                    "feature_id": item["feature_id"],
                    "observed_at_ms": item["observed_at_ms"],
                    "score": item["score"],
                    "data_quality": item["data_quality"],
                }
                for item in contributing
            ],
        }
    )

    return PaperSignalDecision(
        admitted=admitted,
        symbol=symbol,
        direction=direction,
        weighted_score=round(weighted_score, 12),
        data_coverage=round(data_coverage, 12),
        directional_score=(
            round(directional_score, 12) if directional_score is not None else None
        ),
        directional_coverage=round(directional_coverage, 12),
        paper_risk_multiplier=risk_multiplier,
        evidence_digest=digest,
        rejection_reasons=reasons,
        contributing_features=list(contributing),
        evidence=evidence,
    )
