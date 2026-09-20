"""A journal record is on disk before append returns, survives a restart, and a torn tail is never believed."""

from __future__ import annotations

import os
import threading

import pytest

from tradesync_core import durable_journal
from tradesync_core.durable_journal import MAX_RECORD_BYTES, DurableJournal, JournalError


def test_records_survive_a_new_instance_in_order(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    first = DurableJournal(path)
    first.append({"kind": "spent", "approval_id": "apr_1"})
    first.append({"kind": "spent", "approval_id": "apr_2"})
    # A restart is a new process with nothing in memory: only the file remains.
    assert DurableJournal(path).records() == [
        {"approval_id": "apr_1", "kind": "spent"},
        {"approval_id": "apr_2", "kind": "spent"},
    ]


def test_an_absent_journal_holds_no_records(tmp_path) -> None:
    assert DurableJournal(tmp_path / "missing.jsonl").records() == []


def test_every_append_is_synced_before_it_returns(tmp_path, monkeypatch) -> None:
    synced: list[int] = []
    real_fsync = os.fsync
    monkeypatch.setattr(durable_journal.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))
    journal = DurableJournal(tmp_path / "journal.jsonl")
    journal.append({"n": 1})
    journal.append({"n": 2})
    assert len(synced) == 2


def test_a_torn_tail_is_ignored_and_cut_before_the_next_append(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    journal = DurableJournal(path)
    journal.append({"nonce": 100})
    # A crash mid-append: half a line, no newline. That append never returned.
    with open(path, "ab") as handle:
        handle.write(b'{"nonce": 1')
    assert DurableJournal(path).records() == [{"nonce": 100}]
    DurableJournal(path).append({"nonce": 101})
    assert DurableJournal(path).records() == [{"nonce": 100}, {"nonce": 101}]
    assert path.read_bytes().count(b"\n") == 2


def test_a_malformed_line_before_the_tail_makes_the_journal_untrustworthy(tmp_path) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b'{"nonce": 1}\nnot json\n{"nonce": 3}\n')
    with pytest.raises(JournalError) as refused:
        DurableJournal(path).records()
    assert "line 2" in str(refused.value)
    path.write_bytes(b'{"nonce": 1}\n[1, 2]\n')
    with pytest.raises(JournalError):
        DurableJournal(path).records()


def test_concurrent_appends_each_land_whole(tmp_path) -> None:
    journal = DurableJournal(tmp_path / "journal.jsonl")
    threads = [threading.Thread(target=lambda i=i: journal.append({"i": i, "pad": "x" * 200})) for i in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    records = DurableJournal(journal.path).records()
    assert sorted(record["i"] for record in records) == list(range(40))


def test_a_record_that_is_not_plain_json_or_too_large_is_refused_and_nothing_is_written(tmp_path) -> None:
    journal = DurableJournal(tmp_path / "journal.jsonl")
    with pytest.raises(JournalError):
        journal.append({"when": object()})
    with pytest.raises(JournalError):
        journal.append({"nan": float("nan")})
    with pytest.raises(JournalError):
        journal.append({"blob": "x" * MAX_RECORD_BYTES})
    assert journal.records() == []


def test_an_unwritable_location_raises_instead_of_pretending(tmp_path) -> None:
    # A directory where the file should be: the open fails on every platform.
    blocked = tmp_path / "journal.jsonl"
    blocked.mkdir()
    with pytest.raises(JournalError) as refused:
        DurableJournal(blocked).append({"n": 1})
    assert "could not be written" in str(refused.value)
