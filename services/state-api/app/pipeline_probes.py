"""Probing the runtime: bounded HTTP checks, the database and Redis, and the optional connectors.

Moved out of ``app/integration_pipeline.py`` unchanged. Every probe failure is
surfaced as evidence, never as an endpoint failure, and probes run off the API
event loop so a busy worker cannot turn into a false outage.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.pipeline_assembly import assemble_pipeline_status


def _probe_json_sync(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.get(f"{base_url.rstrip('/')}{path}")
            response.raise_for_status()
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "data": response.json(),
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "reason": str(exc),
            "data": {},
        }


async def _probe_json(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    """Run a bounded probe outside the API event loop.

    Several legacy State API routes still perform comparatively slow work on
    the main worker. A probe must not become a false outage merely because that
    event loop is busy serving the Cockpit.
    """

    return await asyncio.to_thread(_probe_json_sync, base_url, path, timeout)


async def collect_integration_pipeline(
    *,
    pool: Any,
    redis_client: Any,
    market_data_url: str,
    catalog_feature_count: int,
) -> dict[str, Any]:
    """Probe only configured/live runtime surfaces and assemble the contract."""

    service_urls = {
        "market": market_data_url,
        "ingest_gateway": os.getenv(
            "INGEST_GATEWAY_URL", "http://ingest-gateway:8080"
        ).strip(),
        "core_scorer": os.getenv(
            "CORE_SCORER_URL", "http://core-scorer:8000"
        ).strip(),
        "fusion_engine": os.getenv(
            "FUSION_ENGINE_URL", "http://fusion-engine:8002"
        ).strip(),
    }
    optional_urls: dict[str, str] = {}

    probe_timeout = float(os.getenv("INTEGRATION_PROBE_TIMEOUT_SECONDS", "3.0"))
    service_probe_timeout = float(
        os.getenv("INTEGRATION_SERVICE_PROBE_TIMEOUT_SECONDS", "0.75")
    )
    market_tasks: dict[str, Any] = {
        "market_health": _probe_json(service_urls["market"], "/healthz", probe_timeout),
        # Readiness, not just liveness: a reachable service with frozen
        # pollers must not read as live.
        "market_ready": _probe_json(service_urls["market"], "/readyz", probe_timeout),
        "market_status": _probe_json(service_urls["market"], "/status", probe_timeout),
        "market_features": _probe_json(
            service_urls["market"],
            "/features/hyperliquid/BTC-PERP",
            probe_timeout,
        ),
    }
    market_keys = list(market_tasks)
    market_results = await asyncio.gather(*market_tasks.values())
    probes = dict(zip(market_keys, market_results))

    # Probe optional and currently unstarted services separately. Failed Docker
    # DNS lookups must not delay or invalidate the authoritative market probes.
    service_tasks: dict[str, Any] = {}
    for key in ("ingest_gateway", "core_scorer", "fusion_engine"):
        url = service_urls[key]
        if url:
            service_tasks[key] = _probe_json(url, "/healthz", service_probe_timeout)
        else:
            probes[key] = {
                "ok": False,
                "configured": False,
                "reason": "not configured in active runtime",
                "data": {},
            }
    for key, url in optional_urls.items():
        if url:
            service_tasks[key] = _probe_json(url, "/healthz", service_probe_timeout)

    if service_tasks:
        service_keys = list(service_tasks)
        service_results = await asyncio.gather(*service_tasks.values())
        probes.update(dict(zip(service_keys, service_results)))
        for key in service_keys:
            probes[key]["configured"] = True

    for key, url in optional_urls.items():
        if key not in probes:
            probes[key] = {"ok": False, "configured": False, "data": {}}
        else:
            probes[key]["configured"] = bool(url)

    # The three optional connectors, on their own evidence.
    connector_keys = ("agent_harness", "chaseos", "tradingview", "strikezone_research")
    connector_results = await asyncio.gather(
        _harness_probe(pool),
        _knowledge_probe(pool),
        _tradingview_probe(pool),
        _strikezone_research_probe(pool),
    )
    probes.update(dict(zip(connector_keys, connector_results)))

    postgres_result: dict[str, Any] = {"ok": False}
    if pool:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    select
                      (select max(created_at) from signals) as latest_signal_ts,
                      (select max(snapshot_ts) from opportunities) as latest_opportunity_ts
                    """
                )
            postgres_result = {
                "ok": True,
                "latest_signal_ts": row["latest_signal_ts"].isoformat()
                if row and row["latest_signal_ts"]
                else None,
                "latest_opportunity_ts": row["latest_opportunity_ts"].isoformat()
                if row and row["latest_opportunity_ts"]
                else None,
            }
        except Exception as exc:  # surfaced as evidence, never endpoint failure
            postgres_result = {"ok": False, "reason": str(exc)}

    redis_result: dict[str, Any] = {"ok": False}
    if redis_client:
        try:
            redis_result = {"ok": bool(await redis_client.ping())}
        except Exception as exc:  # surfaced as evidence, never endpoint failure
            redis_result = {"ok": False, "reason": str(exc)}

    return assemble_pipeline_status(
        probes=probes,
        postgres=postgres_result,
        redis=redis_result,
        catalog_feature_count=catalog_feature_count,
    )


