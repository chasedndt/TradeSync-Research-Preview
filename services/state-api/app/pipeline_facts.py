"""What the probes established, derived once and read by every node.

Moved out of ``assemble_pipeline_status`` unchanged. The node definitions used
to close over a dozen local flags; deriving them here once, into one frozen
record, is what lets each group of nodes live in its own module while reading
exactly the same values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.pipeline_contract import _is_recent


@dataclass(frozen=True)
class PipelineFacts:
    probes: Mapping[str, Mapping[str, Any]]
    readiness: dict[str, Any]
    catalog_feature_count: int
    market_health_ok: bool
    hyperliquid_enabled: bool
    data_flowing: bool
    market_live: bool
    observation_count: int
    market_latency: Any
    postgres_live: bool
    redis_live: bool
    scorer_live: bool
    fusion_live: bool
    latest_signal: str | None
    latest_opportunity: str | None
    regime_status: str
    scorer_status: str
    performance_status: str

    def probe_label(self, key: str) -> str:
        probe = self.probes.get(key, {})
        if probe.get("ok"):
            return "passed"
        if probe.get("configured") is False:
            return "not configured in this runtime"
        return "offline"


def derive_facts(
    *,
    probes: Mapping[str, Mapping[str, Any]],
    postgres: Mapping[str, Any],
    redis: Mapping[str, Any],
    catalog_feature_count: int,
) -> PipelineFacts:
    market_health = probes.get("market_health", {})
    market_status = probes.get("market_status", {})
    market_features = probes.get("market_features", {})
    providers = market_status.get("data", {}).get("providers", [])
    hyperliquid_enabled = any(
        provider.get("venue") == "hyperliquid" and provider.get("enabled")
        for provider in providers
    )
    market_ready = probes.get("market_ready", {})
    # A 503 from /readyz still returns a body, so the report is available even
    # when the probe itself is marked not ok.
    readiness = market_ready.get("data", {}) or {}
    data_flowing = bool(readiness.get("ready"))
    # "live" now requires fresh stored observations, not merely a reachable
    # process. Reporting a frozen poller as live is the exact failure of
    # 2026-09-07.
    market_live = bool(market_health.get("ok") and hyperliquid_enabled and data_flowing)
    observation_count = int(market_features.get("data", {}).get("count", 0) or 0)
    market_latency = market_status.get("latency_ms")

    postgres_live = bool(postgres.get("ok"))
    redis_live = bool(redis.get("ok"))
    scorer_live = bool(probes.get("core_scorer", {}).get("ok"))
    fusion_live = bool(probes.get("fusion_engine", {}).get("ok"))

    latest_signal = postgres.get("latest_signal_ts")
    latest_opportunity = postgres.get("latest_opportunity_ts")

    # A stored record only counts as evidence of a working stage while it is
    # recent. Without this the pipeline would keep reporting a stage as live on
    # the strength of a row written days ago.
    recent_signal = _is_recent(latest_signal)
    recent_opportunity = _is_recent(latest_opportunity)

    # The regime engine is only "live" once its evaluation actually reaches a
    # stored signal. Evaluating in isolation, with nothing consuming the
    # result, is genuinely partial rather than complete.
    regime_status = (
        "live"
        if market_live and observation_count and recent_signal
        else "partial"
        if market_live and observation_count
        else "offline"
    )
    scorer_status = "live" if scorer_live and fusion_live else (
        "partial" if scorer_live or fusion_live else "offline"
    )
    performance_status = (
        "live"
        if postgres_live and (recent_signal or recent_opportunity)
        else "partial"
        if postgres_live
        else "offline"
    )

    return PipelineFacts(
        probes=probes,
        readiness=readiness,
        catalog_feature_count=catalog_feature_count,
        market_health_ok=bool(market_health.get("ok")),
        hyperliquid_enabled=hyperliquid_enabled,
        data_flowing=data_flowing,
        market_live=market_live,
        observation_count=observation_count,
        market_latency=market_latency,
        postgres_live=postgres_live,
        redis_live=redis_live,
        scorer_live=scorer_live,
        fusion_live=fusion_live,
        latest_signal=latest_signal,
        latest_opportunity=latest_opportunity,
        regime_status=regime_status,
        scorer_status=scorer_status,
        performance_status=performance_status,
    )
