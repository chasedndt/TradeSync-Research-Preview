#!/usr/bin/env python
"""Isolated, rolled-back acceptance for the outcome metrics, the reconciliation views and the audit export.

One connection and one transaction on a throwaway PostgreSQL, rolled back at the end. The script
refuses the compose PostgreSQL port (5432) and a database named tradesync, and every HTTP request it
makes is in-process: the only client it can build carries an ASGI transport.

The database must have ops/sql/schema.sql and every migration applied (ops/apply_schema.py). The real
route modules run against the real tables, reading through heavy_query:

1. GET /state/reconciliation/views finds each seeded divergence, and nothing it should not;
2. GET /state/outcomes/regime-fit gives fit, misfit, undeclared and a rulebook not held, with the
   repository's own rulebook still hashing to its digest after a JSONB round trip;
3. GET /state/outcomes/thesis-adherence scores the worked example from JSONB as stored;
4. GET /state/audit/export and export.csv scrub secrets from real JSONB, carry the digests stored
   beside each row, keep one content digest across two readings, and report truncation;
5. no route wrote: this transaction's insert, update and delete counters are unchanged across every
   reading, and heavy_query's settings are in force in the server;
6. a newer rulebook changes no earlier verdict, a stored rulebook rewritten in place is refused, and
   the plan adherence is scored from cannot be rewritten at all.

    docker run --rm -d --name qa-evidence-metrics -e POSTGRES_USER=qa -e POSTGRES_PASSWORD=qa \
        -e POSTGRES_DB=tradesync_qa -p 127.0.0.1:55462:55462 postgres:16 -c port=55462
    POSTGRES_USER=qa POSTGRES_PASSWORD=qa POSTGRES_DB=tradesync_qa DB_HOST=127.0.0.1 DB_PORT=55462 \
        PYTHONIOENCODING=utf-8 python ops/apply_schema.py
    python tools/qa_outcome_metrics_sql.py --dsn postgresql://qa:qa@127.0.0.1:55462/tradesync_qa
    docker rm -f qa-evidence-metrics
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

import asyncpg  # noqa: E402
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app import audit_export_routes, heavy_query, outcome_metrics, reconciliation_routes  # noqa: E402
from tradesync_core import audit_export  # noqa: E402
from tradesync_core.regime_weights import config_digest  # noqa: E402

from qa_outcome_metrics_seed import LATER, SECRETS, insert_rulebook, seed  # noqa: E402

RealAsyncClient = httpx.AsyncClient


class LocalOnlyClient(RealAsyncClient):
    def __init__(self, *args, **kwargs):
        if not isinstance(kwargs.get("transport"), httpx.ASGITransport):
            raise RuntimeError("only in-process ASGI requests are allowed in this acceptance")
        super().__init__(*args, **kwargs)


httpx.AsyncClient = LocalOnlyClient

passed = 0


def check(condition: bool, message: str) -> None:
    global passed
    if not condition:
        raise AssertionError(f"QA FAIL: {message}")
    passed += 1
    print(f"ok   {message}")


class OneConnection:
    """A pool of one connection: every route's transaction becomes a savepoint in the acceptance transaction."""

    def __init__(self, conn) -> None:
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


async def writes(conn) -> int:
    return int(await conn.fetchval("SELECT coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) FROM pg_stat_xact_user_tables"))


async def views(client, ids) -> None:
    body = (await client.get("/state/reconciliation/views", params={"hours": 24})).json()
    by = {view["name"]: view for view in body["views"]}
    check(list(by) == ["orphaned_events", "duplicate_candidates", "stale_approvals", "partial_orders", "missing_outcomes"],
          "all five reconciliation views answered, in order")
    check(all(v["compared"] and v["window"] for v in body["views"]) and body["window"]["to"] == body["generated_at"],
          "every view states what it compared and its window, and the reading its exact instant")
    check([f["subject_id"] for f in by["orphaned_events"]["findings"]] == [str(ids["e2"])],
          "the event no signal referenced is an orphan; the referenced one is not")
    dup = by["duplicate_candidates"]["findings"]
    check([f["kind"] for f in dup] == ["duplicate_evidence_digest"]
          and sorted(dup[0]["observed"]["opportunity_ids"]) == sorted([str(ids["o1"]), str(ids["o2"])]),
          "two opportunities sharing one evidence digest are one certain duplicate")
    check([f["subject_id"] for f in by["stale_approvals"]["findings"]] == ["qa-env-stale"],
          "the approval unconsumed for 6h is stale; the 1h one is not")
    check(sorted(f["kind"] for f in by["partial_orders"]["findings"]) == ["order_not_terminal", "partial_fill"],
          "the placed order past its settle window, filled 60 of 100 USD, is both findings")
    found = sorted((f["subject_id"], f["kind"], f["observed"]["horizon_minutes"]) for f in by["missing_outcomes"]["findings"])
    check(found == sorted([(str(ids["o1"]), "outcome_still_pending", 60), (str(ids["o2"]), "missing_outcome", 15),
                           (str(ids["o2"]), "missing_outcome", 60), (str(ids["o3"]), "missing_outcome", 15)]),
          "closed horizons with no verdict and a verdict still pending are found; horizons not yet due are not")


