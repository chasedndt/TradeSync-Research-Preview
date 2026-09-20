"""Validating a regime rulebook, and binding it to the digest replay evidence needs.

Moved out of ``regime_weights.py`` unchanged. A rulebook is rejected field by
field with the reason named, so a bad configuration never reaches scoring; an
accepted one is deep-copied and digested, so a stored verdict can always be
matched to the exact configuration that produced it. ``regime_weights``
re-exports every public name here.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .feature_weights import (
    FEATURE_WEIGHTS_KEY,
    FeatureWeightError,
    feature_weights_of,
    validate_feature_weights,
)


class RulebookValidationError(ValueError):
    """Raised when a rulebook or score input violates its contract."""


@dataclass(frozen=True)
class RegimeRulebook:
    """Validated rulebook plus the digest needed for replay evidence."""

    data: dict[str, Any]
    digest: str
    weights: dict[str, float]
    compression_k: float
    risk_caps: dict[str, float]

    @property
    def version(self) -> str:
        return str(self.data["version"])

    @property
    def rulebook_id(self) -> str:
        return str(self.data["rulebook_id"])

    @property
    def feature_weights(self) -> dict[str, float]:
        """Per-feature multipliers; empty means every feature counts once."""
        return feature_weights_of(self.data)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_digest(value: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible configuration."""

    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RulebookValidationError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise RulebookValidationError(f"{field} must be finite")
    return number


def validate_rulebook(data: Mapping[str, Any]) -> RegimeRulebook:
    """Validate configuration and return a typed, replayable rulebook."""

    required_text = (
        "schema_version",
        "rulebook_id",
        "version",
        "status",
        "environment",
        "horizon",
    )
    for field in required_text:
        if not isinstance(data.get(field), str) or not str(data[field]).strip():
            raise RulebookValidationError(f"{field} must be a non-empty string")

    if data["schema_version"] != "regime_rulebook_v1":
        raise RulebookValidationError("schema_version must be regime_rulebook_v1")
    if data["status"] not in {"draft", "paper_active", "retired"}:
        raise RulebookValidationError("status must be draft, paper_active, or retired")
    if data["environment"] != "paper":
        raise RulebookValidationError("v1 rulebooks are restricted to paper mode")

    normalization = data.get("normalization")
    if not isinstance(normalization, Mapping):
        raise RulebookValidationError("normalization must be an object")
    if normalization.get("method") != "tanh_zscore":
        raise RulebookValidationError("normalization.method must be tanh_zscore")
    compression_k = _number(normalization.get("compression_k"), "normalization.compression_k")
    if compression_k <= 0:
        raise RulebookValidationError("normalization.compression_k must be greater than 0")

    validation = data.get("validation")
    if not isinstance(validation, Mapping):
        raise RulebookValidationError("validation must be an object")
    expected_sum = _number(validation.get("weight_sum"), "validation.weight_sum")
    tolerance = _number(validation.get("weight_tolerance"), "validation.weight_tolerance")
    max_weight = _number(
        validation.get("max_single_block_weight"),
        "validation.max_single_block_weight",
    )
    if tolerance < 0 or not 0 < max_weight <= 1:
        raise RulebookValidationError("weight tolerance and maximum block weight are invalid")

    blocks = data.get("blocks")
    if not isinstance(blocks, Mapping) or not blocks:
        raise RulebookValidationError("blocks must be a non-empty object")

    weights: dict[str, float] = {}
    for name, block in blocks.items():
        if not isinstance(name, str) or not name:
            raise RulebookValidationError("every block must have a name")
        if not isinstance(block, Mapping):
            raise RulebookValidationError(f"blocks.{name} must be an object")
        weight = _number(block.get("weight"), f"blocks.{name}.weight")
        if weight < 0 or weight > max_weight:
            raise RulebookValidationError(
                f"blocks.{name}.weight must be between 0 and {max_weight}"
            )
        weights[name] = weight

    total_weight = sum(weights.values())
    if not math.isclose(total_weight, expected_sum, abs_tol=tolerance, rel_tol=0):
        raise RulebookValidationError(
            f"block weights sum to {total_weight:.12g}; expected {expected_sum:.12g}"
        )

    quality = data.get("quality")
    if not isinstance(quality, Mapping):
        raise RulebookValidationError("quality must be an object")
    coverage_threshold = _number(
        quality.get("minimum_coverage_for_normal_paper_risk"),
        "quality.minimum_coverage_for_normal_paper_risk",
    )
    if not 0 <= coverage_threshold <= 1:
        raise RulebookValidationError("minimum coverage must be between 0 and 1")

    paper_risk = data.get("paper_risk")
    if not isinstance(paper_risk, Mapping):
        raise RulebookValidationError("paper_risk must be an object")
    if paper_risk.get("combination_rule") != "minimum_cap_wins":
        raise RulebookValidationError("paper_risk.combination_rule must be minimum_cap_wins")

    for field in (
        "base_multiplier",
        "minimum_multiplier",
        "maximum_multiplier",
        "unknown_flag_multiplier",
    ):
        value = _number(paper_risk.get(field), f"paper_risk.{field}")
        if not 0 <= value <= 1:
            raise RulebookValidationError(f"paper_risk.{field} must be between 0 and 1")

    minimum = float(paper_risk["minimum_multiplier"])
    maximum = float(paper_risk["maximum_multiplier"])
    base = float(paper_risk["base_multiplier"])
    if minimum > maximum or not minimum <= base <= maximum:
        raise RulebookValidationError("paper risk minimum, base, and maximum are inconsistent")

    caps = paper_risk.get("caps")
    if not isinstance(caps, Mapping):
        raise RulebookValidationError("paper_risk.caps must be an object")
    risk_caps: dict[str, float] = {}
    for flag, raw_cap in caps.items():
        cap = _number(raw_cap, f"paper_risk.caps.{flag}")
        if not minimum <= cap <= maximum:
            raise RulebookValidationError(
                f"paper_risk.caps.{flag} must be between {minimum} and {maximum}"
            )
        risk_caps[str(flag)] = cap

    try:
        validate_feature_weights(data.get(FEATURE_WEIGHTS_KEY))
    except FeatureWeightError as exc:
        raise RulebookValidationError(str(exc)) from exc

    copied = json.loads(json.dumps(data))
    return RegimeRulebook(
        data=copied,
        digest=config_digest(copied),
        weights=weights,
        compression_k=compression_k,
        risk_caps=risk_caps,
    )


def load_rulebook(path: str | Path) -> RegimeRulebook:
    """Load and validate a rulebook JSON file."""

    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise RulebookValidationError("rulebook root must be an object")
    return validate_rulebook(data)
