#!/usr/bin/env python
"""Isolated, rolled-back acceptance for the ChaseOS graph projection and its routes.

One connection and one transaction on a throwaway PostgreSQL, rolled back at the end. The script
refuses the compose PostgreSQL port (5432) and a database named tradesync. Every HTTP request is in
process: the only client it can build carries an ASGI transport. Snapshots are written to a
temporary directory standing in for the vault, and that directory is checked to be byte-for-byte
unchanged afterwards.

The database must have ops/sql/schema.sql and every migration applied (ops/apply_schema.py). The real
route module runs against the real tables:

1. before any ingest the connector reports itself configured but never ingested;
2. ingesting a snapshot projects its nodes and edges, and ingesting the same snapshot again
   duplicates nothing (the roadmap's replay-without-duplication gate);
3. a newer snapshot becomes the one in force, and the older one is kept, marked superseded;
4. node search and the neighbour walk read only the snapshot in force, and the walk terminates on
   a cycle, reports the hops it actually returned and says when a limit cut it short;
5. a projection that fails halfway leaves nothing behind and the snapshot in force untouched;
6. a snapshot claiming approval authority is refused by name, and nothing is projected;
7. re-ingesting the older snapshot makes it current again without losing either;
8. no file in the snapshot directory was written.

    docker run --rm -d --name qa-graph -e POSTGRES_USER=qa -e POSTGRES_PASSWORD=qa \
        -e POSTGRES_DB=tradesync_qa -p 127.0.0.1:55491:55491 postgres:16 -c port=55491
    POSTGRES_USER=qa POSTGRES_PASSWORD=qa POSTGRES_DB=tradesync_qa DB_HOST=127.0.0.1 DB_PORT=55491 \
        PYTHONIOENCODING=utf-8 python ops/apply_schema.py
    python tools/qa_graph_projection_sql.py --dsn postgresql://qa:qa@127.0.0.1:55491/tradesync_qa
    docker rm -f qa-graph
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

import asyncpg  # noqa: E402
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app import graph_projection, graph_routes  # noqa: E402
from tradesync_core.graph_snapshot import validate_snapshot  # noqa: E402

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
    """A pool of one connection: the projection's transaction becomes a savepoint in the acceptance transaction."""

    def __init__(self, conn) -> None:
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def node(i: int, **extra) -> dict:
    return {"node_id": f"n{i}", "label": f"QA node {i}", "node_type": "rule" if i % 2 else "note", "source_file": f"qa/f{i}.md",
            "confidence": "EXTRACTED", "source_line": str(10 + i), "domain": "trading", "project": None, **extra}


def edge(edge_id: str, source: int, target: int) -> dict:
    return {"edge_id": edge_id, "source_id": f"n{source}", "target_id": f"n{target}", "relation": "references", "confidence": "INFERRED"}


def snapshot(snapshot_id: str, created_at: str, nodes: list[dict], edges: list[dict]) -> dict:
    return {"snapshot_id": snapshot_id, "created_at": created_at, "vault_root": "/vault", "extraction_scope": ["07_LOGS"],
            "nodes": nodes, "edges": edges, "community_assignments": {nodes[0]["node_id"]: "1"},
            "build_info": {"qa": True}, "metadata": {}}


# The older snapshot: a chain. The newer one: a cycle n1 → n2 → n3 → n1, and n4 hanging off n3.
OLDER = snapshot("qa-snap-older", "2026-09-15T10:00:00+00:00", [node(1), node(2), node(3)],
                 [edge("e1", 1, 2), edge("e2", 2, 3), edge("e3", 1, 3)])
NEWER = snapshot("qa-snap-newer", "2026-09-16T10:00:00+00:00", [node(1), node(2), node(3), node(4)],
                 [edge("e1", 1, 2), edge("e2", 2, 3), edge("e3", 3, 1), edge("e4", 3, 4)])
CLAIMING = snapshot("qa-snap-claiming", "2026-09-16T11:00:00+00:00", [node(1, properties={"approved": True}), node(2)],
                    [edge("e1", 1, 2)])


async def counts(conn, snapshot_id: str) -> tuple[int, int, int]:
    return (
        await conn.fetchval("SELECT count(*) FROM graph_snapshots WHERE snapshot_id = $1", snapshot_id),
        await conn.fetchval("SELECT count(*) FROM graph_nodes WHERE snapshot_id = $1", snapshot_id),
        await conn.fetchval("SELECT count(*) FROM graph_edges WHERE snapshot_id = $1", snapshot_id),
    )


async def current_id(conn) -> list[str]:
    return [r["snapshot_id"] for r in await conn.fetch("SELECT snapshot_id FROM graph_snapshots WHERE superseded_at IS NULL")]


def digest_directory(directory: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir())}


