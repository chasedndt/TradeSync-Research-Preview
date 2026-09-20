"""What one reconciliation finding and one view are: the records every view reports in.

Moved out of ``reconciliation_views`` unchanged, to keep each file to one
responsibility: that module carries the five comparisons and ``combine``; this
one carries the finding and view records they produce, and the two value
readers they share.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    """One disagreement, with the record it is about and enough to act on it."""

    kind: str
    subject_id: str | None
    detail: str
    observed: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "subject_id": self.subject_id, "detail": self.detail,
                "observed": self.observed or {}}


@dataclass(frozen=True)
class View:
    """One comparison: what it compared, over what window, and what it found."""

    name: str
    compared: str
    window: str
    considered: int
    findings: tuple[Finding, ...] = ()
    outside_window: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        clean = not self.findings
        if not self.considered:
            summary = f"nothing to compare: no {self.name.replace('_', ' ')} record in this window"
        elif clean:
            summary = f"{self.considered} record(s) compared with no divergence"
        else:
            summary = f"{len(self.findings)} finding(s) across {self.considered} record(s) compared"
        return {
            "name": self.name,
            "compared": self.compared,
            "window": self.window,
            "considered": self.considered,
            "clean": clean,
            "findings": [finding.to_dict() for finding in self.findings],
            # Records whose counterpart simply predates the window. Never a
            # finding: that would be a divergence invented by a query bound.
            "outside_window": list(self.outside_window),
            "summary": summary,
        }


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)
