"""The ChaseOS knowledge-graph projection: status, ingest, nodes and neighbours.

Moved out of ``app/main.py`` unchanged. ChaseOS is canonical; everything here is
a local projection of a snapshot artifact, rebuildable from it, and it confers no
scoring, approval or execution authority. An unset connector is a normal state,
reported as ``not_configured`` rather than as a fault the operator cannot act on.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.graph_projection import (
    available_snapshots,
    current_snapshot,
    neighbours,
    project_snapshot,
    read_snapshot,
    snapshot_directory,
)
from app.json_util import as_json
from tradesync_core.graph_snapshot import SnapshotRejected

logger = logging.getLogger("state-api")
router = APIRouter()


def register(app, state) -> None:
    """Attach the knowledge-graph projection routes."""

    @router.get("/state/knowledge/graph/status")
    async def get_graph_status():
        """Whether the ChaseOS graph projection is configured, and what is in force.

        An unset connector is a normal state, not a fault: TradeSync must remain
        fully usable with every optional connector disabled. The answer says
        "not_configured" rather than reporting an error the operator cannot act on.
        """
        directory = snapshot_directory()
        files = available_snapshots()

        projected = None
        if state.pool is not None:
            async with state.pool.acquire() as conn:
                projected = await current_snapshot(conn)
        if projected:
            projected = {
                **projected,
                "created_at": projected["created_at"].isoformat(),
                "ingested_at": projected["ingested_at"].isoformat(),
                "extraction_scope": as_json(projected.get("extraction_scope")),
                "build_info": as_json(projected.get("build_info")),
            }

        return {
            "configured": directory is not None,
            "snapshot_dir": str(directory) if directory else None,
            "available_snapshots": [p.name for p in files],
            "projected": projected,
            "status": (
                "not_configured"
                if directory is None
                else "projected"
                if projected
                else "configured_but_never_ingested"
            ),
            # Restated on every response. A projection of canonical knowledge is
            # still not canonical, and it grants nothing.
            "authority": "read_only_projection",
            "note": (
                "ChaseOS is canonical. This is a local projection of a snapshot "
                "artifact, rebuildable from it, and it confers no scoring, "
                "approval or execution authority."
            ),
        }

    @router.post("/state/knowledge/graph/ingest")
    async def ingest_graph_snapshot(filename: Optional[str] = None):
        """Project a snapshot from the configured directory into local adjacency.

        Reads the named file, or the newest when none is named. The vault is opened
        read-only; nothing is written back to ChaseOS, which is the exit-gate
        requirement for this phase.

        A snapshot that claims scoring, approval or execution authority is refused
        by name rather than cleaned up and accepted.
        """
        if state.pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        directory = snapshot_directory()
        if directory is None:
            raise HTTPException(
                status_code=503,
                detail="CHASEOS_GRAPH_DIR is unset; the knowledge connector is offline",
            )

        files = available_snapshots()
        if not files:
            raise HTTPException(
                status_code=404,
                detail=f"no snapshot files in {directory}",
            )

        if filename:
            chosen = next((p for p in files if p.name == filename), None)
            if chosen is None:
                raise HTTPException(status_code=404, detail=f"no snapshot named {filename}")
        else:
            chosen = files[0]

        try:
            snapshot = read_snapshot(chosen)
        except SnapshotRejected as exc:
            # 422, not 500: the file was read fine and is not acceptable. The
            # reason is returned so the operator can take it back to ChaseOS.
            raise HTTPException(status_code=422, detail=str(exc))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"unreadable snapshot: {exc}")

        async with state.pool.acquire() as conn:
            result = await project_snapshot(conn, snapshot)

        logger.info(
            f"Projected ChaseOS snapshot {result['snapshot_id']} "
            f"({result['nodes']} nodes, {result['edges']} edges)",
            extra={"trace_id": "knowledge"},
        )
        return {"source_file": chosen.name, **result}

    @router.get("/state/knowledge/graph/nodes")
    async def get_graph_nodes(
        q: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = Query(50, ge=1, le=500),
    ):
        """Search the projected nodes by label substring and type."""
        if state.pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with state.pool.acquire() as conn:
            projected = await current_snapshot(conn)
            if not projected:
                return {"snapshot_id": None, "nodes": [], "status": "no_projection"}

            clauses = ["snapshot_id = $1"]
            args: list = [projected["snapshot_id"]]
            if q:
                args.append(f"%{q.lower()}%")
                clauses.append(f"lower(label) LIKE ${len(args)}")
            if node_type:
                args.append(node_type)
                clauses.append(f"node_type = ${len(args)}")
            args.append(limit)

            rows = await conn.fetch(
                f"""
                SELECT node_id, label, node_type, source_file, source_line,
                       domain, project, confidence, provenance, community_id
                FROM graph_nodes
                WHERE {' AND '.join(clauses)}
                ORDER BY label
                LIMIT ${len(args)}
                """,
                *args,
            )

        return {
            "snapshot_id": projected["snapshot_id"],
            "nodes": [dict(row) for row in rows],
            "authority": "read_only_projection",
        }

    @router.get("/state/knowledge/graph/neighbours/{node_id}")
    async def get_graph_neighbours(
        node_id: str,
        depth: int = Query(2, ge=1, le=4),
        limit: int = Query(100, ge=1, le=500),
    ):
        """Nodes within ``depth`` hops of ``node_id``, in either direction.

        Undirected, because lineage and evidence-path questions do not care which
        way the extractor oriented an edge. Depth is capped: an unbounded walk over
        a 27k-note graph is not a query, it is a table scan with extra steps.
        """
        if state.pool is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        async with state.pool.acquire() as conn:
            projected = await current_snapshot(conn)
            if not projected:
                raise HTTPException(status_code=404, detail="no graph projection in force")
            found = await conn.fetchval(
                "SELECT 1 FROM graph_nodes WHERE snapshot_id = $1 AND node_id = $2",
                projected["snapshot_id"],
                node_id,
            )
            if not found:
                raise HTTPException(
                    status_code=404,
                    detail=f"node {node_id} is not in snapshot {projected['snapshot_id']}",
                )
            found_nodes = await neighbours(
                conn, projected["snapshot_id"], node_id, depth, limit
            )

        # Which hops are actually represented, not just which were asked for.
        # Results are ordered nearest-first, so a hub node with 1,500 immediate
        # neighbours fills the whole limit at one hop and a depth=3 request returns
        # nothing from hops 2 or 3. "truncated" says something was cut; this says
        # what you are actually looking at.
        hops_returned = sorted({int(n["hops"]) for n in found_nodes})
        truncated = len(found_nodes) >= limit

        return {
            "snapshot_id": projected["snapshot_id"],
            "node_id": node_id,
            "depth": depth,
            "neighbours": found_nodes,
            "truncated": truncated,
            "hops_returned": hops_returned,
            "reached_requested_depth": (not truncated) or (depth in hops_returned),
            "authority": "read_only_projection",
        }

    app.include_router(router)