async def _harness_probe(pool: Any = None) -> dict[str, Any]:
    """The Hermes link as the heartbeat last saw it; never a request of its own."""
    from app import hermes_link

    link = hermes_link.status_now()
    if link["status"] == "not_configured":
        return {"ok": False, "configured": False}
    return {
        "ok": link["status"] in ("live", "degraded"),
        "configured": True,
        "url": link["url"],
        "models": link["models"],
        "reason": link["last_error"] or "",
        "link": link,
        "gateway": await hermes_link.gateway_state(pool),
    }


async def _knowledge_probe(pool: Any) -> dict[str, Any]:
    """The projected canonical-vault snapshot, if the connector is configured."""
    from app import graph_projection

    if graph_projection.snapshot_directory() is None:
        return {"ok": False, "configured": False}
    if not pool:
        return {"ok": False, "configured": True, "reason": "database pool not ready"}
    try:
        async with pool.acquire() as conn:
            current = await graph_projection.current_snapshot(conn)
    except Exception as exc:  # evidence, never an endpoint failure
        return {"ok": False, "configured": True, "reason": f"{type(exc).__name__}: {exc}"}
    if not current:
        files = graph_projection.available_snapshots()
        return {"ok": False, "configured": True,
                "reason": f"{len(files)} snapshot file(s) present, none projected yet" if files else "no snapshot files in the directory"}
    return {
        "ok": True, "configured": True,
        "snapshot_id": current.get("snapshot_id"), "nodes": current.get("node_count"), "edges": current.get("edge_count"),
        "created_at": current.get("created_at"),
    }


async def _tradingview_probe(pool: Any) -> dict[str, Any]:
    """Pine alert receipts: the receiver's configuration and what has actually arrived."""
    configured = bool(os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip())
    out: dict[str, Any] = {"ok": False, "configured": configured, "public_url": os.getenv("TRADINGVIEW_PUBLIC_URL", "").strip() or None,
                           "accepted_total": 0, "accepted_24h": 0, "claims_total": 0}
    if not pool:
        return out
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT count(*) FILTER (WHERE accepted) AS total,
                       count(*) FILTER (WHERE accepted AND received_at > now() - interval '24 hours') AS recent,
                       max(received_at) FILTER (WHERE accepted) AS latest,
                       (SELECT payload->>'indicator' FROM quarantine_intake WHERE source = 'tradingview' AND accepted
                          ORDER BY received_at DESC LIMIT 1) AS latest_indicator,
                       (SELECT count(*) FROM evidence_claims WHERE source = 'tradingview') AS claims
                FROM quarantine_intake WHERE source = 'tradingview'
                """
            )
        out.update({
            "accepted_total": int(row["total"] or 0), "accepted_24h": int(row["recent"] or 0),
            "latest_at": row["latest"].isoformat() if row["latest"] else None,
            "latest_indicator": row["latest_indicator"], "claims_total": int(row["claims"] or 0),
        })
        out["ok"] = configured and out["accepted_24h"] > 0
    except Exception as exc:
        out["reason"] = f"{type(exc).__name__}: {exc}"
    return out


async def _strikezone_research_probe(pool: Any) -> dict[str, Any]:
    """Read the latest bridged evidence receipt without touching its artifacts."""

    if not pool:
        return {"ok": False, "configured": False, "available": False, "reason": "database pool not ready"}
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT payload, source_updated_at, snapshot_at "
                "FROM sz_documents WHERE kind = 'research_evidence'"
            )
    except Exception as exc:
        return {
            "ok": False,
            "configured": True,
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    if not row:
        return {
            "ok": False,
            "configured": True,
            "available": False,
            "reason": "no research evidence receipt has been bridged",
        }

    payload = row["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = None
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "configured": True,
            "available": False,
            "reason": "stored research evidence is malformed",
        }

    observed_at = row["source_updated_at"] or row["snapshot_at"]
    max_age = int(os.getenv("STRIKEZONE_RESEARCH_MAX_AGE_SECONDS", "86400"))
    age_seconds = None
    fresh = False
    if isinstance(observed_at, datetime):
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age_seconds = max(0, round((datetime.now(timezone.utc) - observed_at).total_seconds(), 1))
        fresh = age_seconds <= max_age

    validation_ok = bool(payload.get("validation_ok"))
    missing_sources = list(payload.get("missing_source_classes") or [])
    return {
        "ok": fresh and validation_ok and not missing_sources,
        "configured": True,
        "available": True,
        "fresh": fresh,
        "age_seconds": age_seconds,
        "source_updated_at": observed_at.isoformat() if isinstance(observed_at, datetime) else None,
        "snapshot_at": row["snapshot_at"].isoformat() if isinstance(row["snapshot_at"], datetime) else None,
        "payload": payload,
    }