async def fit(client, conn, ids, plain) -> None:
    stored = await conn.fetchval("SELECT config FROM regime_rulebooks WHERE config_digest = $1", plain)
    check(config_digest(json.loads(stored)) == plain,
          "the repository's own rulebook, read back from JSONB, still hashes to its stored digest")
    body = (await client.get("/state/outcomes/regime-fit", params={"hours": 24})).json()
    verdicts = {call["opportunity_id"]: call["verdict"] for call in body["calls"]}
    check(verdicts == {str(ids["o1"]): "fit", str(ids["o2"]): "misfit", str(ids["o3"]): "undeclared",
                       str(ids["o4"]): "no_rulebook"}, "regime fit: fit, misfit, undeclared and a rulebook not held")
    summary = body["summary"]
    check(summary["regime_fit_rate"] == 0.5 and summary["abstained_by_reason"] == {"undeclared": 1, "no_rulebook": 1},
          "the fit rate is 1 / (1 + 1), with both abstentions counted apart")


async def adherence(client, ids) -> None:
    body = (await client.get("/state/outcomes/thesis-adherence")).json()
    by = {position["position_id"]: position for position in body["positions"]}
    closed, still_open = by[str(ids["p1"])], by[str(ids["p2"])]
    check(closed["adherence"] == 0.6 and closed["departures"] == ["stop_respected", "time_respected"],
          "thesis adherence scores the worked example 3 of 5 from JSONB as stored")
    check(still_open["abstained"] == 4 and body["summary"]["mean_adherence"] == 0.8,
          "an open position abstains on its four exit checks and the mean is (0.6 + 1.0) / 2")


async def export(client, conn) -> None:
    first, second = (await client.get("/state/audit/export", params={"days": 7}),
                     await client.get("/state/audit/export", params={"days": 7}))
    body = first.json()
    check(all(secret not in first.text for secret in SECRETS), "no secret from real JSONB reached the JSON export")
    check(body["sections"]["orders"]["rows"][0]["response"]["signature"] == audit_export.REDACTED
          and body["sections"]["decisions"]["rows"][0]["requested"]["api_key"] == audit_export.REDACTED
          and body["redacted_fields"] == 2, "both secret-looking fields were replaced by the marker and counted")
    check(body["content_digest"] == second.json()["content_digest"], "the same rows give the same content digest twice")
    stored = {r["approval_id"]: [r["approval_digest"], r["candidate_hash"]]
              for r in await conn.fetch("SELECT approval_id, approval_digest, candidate_hash FROM control_envelopes")}
    exported = {r["approval_id"]: [r["approval_digest"], r["candidate_hash"]] for r in body["sections"]["approvals"]["rows"]}
    check(len(stored) == 2 and exported == stored, "each exported approval carries the digest and candidate hash stored beside it")
    evidence = {str(r["id"]): r["digest"] for r in await conn.fetch("SELECT id, links->>'evidence_digest' AS digest FROM opportunities")}
    rows = body["sections"]["outcomes"]["rows"]
    check(bool(rows) and all(row["evidence_digest"] == evidence[row["opportunity_id"]] for row in rows),
          "each exported outcome carries its opportunity's stored evidence digest")
    csv_response = await client.get("/state/audit/export.csv", params={"section": "orders", "days": 7})
    check(csv_response.headers["content-type"].startswith("text/csv") and all(s not in csv_response.text for s in SECRETS)
          and csv_response.text.splitlines()[0].split(",") == list(audit_export.SECTIONS["orders"]),
          "the CSV export is text/csv, carries no secret, and heads with the section's declared columns")
    check(csv_response.headers["X-Export-Row-Count"] == "1" and csv_response.headers["X-Export-Truncated"] == "false",
          "the CSV states its row count and that it was not truncated")
    capped = (await client.get("/state/audit/export", params={"days": 7, "rows": 1})).json()["sections"]["approvals"]
    check(capped["truncated"] is True and capped["row_count"] == 1 and capped["rows_available_in_window"] == 2,
          "a section past its cap says truncated, having read one row past the cap to know")


