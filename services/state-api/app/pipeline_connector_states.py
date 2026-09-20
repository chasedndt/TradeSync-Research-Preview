"""The optional connectors' states, each judged on its own evidence.

Moved out of ``assemble_pipeline_status`` unchanged. Optional connectors are not
judged on a generic /healthz that some of them do not have: the Hermes API server
answers /health, the knowledge connector is a directory of snapshots, and Pine
alerts are receipts, not a service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ConnectorStates:
    tv_status: str
    tv_configured: bool
    tv_evidence: list[str]
    optional: dict[str, tuple[str, list[str]]]
    strikezone_research: dict[str, Any]


def connector_states(probes: Mapping[str, Mapping[str, Any]]) -> ConnectorStates:
    # Optional connectors are judged on their own evidence, not on a generic
    # /healthz that some of them do not have (the Hermes API server answers
    # /health; the knowledge connector is a directory of snapshots; Pine
    # alerts are receipts, not a service).
    optional_states: dict[str, tuple[str, list[str]]] = {}

    tv = probes.get("tradingview", {})
    tv_configured = bool(tv.get("configured"))
    tv_recent = tv.get("accepted_24h", 0) or 0
    if tv_configured and tv_recent:
        tv_status = "live"
    elif tv_configured and tv.get("accepted_total"):
        tv_status = "partial"
    elif tv_configured:
        tv_status = "partial"
    else:
        tv_status = "offline"
    tv_evidence = [
        "Receiver: secret " + ("configured" if tv_configured else "NOT configured (endpoint refuses every alert)"),
        f"Public route: {tv.get('public_url') or 'not declared'}",
        f"Accepted alerts: {tv.get('accepted_total', 0)} total, {tv_recent} in the last 24 h"
        + (f"; latest {tv.get('latest_at')} from {tv.get('latest_indicator')}" if tv.get("latest_at") else ""),
    ]
    research = dict(probes.get("strikezone_research", {}))
    research_payload = research.get("payload") or {}
    if research.get("available"):
        research_status = "live" if research.get("ok") else "partial"
        research_lines = [
            f"Latest browser-research run: {research_payload.get('run_slug') or 'unnamed'} · "
            f"{research_payload.get('evidence_item_count', 0)} evidence items · "
            f"{research_payload.get('charts_captured', 0)}/{research_payload.get('charts_expected', 0)} charts",
            f"Evidence status: {research_payload.get('status') or 'unknown'} · "
            f"strict validation {'passed' if research_payload.get('validation_ok') else 'blocked'} · "
            f"receipt age {research.get('age_seconds')}s",
        ]
        missing_sources = research_payload.get("missing_source_classes") or []
        if missing_sources:
            research_lines.append("Unavailable source classes: " + ", ".join(missing_sources))
        validation_missing = research_payload.get("validation_missing") or []
        if validation_missing:
            research_lines.append("Validation blockers: " + ", ".join(validation_missing))
    else:
        research_status = "contract_only"
        research_lines = [research.get("reason") or "No browser-research receipt has been bridged"]

    legacy_status = "live" if tv_status == "live" else "partial" if tv.get("accepted_total") else "contract_only"
    optional_states["strike_zone"] = (
        research_status if research.get("available") else legacy_status,
        [f"Strike Zone indicators arrive as TradingView alerts: {tv.get('accepted_total', 0)} received, "
         f"{tv.get('claims_total', 0)} became measured claims"] + research_lines,
    )

    h = probes.get("agent_harness", {})
    link = h.get("link") or {}
    gateway = ((h.get("gateway") or {}).get("payload") or {})
    platforms = gateway.get("platforms") or {}
    link_lines = []
    if link:
        link_lines.append(
            f"Gateway {link.get('host')}:{link.get('port')} · {link.get('platform') or 'hermes'} {link.get('version') or ''} · "
            f"last answer {link.get('seconds_since_seen')}s ago in {link.get('latency_ms')} ms · heartbeat every {int(link.get('heartbeat_s') or 0)}s"
        )
        if link.get("availability_recent") is not None:
            link_lines.append(f"Recent availability {round(link['availability_recent'] * 100)}% of heartbeats; models {', '.join(link.get('models') or []) or 'not yet listed'}")
    if platforms:
        link_lines.append("Gateway platforms: " + ", ".join(f"{k} {v.get('state')}" for k, v in platforms.items() if isinstance(v, dict)))
    if h.get("configured") and h.get("ok"):
        state_ = "live" if link.get("status") == "live" else "partial"
        optional_states["agent_harness"] = (state_, link_lines or ["Hermes gateway answering"])
    elif h.get("configured"):
        optional_states["agent_harness"] = ("offline", [f"Hermes gateway not answering: {h.get('reason') or 'no heartbeat yet'}"] + link_lines)
    else:
        optional_states["agent_harness"] = ("contract_only", ["AGENT_HARNESS_URL is unset"])

    g = probes.get("chaseos", {})
    if g.get("configured") and g.get("ok"):
        optional_states["chaseos"] = (
            "live",
            [f"Canonical vault snapshot projected: {g.get('snapshot_id')} ({g.get('nodes')} nodes, {g.get('edges')} edges, built {g.get('created_at')})"],
        )
    elif g.get("configured"):
        optional_states["chaseos"] = ("offline", [f"Snapshot directory configured but nothing projected: {g.get('reason', 'no snapshot')}"])
    else:
        optional_states["chaseos"] = ("contract_only", ["CHASEOS_GRAPH_DIR is unset"])

    return ConnectorStates(
        tv_status=tv_status,
        tv_configured=tv_configured,
        tv_evidence=tv_evidence,
        optional=optional_states,
        strikezone_research=research,
    )
