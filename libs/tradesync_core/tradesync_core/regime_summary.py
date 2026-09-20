"""Summarise one market's regime from the evidence behind it, and say why it is not more certain.

The Market page rendered the classifier's four regime labels as four badges and
a confidence word. That is the *output* with none of the *evidence*: a reader
could not see which inputs were read, which were proxies, how old they were,
whether any two disagreed, or why the condition came back ``unknown``. The last
is the worst of them, because a bare "UNKNOWN" reads as "this market is
unknowable" when it almost always means one named input did not arrive.

This module turns that output back into evidence. It is pure — the caller
fetches the snapshot and the stored regime history, and everything here is
arithmetic and naming over what it is given — so the Cockpit reproduces none of
it in TypeScript.

Vocabulary, in ordinary language:

``condition``
    The classifier's market condition (``squeeze_risk``, ``capitulation``,
    ``trending_healthy``, ``choppy``, ``unknown``). It is descriptive: it is
    never a forecast and never a trade direction.
``usable``
    A reading the classifier is allowed to classify from: read from the venue
    (``REAL``) or computed from readings that were (``DERIVED``). A ``PROXY`` is
    present but not usable, which is why it lowers confidence without being a
    gap, and why it can never establish a direction.
``confidence``
    How much of the required evidence was usable, fresh and in agreement. It
    describes the evidence, never the probability that the regime persists.

The guarantee this module exists to keep: whenever ``condition`` is ``unknown``,
``why_not_higher`` is non-empty and ``missing_inputs`` names every input that
was not usable. A caller can render the condition without ever showing an
unexplained "UNKNOWN".
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "regime_summary_v1"

# The inputs the classifier needs before it will name a condition.
REQUIRED_INPUTS: tuple[str, ...] = ("funding", "oi", "volume")
INPUT_LABELS = {"funding": "Funding", "oi": "Open interest", "volume": "Volume", "trend": "Trend"}

# What the classifier may classify from, and what merely counts as present.
USABLE_STATUSES = frozenset({"REAL", "DERIVED"})
PRESENT_STATUSES = frozenset({"REAL", "DERIVED", "PROXY"})

# The same freshness limit the paper signal and the thesis apply to evidence.
DEFAULT_STALE_AFTER_MS = 120_000

UNKNOWN = "unknown"

CONDITION_LABELS = {
    "squeeze_risk": "Squeeze risk",
    "capitulation": "Capitulation",
    "trending_healthy": "Trending, healthy",
    "choppy": "Choppy",
    UNKNOWN: "Not classified",
}

ELEVATED_POSITIVE = frozenset({"elevated_positive", "extreme_positive"})
ELEVATED_NEGATIVE = frozenset({"elevated_negative", "extreme_negative"})
TRENDING = frozenset({"strong_trend", "weak_trend"})

AUTHORITY = "context_only"
NOTE = (
    "A description of the evidence behind the regime, not a forecast and not a trade direction. "
    "Confidence is how much required evidence was usable, fresh and in agreement; it is never a probability."
)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int(value: Any) -> int | None:
    number = _finite(value)
    return None if number is None else int(number)


def _metrics(snapshot: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in (snapshot or {}).get("available_metrics") or []:
        if isinstance(row, Mapping) and row.get("metric"):
            out[str(row["metric"])] = row
    return out


def _seconds(ms: float | None) -> int:
    return int(round((ms or 0) / 1000))


def _reason(key, status, block, stale, age_ms, stale_after_ms, read) -> str | None:
    """Why this input could not be classified from, or None when it could."""
    label = INPUT_LABELS[key]
    if not read:
        return f"{label} was not read at all: market-data did not answer for this market."
    if block is None or status == "UNAVAILABLE":
        return f"{label} is absent from this reading, so the classifier had nothing to read for it."
    if status == "PROXY":
        return f"{label} is a proxy, which counts as present but is never classified from and can set no direction."
    if status == "STALE":
        return f"{label} is marked stale by market-data."
    if stale:
        return f"{label} was last read {_seconds(age_ms)}s ago, past the {_seconds(stale_after_ms)}s limit."
    if status not in USABLE_STATUSES:
        return f"{label} has status {status}, which the classifier does not classify from."
    return None


def components(
    snapshot: Mapping[str, Any] | None,
    now_ms: int,
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> list[dict[str, Any]]:
    """One row per required input: its regime, where it came from, how old it is, and whether it was usable."""
    regimes = (snapshot or {}).get("regimes") or {}
    metrics = _metrics(snapshot)
    read = snapshot is not None
    rows: list[dict[str, Any]] = []
    for key in REQUIRED_INPUTS:
        entry = metrics.get(key)
        status = str((entry or {}).get("status") or ("UNAVAILABLE" if read else "NOT_READ"))
        block = (snapshot or {}).get(key)
        observed = _finite((entry or {}).get("last_updated"))
        age_ms = None if observed is None else max(0, int(now_ms - observed))
        stale = age_ms is not None and age_ms > stale_after_ms
        reason = _reason(key, status, block, stale, age_ms, stale_after_ms, read)
        rows.append({
            "input": key,
            "label": INPUT_LABELS[key],
            "regime": str(regimes.get(key) or UNKNOWN),
            "status": status,
            "present": status in PRESENT_STATUSES and block is not None,
            "usable": reason is None,
            "stale": bool(stale),
            "source": (entry or {}).get("source"),
            "detail": (entry or {}).get("note"),
            "observed_at_ms": _int(observed),
            "age_ms": age_ms,
            "reason": reason,
        })
    return rows


def conflicts(regimes: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Pairs of readings that point opposite ways, each stated in plain words."""
    funding = str(regimes.get("funding") or UNKNOWN)
    oi = str(regimes.get("oi") or UNKNOWN)
    volume = str(regimes.get("volume") or UNKNOWN)
    trend = str(regimes.get("trend") or UNKNOWN)
    found: list[dict[str, Any]] = []
    if funding in ELEVATED_POSITIVE and oi == "unwind":
        found.append({"inputs": ["funding", "oi"],
                      "detail": "Longs are paying to hold while open interest falls: the side paying for the move is leaving it."})
    if funding in ELEVATED_NEGATIVE and oi == "build":
        found.append({"inputs": ["funding", "oi"],
                      "detail": "Shorts are paying to hold while open interest rises: positions are being added against the paying side."})
    if trend in TRENDING and volume == "low":
        found.append({"inputs": ["trend", "volume"],
                      "detail": "A trend is labelled while volume is low, so the move has little participation behind it."})
    if oi == "build" and volume == "low":
        found.append({"inputs": ["oi", "volume"],
                      "detail": "Open interest builds on low volume: positions accumulate without turnover behind them."})
    return found


