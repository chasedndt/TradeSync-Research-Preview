#!/usr/bin/env python
"""Isolated, rolled-back SQL acceptance for migration 034 and the agent harness control store.

One connection and one transaction, rolled back at the end, in a throwaway schema:

1. 034 UP. The seed (running, no command), the one-row rule, the check constraints, the
   append-only trigger and the one-request, one-claim, one-result-per-command index are checked,
   inside a savepoint that is then rolled back.
2. state-api's own store and gate (``app.harness_control_store``, ``app.harness_gate``) run against
   the real tables: a stop and its refusal text, its claim, its result, a duplicate result, a start
   superseded before it was claimed, a late result for that older command, history in order, and
   the gate opening again after a start.
3. 034 DOWN leaves nothing in the schema, and the gate then refuses because the switch cannot be
   read; 034 UP again restores the seed.

Unqualified names resolve only inside the throwaway schema (``SET LOCAL search_path``). The DSN is
required, meant for a throwaway ``postgres:16`` container, and nothing is read from the environment.

    docker run --rm -d --name qa-harness-control-034 -e POSTGRES_USER=qa -e POSTGRES_PASSWORD=qa \
        -e POSTGRES_DB=qa -p 127.0.0.1:55434:5432 postgres:16
    python tools/qa_harness_control_sql.py --dsn postgresql://qa:qa@127.0.0.1:55434/qa
    docker rm -f qa-harness-control-034
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

import asyncpg  # noqa: E402

from app import harness_control_store as store  # noqa: E402
from app import harness_gate  # noqa: E402
from ops.migrate import up_sql  # noqa: E402

SCHEMA = "qa_harness_control_034"
MIGRATION = ROOT / "ops" / "migrations" / "034_agent_harness_control.sql"
EVENT = "INSERT INTO agent_harness_control_events (kind, command_id, desired_state, previous_state, operator, reason, detail) "


class OneConnection:
    """A pool of one connection: the store's own transactions become savepoints in the acceptance transaction."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def acquire(self):
        @asynccontextmanager
        async def acquired():
            yield self.conn

        return acquired()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"QA FAIL: {message}")
    print(f"ok   {message}")


async def refused(conn, statement: str, sqlstate: str, message: str, *args) -> None:
    try:
        async with conn.transaction():
            await conn.execute(statement, *args)
    except asyncpg.PostgresError as exc:
        check(exc.sqlstate == sqlstate, f"{message} (SQLSTATE {exc.sqlstate})")
        return
    raise AssertionError(f"QA FAIL: {message}: the statement was accepted")


async def migration_checks(conn) -> None:
    rows = await conn.fetch("SELECT * FROM agent_harness_control")
    check(len(rows) == 1 and rows[0]["desired_state"] == "running" and rows[0]["command_id"] is None
          and rows[0]["operator"] == "migration 034" and rows[0]["result_status"] is None, "034 UP seeds one running row with no command")
    await refused(conn, "INSERT INTO agent_harness_control (singleton) VALUES (true)", "23505", "a second control row is refused")
    await refused(conn, "INSERT INTO agent_harness_control (singleton) VALUES (false)", "23514", "a row that is not the singleton is refused")
    await refused(conn, "UPDATE agent_harness_control SET desired_state = 'paused'", "23514", "a state other than running or stopped is refused")
    await refused(conn, "UPDATE agent_harness_control SET reason = 'bad'", "23514", "a reason under 5 characters is refused")
    await refused(conn, "UPDATE agent_harness_control SET reason = repeat('x', 241)", "23514", "a reason over 240 characters is refused")
    await refused(conn, "UPDATE agent_harness_control SET operator = '   '", "23514", "a blank operator is refused")
    await refused(conn, "UPDATE agent_harness_control SET result_status = 'applied'", "23514", "a result without its command and time is refused")
    await refused(conn, "UPDATE agent_harness_control SET claimed_at = now()", "23514", "a claim time without a claimed command is refused")
    command = uuid.uuid4()
    await conn.execute(EVENT + "VALUES ('requested', $1, 'stopped', 'running', 'qa', 'acceptance check', NULL)", command)
    await refused(conn, EVENT + "VALUES ('requested', $1, 'stopped', 'running', 'qa', 'second request', NULL)", "23505",
                  "a second request row for one command is refused", command)
    await conn.execute(EVENT + "VALUES ('applied', $1, 'stopped', NULL, NULL, NULL, 'qa')", command)
    await refused(conn, EVENT + "VALUES ('failed', $1, 'stopped', NULL, NULL, NULL, 'qa')", "23505",
                  "a failed result after an applied one for the same command is refused", command)
    await refused(conn, EVENT + "VALUES ('requested', $1, 'stopped', NULL, NULL, NULL, NULL)", "23514",
                  "a request row without operator, reason and previous state is refused", uuid.uuid4())
    await refused(conn, EVENT + "VALUES ('approved', $1, 'stopped', NULL, NULL, NULL, NULL)", "23514", "an unknown event kind is refused",
                  uuid.uuid4())
    await refused(conn, "UPDATE agent_harness_control_events SET detail = 'rewritten'", "P0001", "an audit row cannot be updated")
    await refused(conn, "DELETE FROM agent_harness_control_events", "P0001", "an audit row cannot be deleted")


