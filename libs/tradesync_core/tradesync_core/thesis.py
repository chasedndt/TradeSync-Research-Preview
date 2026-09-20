"""Assemble the SOP's minimum valid thesis from measured evidence.

The Daily Thesis SOP names seven parts: chart structure, anchor levels, a
confirmation stack, invalidation, no-trade conditions, confidence, and the
public/private separation. This module builds exactly that object from what
the system has *measured* — the entry-time regime, venue candles, the scoring
contributors with what each has earned, the skill gate, the economic calendar
and the execution gate. Nothing here is drafted by a model and nothing here
sets a direction of its own: the direction is the paper signal's, and the
confidence is evidence coverage, never a win probability.

Every line carries where it came from and how old it was, because the SOP's
freshness gates refuse a stale thesis rather than render one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .thesis_conditions import (
    HIGH_IMPACT_WINDOW_MINUTES,
    LOW_COVERAGE_BELOW,
    STALE_AFTER_MS,
    NoTradeCondition,
    no_trade_conditions,
)
from .thesis_context import derivatives_line, derivatives_read
from .thesis_levels import _finite, anchor_levels, confirmation_stack, invalidation

SCHEMA_VERSION = "thesis_v1"
VISIBILITY = "private"  # never published; the SOP separates public and private


@dataclass(frozen=True)
class Line:
    """One rendered sentence with its provenance."""

    text: str
    source: str
    captured_at_ms: int | None = None
    age_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source": self.source, "captured_at_ms": self.captured_at_ms, "age_ms": self.age_ms}


def build_thesis(
    *,
    symbol: str,
    now_ms: int,
    regime: Mapping[str, Any] | None,
    signal: Mapping[str, Any] | None,
    source_status: Mapping[str, Any],
    observation_age_ms: int | None,
    candles: Sequence[Mapping[str, Any]],
    bucket_s: int,
    contributors: Sequence[Mapping[str, Any]],
    cards: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any] | None,
    events: Sequence[Mapping[str, Any]],
    execution_enabled: bool,
    feature_results: Sequence[Mapping[str, Any]] = (),
    sources: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The minimum valid thesis, as data plus rendered lines.

    ``sources`` are the source cards: every external source (indicator, agent
    channel, job) with a measured track record. Earned ones join the
    confirmation stack; the rest are counted so the reader can see how much
    of the fleet has been measured at all.
    """
    derivatives = derivatives_read(feature_results, now_ms)
    earned_sources = [s for s in sources if s.get("earned")]
    measured_sources = sum(1 for s in sources if (s.get("claims_measured") or 0) > 0)
    newest_context = max((d["observed_at_ms"] for d in derivatives if d["observed_at_ms"]), default=None)
    direction = str((signal or {}).get("direction") or "NONE")
    coverage = _float((signal or {}).get("data_coverage"))
    directional_score = _float((signal or {}).get("directional_score"))
    signal_at_ms = (signal or {}).get("evaluated_at_ms")
    regime_label = str((regime or {}).get("regime") or "unknown")
    anchors = anchor_levels(candles, bucket_s)
    cards_by = {str(c.get("feature_id")): c for c in cards}
    stack = confirmation_stack(contributors, cards_by)
    earned = sum(1 for s in stack if s["earned"]) + len(earned_sources)
    gate_state = (gate or {}).get("gate")
    source_live = source_status.get("status") == "live"
    conditions = no_trade_conditions(
        gate=gate_state, execution_enabled=execution_enabled, observation_age_ms=observation_age_ms,
        source_live=source_live, coverage=coverage, events=events, earned_count=earned,
    )
    inval = invalidation(direction, anchors, regime_label)
    active = [c for c in conditions if c.active]
    verdict = "NO TRADE" if active else "PAPER READ ONLY"

    lines = [
        Line(
            f"{symbol}: the last hour before the latest paper signal was {regime_label}"
            + (f" ({regime['trailing_return_pct']:+.2f}% trailing)" if _finite((regime or {}).get('trailing_return_pct')) else "")
            + ".",
            "opportunity_entry_regimes (candles closed before entry)",
            _int((regime or {}).get("computed_at_ms")),
            _age(now_ms, (regime or {}).get("computed_at_ms")),
        ),
        Line(
            (f"Paper read is {direction} with directional score {directional_score:+.2f} and evidence coverage {coverage:.2f}"
             + (f" ({signal['read_source']})." if (signal or {}).get("read_source") else ".")
             if direction in ("LONG", "SHORT") and directional_score is not None and coverage is not None
             else "No admitted paper read for this symbol right now."),
            "core-scorer paper signal (regime rulebook)", _int(signal_at_ms), _age(now_ms, signal_at_ms),
        ),
        Line(
            (f"Anchors: 24h {anchors.get('low_24h'):,.2f}–{anchors.get('high_24h'):,.2f}, 4h {anchors.get('low_4h'):,.2f}–{anchors.get('high_4h'):,.2f}, "
             f"1h {anchors.get('low_1h'):,.2f}–{anchors.get('high_1h'):,.2f}, last close {anchors.get('last_close'):,.2f}."
             if anchors.get("high_24h") is not None else "Anchors unavailable: no candles."),
            f"{anchors.get('source')} {bucket_s}s buckets",
            None, None,
        ),
        Line(
            derivatives_line(derivatives),
            "catalog feature results (current values, context-only ones score nothing)",
            newest_context, _age(now_ms, newest_context),
        ),
        Line(
            ("Confirmation stack: " + "; ".join(
                f"{s['feature_id']} reads {s['reads']} ({_score_text(s['score'])}), {str(s['standing'] or 'unknown').replace('_', ' ')}, "
                + ("earned " + ", ".join(s["earned_by"]) if s["earned"] else "weight not yet earned")
                for s in stack
            ) + ".") if stack else "Confirmation stack: no scoring contributors ready.",
            "regime evaluation contributors + evidence cards", _int(signal_at_ms), _age(now_ms, signal_at_ms),
        ),
        Line(
            ("External sources: " + "; ".join(
                f"{s['source_id']} earned {', '.join(s.get('earned_by', []))}" for s in earned_sources
            ) + f" ({measured_sources} of {len(sources)} sources measured).")
            if earned_sources else
            f"External sources: none of {measured_sources} measured source(s) has earned a weight; {len(sources)} sources recording.",
            "source cards (claims extracted from Pine alerts, agent posts and job outputs)", now_ms, 0,
        ),
        Line(
            (f"Invalidation: {inval['rule']} at {inval['level']:,.2f}." if inval.get("level") is not None else f"Invalidation: {inval['rule']}."),
            "anchor levels", None, None,
        ),
        Line(
            "No-trade conditions active: " + ("; ".join(f"{c.code} ({c.detail})" for c in active) if active else "none") + ".",
            "skill gate, evidence cards, execution status, market liveness, economic calendar", now_ms, 0,
        ),
        Line(
            f"Confidence is evidence coverage {coverage:.2f} — the share of the rulebook's weight with admissible evidence, not a win probability."
            if coverage is not None else "Confidence: no coverage figure without an admitted read.",
            "core-scorer data_coverage", _int(signal_at_ms), _age(now_ms, signal_at_ms),
        ),
        Line(f"Verdict: {verdict}. Private thesis; not for publication.", "thesis assembler", now_ms, 0),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "generated_at_ms": now_ms,
        "visibility": VISIBILITY,
        "verdict": verdict,
        "freshness": {
            "source_status": dict(source_status),
            "observation_age_ms": observation_age_ms,
            "stale": observation_age_ms is None or observation_age_ms > STALE_AFTER_MS or not source_live,
            "stale_after_ms": STALE_AFTER_MS,
        },
        "structure": {
            "entry_regime": regime_label,
            "trailing_return_pct": _float((regime or {}).get("trailing_return_pct")),
            "lookback_minutes": (regime or {}).get("lookback_minutes"),
            "direction": direction,
            "directional_score": directional_score,
            "signal_evaluated_at_ms": _int(signal_at_ms),
        },
        "anchors": anchors,
        "derivatives": derivatives,
        "confirmation_stack": stack,
        "sources": {
            "earned": [{"source_id": s.get("source_id"), "source": s.get("source"), "earned_by": list(s.get("earned_by", []))} for s in earned_sources],
            "measured": measured_sources,
            "recording": len(sources),
        },
        "invalidation": inval,
        "no_trade_conditions": [c.to_dict() for c in conditions],
        "confidence": {
            "evidence_coverage": coverage,
            "meaning": "share of rulebook weight with admissible evidence; never a win probability",
        },
        "skill_gate": {"gate": gate_state, "any_economic_edge": bool((gate or {}).get("any_economic_edge", False))},
        "upcoming_events": [dict(e) for e in events[:5]],
        "lines": [line.to_dict() for line in lines],
        "text": "\n".join(line.text for line in lines),
        "note": (
            "Assembled from measured evidence only. Direction is the paper signal's; "
            "confidence is coverage; every line names its source and age. "
            "No model drafted this and nothing here can act."
        ),
    }


def _score_text(v: Any) -> str:
    """A contributor's score as the stack renders it, or said plainly to be missing.

    ``confirmation_stack`` already reads a contributor with no numeric score as
    "flat"; rendering it must not then fail on formatting that score.
    """
    return f"{v:+.2f}" if isinstance(v, (int, float)) else "no reading"


def _float(v: Any) -> float | None:
    return float(v) if _finite(v) else None


def _int(v: Any) -> int | None:
    return int(v) if _finite(v) else None


def _age(now_ms: int, at_ms: Any) -> int | None:
    return now_ms - int(at_ms) if _finite(at_ms) else None
