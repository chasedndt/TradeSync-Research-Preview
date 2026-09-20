"""Every reason not to trade, each stated whether or not it is active.

Moved out of ``thesis.py`` unchanged. A thesis lists all six conditions every
time — active or not — so a reader sees what was checked, not only what fired.
``thesis`` re-exports every public name here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

STALE_AFTER_MS = 120_000
HIGH_IMPACT_WINDOW_MINUTES = 120
LOW_COVERAGE_BELOW = 0.5


@dataclass
class NoTradeCondition:
    code: str
    active: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "active": self.active, "detail": self.detail}


def no_trade_conditions(
    *,
    gate: str | None,
    execution_enabled: bool,
    observation_age_ms: int | None,
    source_live: bool,
    coverage: float | None,
    events: Sequence[Mapping[str, Any]],
    earned_count: int,
) -> list[NoTradeCondition]:
    """Every reason not to trade, each stated whether or not it is active."""
    soon = [
        e for e in events
        if e.get("impact") == "High" and isinstance(e.get("minutes_until"), int)
        and 0 <= e["minutes_until"] <= HIGH_IMPACT_WINDOW_MINUTES
    ]
    stale = observation_age_ms is None or observation_age_ms > STALE_AFTER_MS or not source_live
    return [
        NoTradeCondition("no_demonstrated_edge", gate != "OPEN",
                         "skill gate is CLOSED: no cell shows economic edge after costs" if gate != "OPEN" else "skill gate reports economic edge in at least one cell"),
        NoTradeCondition("no_earned_inputs", earned_count == 0,
                         "no scoring input has earned its weight on the evidence cards" if earned_count == 0 else f"{earned_count} input(s) have earned a weight"),
        NoTradeCondition("execution_disabled", not execution_enabled,
                         "EXECUTION_ENABLED is false: paper only" if not execution_enabled else "execution gate open"),
        NoTradeCondition("stale_evidence", stale,
                         "market observations are stale or the source is not live" if stale else "observations current"),
        NoTradeCondition("low_coverage", coverage is None or coverage < LOW_COVERAGE_BELOW,
                         f"evidence coverage {coverage if coverage is not None else 'unknown'} below {LOW_COVERAGE_BELOW}" if coverage is None or coverage < LOW_COVERAGE_BELOW else f"evidence coverage {coverage:.2f}"),
        NoTradeCondition("high_impact_event_near", bool(soon),
                         ("; ".join(f"{e.get('title')} in {e.get('minutes_until')} min" for e in soon[:3])) if soon else f"no High-impact event within {HIGH_IMPACT_WINDOW_MINUTES} min"),
    ]