async def store_checks(pool) -> None:
    row, previous = await store.request(pool, "stopped", "qa operator", "Stop Hermes for the acceptance run")
    stop_id = uuid.UUID(str(row["command_id"]))
    check(previous == "running" and row["desired_state"] == "stopped", "a stop issues a command and returns the state it replaced")
    reason = await harness_gate.refusal(pool)
    check(reason is not None and "stopped by qa operator" in reason and "Stop Hermes for the acceptance run" in reason,
          "while stopped the gate refuses, naming who and why")
    check(await store.claim(pool, stop_id) == "claimed", "the host claims the stop")
    check(await store.claim(pool, stop_id) == "already_claimed", "a claimed command is not handed out again")
    check(await store.report(pool, stop_id, "applied", "wsl.exe -d Ubuntu -- hermes gateway stop", 0, "inactive",
                             "the gateway is stopped") == "recorded", "the result is recorded")
    check(await store.report(pool, stop_id, "failed", "again", 1, "active", "") == "duplicate", "a second result for one command is not recorded")
    current = await store.current(pool)
    check((str(current["result_command_id"]), current["result_status"], current["result_exit_status"], current["result_is_active"])
          == (str(stop_id), "applied", 0, "inactive") and current["result_at"] is not None, "the control row holds the host result and its time")
    check(str(current["claimed_command_id"]) == str(stop_id) and current["claimed_at"] is not None, "the control row holds the claim")

    start_row, _ = await store.request(pool, "running", "qa operator", "Start it again")
    again_row, _ = await store.request(pool, "stopped", "qa operator", "Stop after all")
    start_id, again_id = uuid.UUID(str(start_row["command_id"])), uuid.UUID(str(again_row["command_id"]))
    check(await store.claim(pool, start_id) == "superseded", "a command replaced before it was claimed is never claimed")
    check(await store.claim(pool, again_id) == "claimed", "the newest command is claimed")
    check(await store.report(pool, again_id, "applied", "stop", 0, "inactive", "") == "recorded", "the newest result is recorded")
    check(await store.report(pool, start_id, "failed", "start", None, "unknown", "late") == "recorded", "a late result for the older command is audited")
    check(str((await store.current(pool))["result_command_id"]) == str(again_id), "a late result does not replace the current result")
    check(await store.claim(pool, uuid.uuid4()) == "unknown", "an unknown command is not claimed")
    check(await store.report(pool, uuid.uuid4(), "applied", "x", 0, "inactive", "") == "unknown", "an unknown command gets no result")

    history = await store.history(pool, 50)
    check([event["kind"] for event in history] == ["failed", "applied", "applying", "requested", "requested", "applied", "applying", "requested"],
          "history lists every request, claim and result, newest first")
    check(history[-1]["operator"] == "qa operator" and history[-1]["previous_state"] == "running", "the first request keeps who and what it replaced")
    await store.request(pool, "running", "qa operator", "Acceptance finished")
    check(await harness_gate.refusal(pool) is None, "after a start the gate opens")


async def accept(dsn: str) -> None:
    text = MIGRATION.read_text(encoding="utf-8-sig")
    up, down = up_sql(text), text.split("-- DOWN", 1)[1].strip()
    conn = await asyncpg.connect(dsn)
    transaction = conn.transaction()
    await transaction.start()
    try:
        await conn.execute(f"CREATE SCHEMA {SCHEMA}")
        await conn.execute(f"SET LOCAL search_path TO {SCHEMA}")
        await conn.execute(up)
        await conn.execute("SAVEPOINT migration_checks")
        await migration_checks(conn)
        await conn.execute("ROLLBACK TO SAVEPOINT migration_checks")
        pool = OneConnection(conn)
        await store_checks(pool)
        await conn.execute(down)
        relations = await conn.fetchval("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = $1", SCHEMA)
        functions = await conn.fetchval("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = $1", SCHEMA)
        check(relations == 0 and functions == 0, "034 DOWN leaves no table, index or function behind")
        await conn.execute("SAVEPOINT unreadable")
        reason = await harness_gate.refusal(pool)
        await conn.execute("ROLLBACK TO SAVEPOINT unreadable")
        check(reason is not None and "could not be read" in reason, "with the tables gone the gate refuses instead of opening")
        await conn.execute(up)
        seed = await store.current(pool)
        check(seed["desired_state"] == "running" and seed["command_id"] is None, "034 UP again restores the running seed")
    finally:
        await transaction.rollback()
        remaining = await conn.fetchval("SELECT count(*) FROM pg_namespace WHERE nspname = $1", SCHEMA)
        await conn.close()
    check(remaining == 0, "after the rollback the throwaway schema is gone")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dsn", required=True, help="a throwaway database, e.g. postgresql://qa:qa@127.0.0.1:55434/qa")
    asyncio.run(accept(parser.parse_args().dsn))
    print("migration 034 and the agent harness control store: accepted, rolled back")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