async def bounded(conn) -> None:
    workers, timeout = await conn.fetchval("SHOW max_parallel_workers_per_gather"), await conn.fetchval("SHOW statement_timeout")
    check(workers == "0" and timeout == "30s", f"heavy_query's settings are in force in the server: workers {workers}, timeout {timeout}")
    names = sorted(heavy_query.readings)
    check(len(names) == 13 and all(heavy_query.readings[name]["failures"] == 0 for name in names),
          f"all 13 named reads ran through heavy_query with no failure: {', '.join(names)}")


async def rewrites(client, conn, ids, expecting) -> None:
    await insert_rulebook(conn, LATER)
    verdicts = {c["opportunity_id"]: c["verdict"] for c in (await client.get("/state/outcomes/regime-fit")).json()["calls"]}
    check(verdicts[str(ids["o1"])] == "fit" and verdicts[str(ids["o2"])] == "misfit",
          "a newer rulebook expecting the opposite regimes changes neither earlier verdict")
    savepoint = conn.transaction()
    await savepoint.start()
    try:
        await conn.execute("UPDATE regime_rulebooks SET config = jsonb_set(config, '{regime_expectation,LONG}', "
                           "'[\"falling\"]') WHERE config_digest = $1", expecting)
        calls = (await client.get("/state/outcomes/regime-fit")).json()["calls"]
        verdicts = {c["opportunity_id"]: c["verdict"] for c in calls}
        check(verdicts[str(ids["o1"])] == verdicts[str(ids["o2"])] == "rulebook_altered",
              "a stored rulebook rewritten in place no longer hashes to its digest and is refused, not re-judged")
    finally:
        await savepoint.rollback()
    savepoint = conn.transaction()
    await savepoint.start()
    refused = None
    try:
        await conn.execute("UPDATE managed_paper_positions SET initial_plan = '{}'::jsonb WHERE id = $1", ids["p1"])
    except asyncpg.PostgresError as exc:
        refused = str(exc)
    finally:
        await savepoint.rollback()
    check(refused is not None and "immutable" in refused,
          "the plan adherence is scored from cannot be rewritten: the database's own trigger refuses it")


async def main(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    port, database = await conn.fetchval("select current_setting('port')"), await conn.fetchval("select current_database()")
    if port == "5432" or database == "tradesync":
        await conn.close()
        raise SystemExit(f"refusing: port {port} and database {database} look like the running stack")
    print(f"PostgreSQL {await conn.fetchval('show server_version')} on port {port}, database {database}")
    app, outer = FastAPI(), conn.transaction()
    state = SimpleNamespace(pool=OneConnection(conn))
    for module in (reconciliation_routes, audit_export_routes, outcome_metrics):
        module.register(app, state)
    await outer.start()
    try:
        ids, plain, expecting = await seed(conn)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa") as client:
            before = await writes(conn)
            await views(client, ids)
            await fit(client, conn, ids, plain)
            await adherence(client, ids)
            await export(client, conn)
            after = await writes(conn)
            check(after == before, f"no route wrote: this transaction's inserts, updates and deletes stayed at {before}")
            await bounded(conn)
            await rewrites(client, conn, ids, expecting)
    finally:
        await outer.rollback()
        await conn.close()
    print(f"\n{passed} checks passed. Rolled back; nothing kept.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rolled-back acceptance for outcome metrics, reconciliation and audit export")
    parser.add_argument("--dsn", required=True, help="a throwaway PostgreSQL; port 5432 and database tradesync are refused")
    asyncio.run(main(parser.parse_args().dsn))