def transitions(history: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each change of the stored entry-regime label, newest first.

    ``history`` is newest first, one row per opportunity. Consecutive rows
    carrying the same label are one stretch, so a transition is recorded only
    where the label actually changed.
    """
    rows = [r for r in history if isinstance(r, Mapping) and r.get("regime")]
    out: list[dict[str, Any]] = []
    for newer, older in zip(rows, rows[1:]):
        if str(newer["regime"]) != str(older["regime"]):
            out.append({
                "from": str(older["regime"]),
                "to": str(newer["regime"]),
                "at_ms": _int(newer.get("computed_at_ms")),
                "opportunity_id": newer.get("opportunity_id"),
                "trailing_return_pct": _finite(newer.get("trailing_return_pct")),
            })
    return out


def _held(history: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The stored label now in force and how many consecutive readings have carried it."""
    rows = [r for r in history if isinstance(r, Mapping) and r.get("regime")]
    if not rows:
        return None
    label = str(rows[0]["regime"])
    readings = 0
    for row in rows:
        if str(row["regime"]) != label:
            break
        readings += 1
    return {
        "regime": label,
        "readings": readings,
        "since_ms": _int(rows[readings - 1].get("computed_at_ms")),
        "trailing_return_pct": _finite(rows[0].get("trailing_return_pct")),
        "basis": "candles closed before each opportunity's own entry; no price from after the decision",
    }


def _confidence_level(usable: int, conflicting: int) -> str:
    if usable == len(REQUIRED_INPUTS) and conflicting == 0:
        return "high"
    if usable >= 2:
        return "medium"
    return "low"


def _snapshot_age_ms(snapshot: Mapping[str, Any] | None, now_ms: int) -> int | None:
    """How long before this reading the venue was last observed.

    market-data states it only on its list of snapshots; the single-market
    snapshot this summary reads carries just the observation time, which left
    the age unknown beside a known read time. Measured here from that time.
    """
    if snapshot is None:
        return None
    stated = _int(snapshot.get("snapshot_age_ms"))
    if stated is not None:
        return stated
    observed = _int(snapshot.get("ts"))
    return max(0, now_ms - observed) if observed is not None else None


def summarize(
    *,
    symbol: str,
    snapshot: Mapping[str, Any] | None,
    history: Sequence[Mapping[str, Any]] = (),
    now_ms: int,
    venue: str = "hyperliquid",
    stale_after_ms: int = DEFAULT_STALE_AFTER_MS,
) -> dict[str, Any]:
    """The regime, the evidence behind it, what disagrees, and every reason confidence is not higher."""
    regimes = (snapshot or {}).get("regimes") or {}
    rows = components(snapshot, now_ms, stale_after_ms)
    usable = [r for r in rows if r["usable"]]
    unusable = [r for r in rows if not r["usable"]]
    disagreements = conflicts(regimes) if snapshot is not None else []
    condition = str(regimes.get("market_condition") or UNKNOWN).lower()
    level = _confidence_level(len(usable), len(disagreements))

    why: list[str] = [r["reason"] for r in unusable if r["reason"]]
    why += [c["detail"] for c in disagreements]
    if condition == UNKNOWN and not why:
        # Every input was usable and none disagreed, so the condition is unknown
        # because no rule matches this combination. Name the combination rather
        # than leaving "unknown" standing on its own.
        named = ", ".join(f"{INPUT_LABELS[r['input']].lower()} {r['regime']}" for r in rows)
        why.append(
            "Every required input was read and fresh, and none disagreed, but no condition rule matches "
            f"{named}. The market is classified as none of squeeze risk, capitulation, trending or choppy."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "venue": venue,
        "symbol": symbol,
        "read_at_ms": now_ms,
        "observed_at_ms": _int((snapshot or {}).get("ts")),
        "snapshot_age_ms": _snapshot_age_ms(snapshot, now_ms),
        "data_age_ms": _int((snapshot or {}).get("data_age_ms")),
        "source_read": snapshot is not None,
        "current": {
            "condition": condition,
            "label": CONDITION_LABELS.get(condition, condition.replace("_", " ")),
            "known": condition != UNKNOWN,
            "trend": str(regimes.get("trend") or UNKNOWN),
            "trend_basis": "derived from open interest and volume; not an input of its own",
        },
        "confidence": {
            "level": level,
            "usable_inputs": len(usable),
            "required_inputs": len(REQUIRED_INPUTS),
            "share_usable": round(len(usable) / len(REQUIRED_INPUTS), 4),
            "reported_by_market_data": regimes.get("confidence"),
            "reported_note": regimes.get("confidence_note"),
            "basis": "the share of required inputs that were read, fresh and in agreement",
        },
        "components": rows,
        "conflicts": disagreements,
        "missing_inputs": [
            {"input": r["input"], "label": r["label"], "status": r["status"], "reason": r["reason"]}
            for r in unusable
        ],
        "why_not_higher": why,
        "at_highest_confidence": level == "high" and not why,
        "history": {"held": _held(history), "transitions": transitions(history),
                    "source": "opportunity_entry_regimes", "readings": len(history)},
        "authority": AUTHORITY,
        "note": NOTE,
    }
