"""The agent harness switch: a request issues a command, a command is claimed and reported once, and every step is audited."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import pytest

from app import harness_control_store as store


@pytest.fixture(autouse=True)
def fresh_memory():
    store.reset_memory()
    yield
    store.reset_memory()


def run(coro):
    return asyncio.run(coro)


def kinds(events):
    return [event["kind"] for event in events]


def test_installed_it_is_running_with_no_command_and_no_history() -> None:
    row = run(store.current(None))
    assert row["desired_state"] == "running" and row["operator"] == "migration 034" and row["command_id"] is None
    assert row["result_command_id"] is None and run(store.history(None)) == []


def test_a_stop_issues_a_new_command_and_audits_who_why_and_what_it_replaced() -> None:
    row, previous = run(store.request(None, "stopped", "chase", "Hermes compute needed elsewhere"))
    assert previous == "running" and row["desired_state"] == "stopped" and isinstance(row["command_id"], uuid.UUID)
    assert (row["operator"], row["reason"]) == ("chase", "Hermes compute needed elsewhere")
    [event] = run(store.history(None))
    assert event["kind"] == "requested" and event["command_id"] == row["command_id"] and event["previous_state"] == "running"
    assert (event["operator"], event["reason"], event["desired_state"]) == ("chase", "Hermes compute needed elsewhere", "stopped")
    again, previous = run(store.request(None, "running", "chase", "Maintenance finished"))
    assert previous == "stopped" and again["command_id"] != row["command_id"]
    assert kinds(run(store.history(None))) == ["requested", "requested"]


def test_the_current_command_is_claimed_once_and_reported_once() -> None:
    row, _ = run(store.request(None, "stopped", "chase", "Stop for the weekend"))
    command = row["command_id"]
    assert run(store.claim(None, command)) == "claimed"
    assert run(store.claim(None, command)) == "already_claimed"
    assert run(store.report(None, command, "applied", "hermes gateway stop", 0, "inactive", "the gateway is stopped")) == "recorded"
    assert run(store.report(None, command, "failed", "hermes gateway stop", 1, "active", "")) == "duplicate"
    assert run(store.claim(None, command)) == "reported"
    after = run(store.current(None))
    assert (after["result_command_id"], after["result_status"], after["result_exit_status"], after["result_is_active"]) == (
        command, "applied", 0, "inactive")
    assert after["claimed_command_id"] == command and after["claimed_at"] is not None
    assert kinds(run(store.history(None))) == ["applied", "applying", "requested"]


def test_a_superseded_or_unknown_command_is_never_claimed() -> None:
    first, _ = run(store.request(None, "stopped", "chase", "Stop for the weekend"))
    second, _ = run(store.request(None, "running", "chase", "Changed my mind"))
    assert run(store.claim(None, first["command_id"])) == "superseded"
    assert run(store.claim(None, uuid.uuid4())) == "unknown"
    assert run(store.report(None, uuid.uuid4(), "applied", "x", 0, "active", "")) == "unknown"
    assert run(store.claim(None, second["command_id"])) == "claimed"
    assert kinds(run(store.history(None))) == ["applying", "requested", "requested"]


def test_a_late_result_for_an_older_command_is_audited_but_keeps_the_current_result() -> None:
    older, _ = run(store.request(None, "running", "chase", "Start it again"))
    newer, _ = run(store.request(None, "stopped", "chase", "Stop it after all"))
    assert run(store.report(None, newer["command_id"], "applied", "stop", 0, "inactive", "")) == "recorded"
    assert run(store.report(None, older["command_id"], "failed", "start", None, "unknown", "interrupted")) == "recorded"
    row = run(store.current(None))
    assert row["result_command_id"] == newer["command_id"] and row["result_status"] == "applied"
    assert kinds(run(store.history(None)))[:2] == ["failed", "applied"]


def test_a_missing_control_row_refuses_every_change() -> None:
    store._memory["row"] = None
    assert run(store.current(None)) is None
    with pytest.raises(store.ControlMissing):
        run(store.request(None, "stopped", "chase", "Stop it now"))
    with pytest.raises(store.ControlMissing):
        run(store.claim(None, uuid.uuid4()))
    with pytest.raises(store.ControlMissing):
        run(store.report(None, uuid.uuid4(), "applied", "x", 0, "inactive", ""))


class Conn:
    """The statements the store issues, in order, answered as the database would for these tests."""

    def __init__(self, row, events=()):
        self.row = dict(row) if row else None
        self.events = list(events)
        self.log: list[tuple[str, tuple, bool]] = []
        self.in_transaction = False

    def transaction(self):
        @asynccontextmanager
        async def tx():
            self.in_transaction = True
            try:
                yield
            finally:
                self.in_transaction = False

        return tx()

    async def fetchrow(self, sql, *args):
        self.log.append((sql, args, self.in_transaction))
        if sql == store.REQUEST_SQL:
            self.row.update(desired_state=args[0], operator=args[1], reason=args[2], command_id=args[3])
        return dict(self.row) if self.row else None

    async def fetch(self, sql, *args):
        self.log.append((sql, args, self.in_transaction))
        return [event for event in self.events if event["command_id"] == args[0]]

    async def execute(self, sql, *args):
        self.log.append((sql, args, self.in_transaction))
        if sql == store.EVENT_SQL:
            self.events.append({"kind": args[1], "command_id": args[2], "desired_state": args[3]})


def pool_for(conn):
    class Pool:
        def acquire(self):
            @asynccontextmanager
            async def acquired():
                yield conn

            return acquired()

    return Pool()


SEED = {"desired_state": "running", "operator": "migration 034", "reason": store.SEED_REASON, "requested_at": None,
        "command_id": None, "claimed_command_id": None, "claimed_at": None, "result_command_id": None, "result_status": None,
        "result_command": None, "result_exit_status": None, "result_is_active": None, "result_detail": None, "result_at": None}


def test_with_a_database_a_request_locks_the_row_then_writes_the_change_and_its_audit_row_together() -> None:
    conn = Conn(SEED)
    row, previous = run(store.request(pool_for(conn), "stopped", "chase", "Stop for the weekend"))
    assert [(sql, in_tx) for sql, _, in_tx in conn.log] == [(store.LOCK_SQL, True), (store.REQUEST_SQL, True), (store.EVENT_SQL, True)]
    assert conn.log[2][1][1:7] == ("requested", row["command_id"], "stopped", "running", "chase", "Stop for the weekend")
    assert previous == "running"
    with pytest.raises(store.ControlMissing):
        run(store.request(pool_for(Conn(None)), "stopped", "chase", "Stop for the weekend"))


def test_with_a_database_a_claim_and_a_report_are_written_only_when_new() -> None:
    command = uuid.uuid4()
    conn = Conn({**SEED, "desired_state": "stopped", "command_id": command},
                events=[{"kind": "requested", "command_id": command, "desired_state": "stopped"}])
    pool = pool_for(conn)
    assert run(store.claim(pool, command)) == "claimed"
    assert run(store.claim(pool, command)) == "already_claimed"
    assert run(store.report(pool, command, "applied", "hermes gateway stop", 0, "inactive", "")) == "recorded"
    assert run(store.report(pool, command, "applied", "hermes gateway stop", 0, "inactive", "")) == "duplicate"
    writes = [sql for sql, _, _ in conn.log if sql in (store.CLAIM_SQL, store.RESULT_SQL, store.EVENT_SQL)]
    assert writes == [store.CLAIM_SQL, store.EVENT_SQL, store.RESULT_SQL, store.EVENT_SQL]
    assert all(in_tx for _, _, in_tx in conn.log)
    result_event = [args for sql, args, _ in conn.log if sql == store.EVENT_SQL][-1]
    assert result_event[1:4] == ("applied", command, "stopped") and result_event[7:10] == ("hermes gateway stop", 0, "inactive")
