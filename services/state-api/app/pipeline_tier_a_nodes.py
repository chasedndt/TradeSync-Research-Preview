"""The Tier A nodes: the standalone core that must work with every connector off.

Moved out of ``assemble_pipeline_status`` unchanged, reading the derived
``PipelineFacts`` instead of local variables. Order is part of the contract:
source, ingest, transport, persistence, intelligence, decision support, learning.
"""

from __future__ import annotations

from typing import Any

from app.pipeline_contract import _freshness_evidence, _node, _recovery
from app.pipeline_facts import PipelineFacts


def tier_a_nodes(f: PipelineFacts) -> list[dict[str, Any]]:
    return [
        _node(
            node_id="hyperliquid",
            label="Hyperliquid public market",
            owner="Hyperliquid",
            tier="A",
            stage="source",
            status="live" if f.market_live else "offline",
            required_for_tier_a=True,
            authority="authoritative_market",
            summary=(
                "Authoritative perpetual-market source is answering through the market adapter."
                if f.market_live
                else "No verified Hyperliquid provider response is reaching TradeSync."
            ),
            evidence=[
                f"Provider enabled: {str(f.hyperliquid_enabled).lower()}",
                f"Status probe: {f.market_latency:.0f} ms" if f.market_latency is not None else "Status probe unavailable",
            ],
            missing=(
                []
                if f.market_live
                else ["Fresh stored observations: " + f.readiness.get("reason", "unknown")]
                if f.market_health_ok and f.hyperliquid_enabled
                else ["Live provider response"]
            ),
            impact="Market observation stops when this source is unavailable.",
            recovery=_recovery(
                "restart",
                "Restart the market-data adapter, then inspect provider errors",
                "market-data",
                "docker compose ... up -d --build market-data",
            ),
        ),
        _node(
            node_id="market_data",
            label="Market normalization",
            owner="TradeSync",
            tier="A",
            stage="ingest",
            status="live" if f.market_live and f.observation_count else "partial" if f.market_live else "offline",
            required_for_tier_a=True,
            authority="authoritative_market_derived",
            summary=f"{f.observation_count}/{f.catalog_feature_count} catalog inputs are currently exposed for BTC-PERP.",
            evidence=[
                f"Current feature observations: {f.observation_count}",
                "Mark, funding, OI, volume, and L2 inputs retain explicit provenance",
                _freshness_evidence(f.readiness),
            ],
            missing=(
                # Direct CVD and the one-hour return were implemented on
                # 2026-09-07/08; only liquidation flow remains unavailable.
                ["Direct liquidation flow"]
                if f.data_flowing
                else [
                    "Direct liquidation flow",
                    f"Fresh stored observations: {f.readiness.get('reason', 'unknown')}",
                ]
            ),
            impact="Existing observations continue; missing inputs reduce regime coverage rather than becoming zeroes.",
            recovery=_recovery(
                "inspect",
                "Inspect unavailable feature reasons in Regime Lab",
                "market-data + Regime Lab",
            ),
        ),
        _node(
            node_id="redis",
            label="Redis transport",
            owner="TradeSync",
            tier="A",
            stage="transport",
            status="healthy" if f.redis_live else "offline",
            required_for_tier_a=True,
            authority="rebuildable_transport",
            summary="Live stream/cache transport is reachable." if f.redis_live else "Redis transport is unreachable.",
            evidence=[f"PING: {'passed' if f.redis_live else 'failed'}"],
            missing=[] if f.redis_live else ["Stream and feature-history transport"],
            impact="Durable reads remain possible, but real-time fan-out and rolling feature history stop.",
            recovery=_recovery(
                "restart",
                "Restart Redis, then replay from durable evidence where supported",
                "redis",
                "docker compose ... up -d redis",
            ),
        ),
        _node(
            node_id="postgres",
            label="PostgreSQL durable truth",
            owner="TradeSync",
            tier="A",
            stage="persistence",
            status="healthy" if f.postgres_live else "offline",
            required_for_tier_a=True,
            authority="durable_operational_truth",
            summary="Durable state and migrations are queryable." if f.postgres_live else "Durable TradeSync state is unavailable.",
            evidence=[
                f"Database probe: {'passed' if f.postgres_live else 'failed'}",
                f"Latest signal: {f.latest_signal or 'none'}",
                f"Latest opportunity: {f.latest_opportunity or 'none'}",
            ],
            missing=[] if f.postgres_live else ["Durable decisions, experiments, journal, and outcomes"],
            impact="Execution and durable decisions fail closed when PostgreSQL is unavailable.",
            recovery=_recovery(
                "restart",
                "Restart PostgreSQL and rerun schema-init",
                "postgres + schema-init",
                "docker compose ... up -d postgres schema-init",
            ),
        ),
        _node(
            node_id="regime_engine",
            label="Regime evidence engine",
            owner="TradeSync",
            tier="A",
            stage="intelligence",
            status=f.regime_status,
            required_for_tier_a=True,
            authority="deterministic_paper_shadow",
            summary=(
                "The versioned rulebook is evaluating live evidence and feeding stored paper signals."
                if f.regime_status == "live"
                else "The versioned rulebook is evaluating live evidence, but not every block has admitted inputs."
                if f.regime_status == "partial"
                else "The regime rulebook has no live market evidence."
            ),
            evidence=[
                f"Feature inputs visible: {f.observation_count}/{f.catalog_feature_count}",
                "Regime Lab owns normalization, quality, and contribution traces",
            ],
            missing=["Full block coverage", "Direct liquidation evidence", "Champion activation/replay gate"],
            impact="Paper risk remains capped and explanations identify missing blocks.",
            recovery=_recovery(
                "develop",
                "Complete liquidation provenance and fixed-window replay before activation",
                "regime engine",
            ),
        ),
        _node(
            node_id="scorer_fusion",
            label="Scorer + opportunity fusion",
            owner="TradeSync",
            tier="A",
            stage="decision_support",
            status=f.scorer_status,
            required_for_tier_a=True,
            authority="paper_opportunity",
            summary=(
                "Both scorer and fusion health probes passed."
                if f.scorer_status == "live"
                else "The bounded runtime is not currently producing a verified end-to-end paper opportunity stream."
            ),
            evidence=[
                f"core-scorer health: {f.probe_label('core_scorer')}",
                f"fusion-engine health: {f.probe_label('fusion_engine')}",
                f"Latest recorded signal: {f.latest_signal or 'none'}",
            ],
            missing=[
                f"{name} endpoint and service"
                if f.probes.get(key, {}).get("configured") is False
                else name
                for key, name, is_live in (
                    ("core_scorer", "core-scorer", f.scorer_live),
                    ("fusion_engine", "fusion-engine", f.fusion_live),
                )
                if not is_live
            ],
            impact="Market and Regime Lab continue, but ranked paper opportunities are not refreshed.",
            recovery=_recovery(
                "repair_then_restart",
                "Reconcile the legacy scorer inputs, then start scorer and fusion",
                "core-scorer + fusion-engine",
                "Set PIPELINE_CORE_SCORER_URL and PIPELINE_FUSION_ENGINE_URL, then docker compose ... up -d --build core-scorer fusion-engine state-api",
            ),
        ),
        _node(
            node_id="performance_journal",
            label="Performance + journal loop",
            owner="TradeSync",
            tier="A",
            stage="learning",
            status=f.performance_status,
            required_for_tier_a=True,
            authority="measured_outcomes",
            summary=(
                "Paper signals and opportunities are being recorded; outcome reconciliation is still outstanding."
                if f.performance_status == "live"
                else "The durable store exists, but the current lean runtime has no complete outcome producer."
                if f.postgres_live
                else "No durable outcome store is reachable."
            ),
            evidence=["PostgreSQL schema is the intended outcome authority", "No current closed-loop performance job is verified"],
            missing=["Fill/outcome reconciliation", "MFE/MAE and slippage jobs", "Regime-fit feedback receipts"],
            impact="Trade ideas cannot yet learn from complete paper outcomes automatically.",
            recovery=_recovery(
                "develop",
                "Implement deterministic paper outcome and performance jobs",
                "performance journal",
            ),
        ),
    ]