async def acceptance(client, conn, directory: Path) -> None:
    status = (await client.get("/state/knowledge/graph/status")).json()
    check(status["status"] == "configured_but_never_ingested" and sorted(status["available_snapshots"]) == sorted(
        ["older.json", "newer.json", "claiming.json"]) and status["authority"] == "read_only_projection",
          "before any ingest the connector is configured, lists its snapshot files and has projected nothing")

    first = await client.post("/state/knowledge/graph/ingest", params={"filename": "older.json"})
    check(first.status_code == 200 and first.json()["snapshot_id"] == "qa-snap-older" and await counts(conn, "qa-snap-older") == (1, 3, 3),
          "ingesting the older snapshot projects its 3 nodes and 3 edges")
    again = await client.post("/state/knowledge/graph/ingest", params={"filename": "older.json"})
    check(again.status_code == 200 and await counts(conn, "qa-snap-older") == (1, 3, 3) and await current_id(conn) == ["qa-snap-older"],
          "ingesting the same snapshot again duplicates nothing: still 1 snapshot, 3 nodes, 3 edges, one in force")

    newer = await client.post("/state/knowledge/graph/ingest", params={"filename": "newer.json"})
    superseded = await conn.fetchval("SELECT superseded_at IS NOT NULL FROM graph_snapshots WHERE snapshot_id = 'qa-snap-older'")
    check(newer.status_code == 200 and await current_id(conn) == ["qa-snap-newer"] and superseded
          and await counts(conn, "qa-snap-older") == (1, 3, 3) and await counts(conn, "qa-snap-newer") == (1, 4, 4),
          "a newer snapshot is the one in force; the older one is kept whole and marked superseded")

    found = (await client.get("/state/knowledge/graph/nodes", params={"q": "qa node"})).json()
    rules = (await client.get("/state/knowledge/graph/nodes", params={"node_type": "rule"})).json()
    check(found["snapshot_id"] == "qa-snap-newer" and len(found["nodes"]) == 4
          and sorted(n["node_id"] for n in rules["nodes"]) == ["n1", "n3"],
          "node search reads only the snapshot in force, by label and by type")

    one = (await client.get("/state/knowledge/graph/neighbours/n1", params={"depth": 1})).json()
    check(sorted((n["node_id"], n["hops"]) for n in one["neighbours"]) == [("n1", 0), ("n2", 1), ("n3", 1)]
          and one["hops_returned"] == [0, 1] and one["reached_requested_depth"] and not one["truncated"],
          "one hop from n1 reaches n2 by its outgoing edge and n3 by the incoming one: the walk is undirected")
    two = (await client.get("/state/knowledge/graph/neighbours/n1", params={"depth": 4})).json()
    check(sorted((n["node_id"], n["hops"]) for n in two["neighbours"]) == [("n1", 0), ("n2", 1), ("n3", 1), ("n4", 2)],
          "the walk through the cycle n1 → n2 → n3 → n1 terminates, and each node is reported at its nearest hop")
    cut = (await client.get("/state/knowledge/graph/neighbours/n1", params={"depth": 2, "limit": 2})).json()
    check(cut["truncated"] and cut["hops_returned"] == [0, 1] and not cut["reached_requested_depth"],
          "a limit that cuts the walk short says so, and says the requested depth was not reached")
    missing = await client.get("/state/knowledge/graph/neighbours/n9")
    check(missing.status_code == 404 and "qa-snap-newer" in missing.json()["detail"],
          "a node that is not in the snapshot in force is a 404 naming that snapshot")

    broken = validate_snapshot(snapshot("qa-snap-broken", "2026-09-16T12:00:00+00:00", [node(1), node(2)], [edge("e1", 1, 2)]))
    broken["edges"] = [{**broken["edges"][0], "target_id": "n9"}]  # past the validator: only the database can stop it now
    savepoint = conn.transaction()
    await savepoint.start()
    failure = None
    try:
        await graph_projection.project_snapshot(conn, broken)
    except asyncpg.PostgresError as exc:
        failure = type(exc).__name__
    finally:
        await savepoint.rollback()
    check(failure == "ForeignKeyViolationError" and await counts(conn, "qa-snap-broken") == (0, 0, 0)
          and await current_id(conn) == ["qa-snap-newer"],
          "a projection that fails at its last edge leaves no row behind, and the snapshot in force is untouched")

    claiming = await client.post("/state/knowledge/graph/ingest", params={"filename": "claiming.json"})
    check(claiming.status_code == 422 and "approved" in claiming.json()["detail"]
          and await counts(conn, "qa-snap-claiming") == (0, 0, 0) and await current_id(conn) == ["qa-snap-newer"],
          "a snapshot claiming approval authority is refused by name, and nothing of it is projected")

    back = await client.post("/state/knowledge/graph/ingest", params={"filename": "older.json"})
    check(back.status_code == 200 and await current_id(conn) == ["qa-snap-older"]
          and await counts(conn, "qa-snap-older") == (1, 3, 3) and await counts(conn, "qa-snap-newer") == (1, 4, 4),
          "re-ingesting the older snapshot makes it current again, and neither snapshot loses a row")


async def main(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    port, database = await conn.fetchval("select current_setting('port')"), await conn.fetchval("select current_database()")
    if port == "5432" or database == "tradesync":
        await conn.close()
        raise SystemExit(f"refusing: port {port} and database {database} look like the running stack")
    print(f"PostgreSQL {await conn.fetchval('show server_version')} on port {port}, database {database}")
    with tempfile.TemporaryDirectory(prefix="qa-graph-vault-") as tmp:
        directory = Path(tmp)
        for name, document in (("older.json", OLDER), ("newer.json", NEWER), ("claiming.json", CLAIMING)):
            (directory / name).write_text(json.dumps(document), encoding="utf-8")
        before = digest_directory(directory)
        graph_projection.CHASEOS_GRAPH_DIR = str(directory)
        app, outer = FastAPI(), conn.transaction()
        graph_routes.register(app, SimpleNamespace(pool=OneConnection(conn)))
        await outer.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa") as client:
                await acceptance(client, conn, directory)
        finally:
            await outer.rollback()
            await conn.close()
        check(digest_directory(directory) == before, "no file in the snapshot directory was written: the vault is only read")
    print(f"\n{passed} checks passed. Rolled back; nothing kept.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rolled-back acceptance for the ChaseOS graph projection")
    parser.add_argument("--dsn", required=True, help="a throwaway PostgreSQL; port 5432 and database tradesync are refused")
    asyncio.run(main(parser.parse_args().dsn))
