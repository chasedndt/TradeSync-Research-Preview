"""Deterministic admission checks for ordered versioned data-plane batches.

These checks run before persistence. PostgreSQL constraints remain the final
durable guard, while this module gives every producer the same refusal reasons.
No check guesses missing lineage or silently sorts an out-of-order batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class QualityIssue:
    code: str
    index: int
    event_id: str | None
    detail: str


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def validate_event_batch(
    events: Iterable[Mapping[str, Any]],
    *,
    now: datetime,
    max_age: timedelta,
    authoritative_sources: set[str] | frozenset[str],
) -> list[QualityIssue]:
    """Return all deterministic quality issues in input order.

    Required fields are ``event_id``, ``observed_at``, ``source``, ``authority``
    and a ``lineage`` mapping holding a non-empty ``source_ref``. Timestamps must
    be timezone-aware, non-decreasing, not in the future, and no older than the
    supplied admission window. An authoritative claim is accepted only from the
    explicitly supplied source set.
    """
    clock = _utc(now)
    if clock is None:
        raise ValueError("now must be timezone-aware")
    if max_age <= timedelta(0):
        raise ValueError("max_age must be positive")

    issues: list[QualityIssue] = []
    seen: set[str] = set()
    previous: datetime | None = None
    for index, event in enumerate(events):
        raw_id = event.get("event_id")
        event_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else None
        if event_id is None:
            issues.append(QualityIssue("missing_event_id", index, None, "event_id is required"))
        elif event_id in seen:
            issues.append(QualityIssue("duplicate_event_id", index, event_id, "event_id repeats in this batch"))
        else:
            seen.add(event_id)

        observed = _utc(event.get("observed_at"))
        if observed is None:
            issues.append(QualityIssue("invalid_timestamp", index, event_id, "observed_at must include a timezone"))
        else:
            if previous is not None and observed < previous:
                issues.append(QualityIssue("timestamp_order", index, event_id, "observed_at moved backwards"))
            previous = observed
            if observed > clock:
                issues.append(QualityIssue("future_event", index, event_id, "observed_at is after the admission clock"))
            elif clock - observed > max_age:
                issues.append(QualityIssue("stale_event", index, event_id, "observed_at is outside the admission window"))

        source = event.get("source")
        authority = event.get("authority")
        if authority == "authoritative" and source not in authoritative_sources:
            issues.append(QualityIssue("source_authority", index, event_id, "source cannot claim authoritative status"))

        lineage = event.get("lineage")
        source_ref = lineage.get("source_ref") if isinstance(lineage, Mapping) else None
        if not isinstance(source_ref, str) or not source_ref.strip():
            issues.append(QualityIssue("missing_lineage", index, event_id, "lineage.source_ref is required"))

    return issues


def admit_event_batch(*args: Any, **kwargs: Any) -> None:
    """Raise one stable refusal containing every quality code when checks fail."""
    issues = validate_event_batch(*args, **kwargs)
    if issues:
        raise ValueError("data quality refused: " + ",".join(issue.code for issue in issues))
