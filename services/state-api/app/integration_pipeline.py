"""Inspectable runtime topology for TradeSync and its optional connectors.

The response deliberately separates live probes from repository contracts. A
component is never reported as connected merely because code or a document
exists for it.

This module is the stable import surface. The work lives beside it, one
responsibility per file:

- ``pipeline_contract``: node and recovery shapes, healthy states, freshness;
- ``pipeline_facts``: what the probes established, derived once;
- ``pipeline_connector_states``: optional connectors judged on their own evidence;
- ``pipeline_tier_a_nodes`` and ``pipeline_federated_nodes``: the node definitions;
- ``pipeline_assembly``: edges, summaries and the recovery queue;
- ``pipeline_probes``: the bounded runtime probes and ``collect_integration_pipeline``.
"""

from __future__ import annotations

from app.pipeline_assembly import assemble_pipeline_status
from app.pipeline_contract import (
    HEALTHY_STATES,
    RECORD_FRESHNESS_SECONDS,
    _freshness_evidence,
    _is_recent,
    _node,
    _recovery,
)
from app.pipeline_probes import (
    _harness_probe,
    _knowledge_probe,
    _probe_json,
    _probe_json_sync,
    _strikezone_research_probe,
    _tradingview_probe,
    collect_integration_pipeline,
)

__all__ = [
    "HEALTHY_STATES",
    "RECORD_FRESHNESS_SECONDS",
    "_freshness_evidence",
    "_harness_probe",
    "_is_recent",
    "_knowledge_probe",
    "_node",
    "_probe_json",
    "_probe_json_sync",
    "_strikezone_research_probe",
    "_recovery",
    "_tradingview_probe",
    "assemble_pipeline_status",
    "collect_integration_pipeline",
]
