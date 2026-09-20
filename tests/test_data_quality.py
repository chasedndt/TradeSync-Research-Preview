from datetime import datetime, timedelta, timezone

import pytest

from tradesync_core.data_quality import admit_event_batch, validate_event_batch


NOW = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def event(identity: str, minute: int, **overrides):
    row = {
        "event_id": identity,
        "observed_at": NOW - timedelta(minutes=minute),
        "source": "hyperliquid",
        "authority": "authoritative",
        "lineage": {"source_ref": f"ws:{identity}"},
    }
    row.update(overrides)
    return row


def codes(rows):
    return [issue.code for issue in validate_event_batch(
        rows, now=NOW, max_age=timedelta(minutes=30),
        authoritative_sources={"hyperliquid"},
    )]


def test_valid_ordered_batch_has_no_issues():
    assert codes([event("a", 2), event("b", 1), event("c", 0)]) == []


def test_duplicate_ids_are_refused_without_hiding_other_issues():
    assert codes([event("a", 2), event("a", 1, lineage={})]) == [
        "duplicate_event_id", "missing_lineage"
    ]


def test_timestamp_order_is_checked_as_received_not_silently_sorted():
    assert codes([event("newer", 1), event("older", 2)]) == ["timestamp_order"]


def test_stale_future_and_naive_timestamps_are_distinct():
    rows = [
        event("stale", 31),
        event("future", -1),
        event("naive", 0, observed_at=NOW.replace(tzinfo=None)),
    ]
    assert codes(rows) == ["stale_event", "future_event", "invalid_timestamp"]


def test_only_declared_sources_may_claim_authority():
    assert codes([event("x", 0, source="coingecko")]) == ["source_authority"]
    assert codes([event("x", 0, source="coingecko", authority="context")]) == []


def test_missing_lineage_is_never_invented():
    assert codes([event("x", 0, lineage=None)]) == ["missing_lineage"]


def test_admission_error_has_stable_machine_readable_codes():
    with pytest.raises(ValueError, match="duplicate_event_id,missing_lineage"):
        admit_event_batch(
            [event("x", 1), event("x", 0, lineage={})],
            now=NOW,
            max_age=timedelta(minutes=30),
            authoritative_sources={"hyperliquid"},
        )


def test_clock_and_window_configuration_fail_closed():
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_event_batch([], now=NOW.replace(tzinfo=None), max_age=timedelta(minutes=1), authoritative_sources=set())
    with pytest.raises(ValueError, match="positive"):
        validate_event_batch([], now=NOW, max_age=timedelta(0), authoritative_sources=set())
