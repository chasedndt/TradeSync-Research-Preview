"""Scoring a set of blocks under a rulebook, and the paper-risk cap that goes with it.

Moved out of ``regime_weights.py`` unchanged. The score is a quality-weighted
blend, a missing block counts as quality zero rather than as a neutral reading,
and paper risk is separate from the score: the most conservative active cap
wins, and a flag the rulebook does not know fails closed.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .rulebook_validation import RegimeRulebook, RulebookValidationError, _number


def bounded_z_score(z_value: float, compression_k: float = 2.0) -> float:
    """Compress any finite z-score into the open interval (-1, 1)."""

    z = _number(z_value, "z_value")
    k = _number(compression_k, "compression_k")
    if k <= 0:
        raise RulebookValidationError("compression_k must be greater than 0")
    result = math.tanh(z / k)
    # Mathematically tanh only approaches the endpoints. IEEE-754 floating
    # point rounds sufficiently extreme finite inputs to exactly +/-1, so keep
    # the documented open-interval contract explicit at machine precision.
    if result >= 1.0:
        return math.nextafter(1.0, 0.0)
    if result <= -1.0:
        return math.nextafter(-1.0, 0.0)
    return result


def _validate_named_values(
    values: Mapping[str, Any],
    configured_names: set[str],
    field: str,
    minimum: float,
    maximum: float,
) -> dict[str, float]:
    if not isinstance(values, Mapping):
        raise RulebookValidationError(f"{field} must be an object")
    unknown = sorted(set(values) - configured_names)
    if unknown:
        raise RulebookValidationError(f"{field} contains unknown blocks: {', '.join(unknown)}")

    result: dict[str, float] = {}
    for name, raw_value in values.items():
        value = _number(raw_value, f"{field}.{name}")
        if not minimum <= value <= maximum:
            raise RulebookValidationError(
                f"{field}.{name} must be between {minimum} and {maximum}"
            )
        result[name] = value
    return result


def evaluate_blocks(
    rulebook: RegimeRulebook,
    block_scores: Mapping[str, Any],
    data_quality: Mapping[str, Any] | None = None,
    risk_flags: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Calculate a quality-adjusted score and deterministic paper-risk cap.

    The directional/suitability score is:

        sum(weight * quality * score) / sum(weight * quality)

    Missing blocks receive quality zero. Paper risk is separate: the most
    conservative active cap wins, and unknown flags fail closed.
    """

    configured_names = set(rulebook.weights)
    scores = _validate_named_values(
        block_scores,
        configured_names,
        "block_scores",
        -1.0,
        1.0,
    )
    qualities = _validate_named_values(
        data_quality or {},
        configured_names,
        "data_quality",
        0.0,
        1.0,
    )

    contributions: dict[str, dict[str, float]] = {}
    numerator = 0.0
    effective_weight = 0.0
    missing_blocks: list[str] = []

    for name, weight in rulebook.weights.items():
        if name not in scores:
            score = 0.0
            quality_value = 0.0
            missing_blocks.append(name)
        else:
            score = scores[name]
            quality_value = qualities.get(name, 1.0)

        weighted_quality = weight * quality_value
        contribution = weighted_quality * score
        numerator += contribution
        effective_weight += weighted_quality
        contributions[name] = {
            "weight": weight,
            "score": score,
            "quality": quality_value,
            "weighted_quality": round(weighted_quality, 12),
            "raw_contribution": round(contribution, 12),
        }

    weighted_score = numerator / effective_weight if effective_weight > 0 else 0.0
    coverage = effective_weight

    if isinstance(risk_flags, (str, bytes)) or (
        risk_flags is not None and not isinstance(risk_flags, Sequence)
    ):
        raise RulebookValidationError("risk_flags must be an array of strings")
    flags: list[str] = []
    for flag in risk_flags or []:
        if not isinstance(flag, str) or not flag:
            raise RulebookValidationError("risk_flags must contain non-empty strings")
        if flag not in flags:
            flags.append(flag)

    quality_config = rulebook.data["quality"]
    if coverage == 0:
        if "no_data_coverage" not in flags:
            flags.append("no_data_coverage")
    elif coverage < float(quality_config["minimum_coverage_for_normal_paper_risk"]):
        if "low_data_coverage" not in flags:
            flags.append("low_data_coverage")

    paper_risk = rulebook.data["paper_risk"]
    caps_applied: list[dict[str, Any]] = []
    cap_values = [float(paper_risk["base_multiplier"])]
    for flag in flags:
        known = flag in rulebook.risk_caps
        cap = (
            rulebook.risk_caps[flag]
            if known
            else float(paper_risk["unknown_flag_multiplier"])
        )
        cap_values.append(cap)
        caps_applied.append({"flag": flag, "cap": cap, "known": known})

    risk_multiplier = min(cap_values)
    risk_multiplier = max(float(paper_risk["minimum_multiplier"]), risk_multiplier)
    risk_multiplier = min(float(paper_risk["maximum_multiplier"]), risk_multiplier)

    return {
        "rulebook_id": rulebook.rulebook_id,
        "rulebook_version": rulebook.version,
        "config_digest": rulebook.digest,
        "weighted_score": round(weighted_score, 12),
        "data_coverage": round(coverage, 12),
        "paper_risk_multiplier": risk_multiplier,
        "contributions": contributions,
        "missing_blocks": missing_blocks,
        "risk_caps_applied": caps_applied,
        "calculation": "sum(weight * quality * score) / sum(weight * quality)",
    }
