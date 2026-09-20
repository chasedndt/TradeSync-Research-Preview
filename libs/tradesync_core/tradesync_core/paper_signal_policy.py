"""The policy a paper-signal decision is taken under, and the shape of the decision.

Moved out of ``paper_signal.py`` unchanged. The thresholds are chosen research
settings, not measured facts, and they are recorded on every decision so a stored
signal can be re-read later against the policy that produced it.
``paper_signal`` re-exports every public name here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "paper_signal_v1"

# Policy constants. These are chosen research settings, not measured facts, and
# they are recorded on every decision so a stored signal can be re-read later
# against the policy that produced it.
DEFAULT_MINIMUM_COVERAGE_TO_EMIT = 0.30
# Direction is established only by features the catalog marks directional.
# Today exactly one is admitted, so this floor is what stops a single
# half-collected feature from setting a trade direction on its own.
DEFAULT_MINIMUM_DIRECTIONAL_COVERAGE = 0.50
# Hysteresis. Establishing a NEW direction requires clearing the entry
# threshold; an EXISTING direction is held until the score falls back through
# the lower exit threshold. A single symmetric band makes the side flip every
# time a score hovering near zero crosses it, which is noise, not a regime.
DEFAULT_DIRECTION_DEADBAND = 0.05
DEFAULT_DIRECTION_ENTER_THRESHOLD = 0.15
DEFAULT_MAXIMUM_EVIDENCE_AGE_MS = 120_000

INADMISSIBLE_PROVENANCE = frozenset({"proxy", "context_only", "unavailable"})


class PaperSignalError(ValueError):
    """Raised only for malformed input, never for an ordinary refusal."""


@dataclass(frozen=True)
class AdmissionPolicy:
    """The versioned thresholds a decision was taken under."""

    minimum_coverage_to_emit: float = DEFAULT_MINIMUM_COVERAGE_TO_EMIT
    minimum_directional_coverage: float = DEFAULT_MINIMUM_DIRECTIONAL_COVERAGE
    direction_deadband: float = DEFAULT_DIRECTION_DEADBAND
    direction_enter_threshold: float = DEFAULT_DIRECTION_ENTER_THRESHOLD
    maximum_evidence_age_ms: int = DEFAULT_MAXIMUM_EVIDENCE_AGE_MS

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum_coverage_to_emit": self.minimum_coverage_to_emit,
            "minimum_directional_coverage": self.minimum_directional_coverage,
            "direction_deadband": self.direction_deadband,
            "direction_enter_threshold": self.direction_enter_threshold,
            "maximum_evidence_age_ms": self.maximum_evidence_age_ms,
            "note": (
                "Policy thresholds are research settings, not measured facts. "
                "Coverage describes evidence availability, not win probability. "
                "Suitability describes how tradeable conditions are and never "
                "sets a direction."
            ),
        }


@dataclass(frozen=True)
class PaperSignalDecision:
    """Either an admitted paper signal or an explained refusal."""

    admitted: bool
    symbol: str
    direction: str
    weighted_score: float
    data_coverage: float
    directional_score: float | None
    directional_coverage: float
    paper_risk_multiplier: float
    evidence_digest: str
    rejection_reasons: list[dict[str, str]] = field(default_factory=list)
    contributing_features: list[dict[str, Any]] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": "paper_shadow",
            "execution_authority": False,
            "admitted": self.admitted,
            "symbol": self.symbol,
            "direction": self.direction,
            "weighted_score": self.weighted_score,
            "suitability_score": self.weighted_score,
            "data_coverage": self.data_coverage,
            "directional_score": self.directional_score,
            "directional_coverage": self.directional_coverage,
            "paper_risk_multiplier": self.paper_risk_multiplier,
            "evidence_digest": self.evidence_digest,
            "rejection_reasons": self.rejection_reasons,
            "contributing_features": self.contributing_features,
            "evidence": self.evidence,
        }
