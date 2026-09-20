"""A snapshot counted and digested: what an operator checks before trusting a projection.

Moved out of ``graph_snapshot.py`` unchanged. The digest deliberately ignores
the fields ChaseOS changes on every extraction run, so two snapshots of the same
corpus digest the same whichever run produced them. ``graph_snapshot``
re-exports both functions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def snapshot_digest(document: Mapping[str, Any]) -> str:
    """A content digest over the parts that decide what gets projected.

    Deliberately excludes ``snapshot_id``, ``build_info`` and ``metadata``.
    ChaseOS mints a fresh ``snapshot_id`` for every extraction run and records
    timings and free-form notes alongside it, so including any of them would
    make the digest move on every rebuild of an unchanged corpus — which is
    precisely the question the digest exists to answer.

    Two snapshots with the same digest describe the same graph, whatever run
    produced them.
    """
    payload = {
        "vault_root": document.get("vault_root"),
        "extraction_scope": sorted(document.get("extraction_scope") or []),
        "nodes": sorted(
            (str(n.get("node_id")) for n in document.get("nodes") or [] if isinstance(n, Mapping))
        ),
        "edges": sorted(
            (str(e.get("edge_id")) for e in document.get("edges") or [] if isinstance(e, Mapping))
        ),
        "community_assignments": dict(
            sorted((document.get("community_assignments") or {}).items())
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def summarise(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Counts the operator needs to see before trusting a projection."""
    nodes = snapshot.get("nodes") or []
    edges = snapshot.get("edges") or []

    by_type: dict[str, int] = {}
    by_confidence: dict[str, int] = {}
    for node in nodes:
        by_type[node["node_type"]] = by_type.get(node["node_type"], 0) + 1
        by_confidence[node["confidence"]] = by_confidence.get(node["confidence"], 0) + 1

    by_relation: dict[str, int] = {}
    for edge in edges:
        by_relation[edge["relation"]] = by_relation.get(edge["relation"], 0) + 1

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_type": dict(sorted(by_type.items())),
        "nodes_by_confidence": dict(sorted(by_confidence.items())),
        "edges_by_relation": dict(sorted(by_relation.items())),
        # Stated so a reader of the projection cannot mistake it for canonical.
        "authority": "read_only_projection",
    }
