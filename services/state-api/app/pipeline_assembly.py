"""Assembling the pipeline contract: nodes, the edges between them, and the summaries.

Moved out of ``app/integration_pipeline.py``. The probes' facts are derived once
(``pipeline_facts``), the optional connectors are judged on their own evidence
(``pipeline_connector_states``), and each group of nodes lives in its own module;
this file puts them together in the contract's fixed order and computes what
depends on all of them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.pipeline_connector_states import connector_states
from app.pipeline_contract import HEALTHY_STATES
from app.pipeline_facts import derive_facts
from app.pipeline_federated_nodes import federated_nodes
from app.pipeline_tier_a_nodes import tier_a_nodes


def assemble_pipeline_status(
    *,
    probes: Mapping[str, Mapping[str, Any]],
    postgres: Mapping[str, Any],
    redis: Mapping[str, Any],
    catalog_feature_count: int,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a stable UI contract from explicit probe/configuration results."""

    facts = derive_facts(
        probes=probes,
        postgres=postgres,
        redis=redis,
        catalog_feature_count=catalog_feature_count,
    )
    nodes = tier_a_nodes(facts) + federated_nodes(connector_states(probes))

    by_id = {node["id"]: node for node in nodes}

    def edge(source: str, target: str, label: str, *, optional: bool = False) -> dict[str, Any]:
        source_state = by_id[source]["status"]
        target_state = by_id[target]["status"]
        if target_state == "locked":
            status = "locked"
        elif source_state in HEALTHY_STATES and target_state in HEALTHY_STATES:
            status = "flowing"
        elif optional and source_state in {"offline", "contract_only", "planned"}:
            status = "not_connected"
        else:
            status = "partial"
        return {"from": source, "to": target, "label": label, "status": status}

    edges = [
        edge("hyperliquid", "market_data", "public market observations"),
        edge("market_data", "redis", "rolling feature history"),
        edge("market_data", "postgres", "durable evidence boundary"),
        edge("redis", "regime_engine", "cadence-governed windows"),
        edge("regime_engine", "scorer_fusion", "quality-weighted evidence"),
        edge("scorer_fusion", "performance_journal", "paper candidates and outcomes"),
        edge("tradingview_pine", "scorer_fusion", "Pine alert receipt", optional=True),
        edge("strike_zone", "scorer_fusion", "validated paper candidate", optional=True),
        edge("agent_harness", "scorer_fusion", "advisory explanation", optional=True),
        edge("chaseos", "agent_harness", "approved knowledge snapshot", optional=True),
        edge("chaseos", "execution", "single-use approval", optional=True),
        edge("scorer_fusion", "execution", "approved order intent", optional=True),
    ]

    required_nodes = [node for node in nodes if node["required_for_tier_a"]]
    ready_count = sum(node["status"] in HEALTHY_STATES for node in required_nodes)
    tier_a_status = "ready" if ready_count == len(required_nodes) else (
        "offline" if ready_count == 0 else "partial"
    )
    connected_optional = sum(
        node["status"] in HEALTHY_STATES
        for node in nodes
        if not node["required_for_tier_a"] and node["tier"] in {"B", "B/C"}
    )

    priority = {"offline": 0, "partial": 1, "contract_only": 2, "locked": 3, "planned": 4}
    recovery_queue = [
        {
            "node_id": node["id"],
            "label": node["label"],
            "status": node["status"],
            "required_for_tier_a": node["required_for_tier_a"],
            "missing": node["missing"],
            "impact": node["impact"],
            "recovery": node["recovery"],
        }
        for node in sorted(
            (node for node in nodes if node["status"] not in HEALTHY_STATES),
            key=lambda item: (
                0 if item["required_for_tier_a"] else 1,
                priority.get(item["status"], 9),
                item["label"],
            ),
        )
    ]

    return {
        "schema_version": "integration_pipeline_status_v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "mode": "paper",
        "execution_authority": False,
        "tier_a": {
            "status": tier_a_status,
            "ready_count": ready_count,
            "total_count": len(required_nodes),
            "principle": "Standalone core continues when optional connectors are unavailable.",
        },
        "federated": {
            "status": "connected" if connected_optional else "not_connected",
            "connected_count": connected_optional,
            "total_count": 4,
        },
        "nodes": nodes,
        "edges": edges,
        "recovery_queue": recovery_queue,
        "capability_gaps": [
            {
                "id": "direct_liquidations",
                "status": "unavailable",
                "blocking": "positioning coverage and liquidation-specific explanations",
                "next_action": "Implement a source-provenance adapter; do not substitute the OI proxy.",
            },
            {
                "id": "price_change_24h",
                "status": "implemented",
                "blocking": "nothing",
                "next_action": "Derived from the venue's own prevDayPx beside the mark in metaAndAssetCtxs; shown as unavailable when the venue omits it.",
            },
        ],
    }
