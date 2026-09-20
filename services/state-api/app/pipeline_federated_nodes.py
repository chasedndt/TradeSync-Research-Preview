"""The federated nodes: optional connectors, and execution, which stays locked.

Moved out of ``assemble_pipeline_status`` unchanged, reading ``ConnectorStates``
instead of local variables. None of these is required for Tier A; each one's
outage is stated as exactly what it blocks and nothing more.
"""

from __future__ import annotations

from typing import Any

from app.pipeline_connector_states import ConnectorStates
from app.pipeline_contract import _node, _recovery


def federated_nodes(c: ConnectorStates) -> list[dict[str, Any]]:
    optional_states = c.optional
    research = c.strikezone_research
    research_payload = dict(research.get("payload") or {})
    research_missing = list(research_payload.get("missing_source_classes") or [])
    validation_missing = list(research_payload.get("validation_missing") or [])
    strikezone_missing = research_missing + [
        item for item in validation_missing if item not in research_missing
    ]
    if not research.get("available"):
        strikezone_missing = (
            ["A Strike Zone alert in the last 24 h"]
            if optional_states["strike_zone"][0] == "partial"
            else ["A bridged research evidence receipt or configured TradingView alert ingress"]
        )

    nodes = [
        _node(
            node_id="tradingview_pine",
            label="TradingView + Pine Script",
            owner="TradingView / operator",
            tier="B",
            stage="advisory_ingress",
            status=c.tv_status,
            required_for_tier_a=False,
            authority="advisory_signal",
            summary=(
                "Pine alerts are arriving through the authenticated public route and landing in quarantine."
                if c.tv_status == "live"
                else "The receiver is configured; no alert has arrived in the last 24 hours."
                if c.tv_status == "partial"
                else "The webhook receiver refuses every alert until TRADINGVIEW_WEBHOOK_SECRET is set."
            ),
            evidence=c.tv_evidence,
            missing=[] if c.tv_status == "live" else ["A fresh alert receipt (last 24 h)"] if c.tv_configured else ["TRADINGVIEW_WEBHOOK_SECRET"],
            impact="Hyperliquid observation and deterministic regime evidence continue without Pine alerts.",
            recovery=_recovery(
                "configure",
                "Point a TradingView alert at the public webhook with the shared secret in its JSON body",
                "TradingView alert + Cloudflare tunnel",
            ),
        ),
        _node(
            node_id="strike_zone",
            label="Strike Zone Crypto",
            owner="Strike Zone Crypto",
            tier="B",
            stage="research_candidate",
            status=optional_states["strike_zone"][0],
            required_for_tier_a=False,
            authority="paper_candidate",
            summary=(
                "Pine alerts and browser-research evidence enrich TradeSync with "
                "read-only context. Neither can approve or execute a trade."
            ),
            evidence=optional_states["strike_zone"][1]
            + [
                # Corrected 2026-09-08: the repository holds Pine Script
                # indicators, not a service. There is nothing to probe.
                "Submission source, not a probeable service: Pine indicators "
                "reach TradeSync as TradingView alerts",
                "Quarantine intake is the declared boundary",
            ],
            missing=strikezone_missing,
            impact="Only optional Strike Zone context is degraded; Hyperliquid market truth and paper workflows continue.",
            recovery=_recovery(
                "refresh",
                "Bridge a fresh evidence receipt; keep unavailable sources explicit",
                "StrikeZone host bridge + TradingView quarantine",
            ),
        ),
        _node(
            node_id="agent_harness",
            label="Hermes gateway",
            owner="ChaseOS Hermes",
            tier="B",
            stage="advisory_analysis",
            status=optional_states["agent_harness"][0],
            required_for_tier_a=False,
            authority="advisory_only",
            summary=(
                "Hermes is the ChaseOS agent gateway: the fleet's scheduler, its Discord platform and its API server. "
                "TradeSync reads its job outputs, runs its TradeSync jobs from the Fleet page, and asks it to explain, "
                "compare, brief and read posts for claims. Inside TradeSync it cannot score, approve or execute."
            ),
            evidence=optional_states["agent_harness"][1]
            + [
                # The envelope, the probe and the receipt all exist now, so the
                # honest evidence line is what is enforced rather than what is
                # documented. The boundary was "documented as advisory" until
                # 2026-09-08; it is now refused in code and proven against a
                # live model that was prompted into claiming approval.
                "Boundary enforced in code: agent_response_v1 refuses score/direction/approval/order fields, nested or embedded in JSON content",
                "Every accepted answer is filed in quarantine; refused escalation attempts are filed too",
            ],
            missing=[]
            if optional_states["agent_harness"][0] == "live"
            else ["The Hermes gateway API server answering at AGENT_HARNESS_URL"],
            impact="Deterministic scoring and UI continue without model availability.",
            recovery=_recovery("restart", "Start the Hermes gateway (its API server platform); the connector probes /v1/models with the Bearer key", "Hermes gateway"),
        ),
        _node(
            node_id="chaseos",
            label="ChaseOS knowledge + Gate",
            owner="ChaseOS",
            tier="B/C",
            stage="knowledge_and_approval",
            status=optional_states["chaseos"][0],
            required_for_tier_a=False,
            authority="canonical_knowledge_and_approval",
            summary="ChaseOS remains the knowledge and approval authority, never a TradeSync startup dependency.",
            evidence=optional_states["chaseos"][1]
            + [
                "knowledge_sync_v1 contract exists",
                # Both halves landed 2026-09-08. The honest evidence line is
                # what is enforced, not what remains to be written.
                "Read-only GraphSnapshot adapter and PostgreSQL projection: no write path to the vault, mount is :ro",
                "Gate wired: an approval binds to one candidate and authorises one paper evaluation; single use enforced by a unique constraint",
            ],
            missing=[]
            if optional_states["chaseos"][0] == "live"
            else ["A graph snapshot in the canonical vault's 07_LOGS/Graph-Snapshots and CHASEOS_GRAPH_DIR set"],
            impact="Knowledge promotion and ChaseOS approvals are blocked; Tier A market work continues.",
            recovery=_recovery("configure", "Run the vault's runtime/graph/builder.py to write a fresh snapshot; the connector projects the newest file", "ChaseOS connector"),
        ),
        _node(
            node_id="execution",
            label="Wallet + Hyperliquid execution",
            owner="Isolated signer / Hyperliquid",
            tier="C",
            stage="execution",
            status="locked",
            required_for_tier_a=False,
            authority="approval_gated_execution",
            summary="Execution is deliberately unavailable in the current paper-only runtime.",
            evidence=["execution_authority=false", "exec-hl-svc is outside the bounded runtime"],
            missing=["Isolated wallet", "Single-use ChaseOS approval", "Final risk check", "Reconciliation"],
            impact="No order can be signed or sent; research and paper workflows remain available.",
            recovery=_recovery("approval_required", "Do not restart; complete the governed wallet phase first", "signer + Gate + executor"),
        ),
    ]
    if research.get("available"):
        nodes[1]["research_run"] = {
            **research_payload,
            "fresh": bool(research.get("fresh")),
            "age_seconds": research.get("age_seconds"),
            "source_updated_at": research.get("source_updated_at"),
            "snapshot_at": research.get("snapshot_at"),
        }
    return nodes
