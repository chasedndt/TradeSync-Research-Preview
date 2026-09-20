"""The paper sections of the audit export: rehearsals, managed paper positions and their lifecycle events.

Paper mode records no decision and no order by design: while the execution gate is shut the risk check refuses
every preview before a decision is stored, and no order is written. The paper activity that does happen lives in
two other records, and without them an export of the paper default is empty by construction:

- ``paper_rehearsals``: each rehearsal's plan, risk verdict and priced fill, with the evidence digest stored on
  the opportunity it rehearsed;
- ``paper_positions``: each managed paper position's entry, levels, exit and costs as its lifecycle state
  holds them, with the entry evidence SHA-256 stored beside it and how many lifecycle events it has;
- ``paper_position_events``: its lifecycle transitions (opened, closed, funding settled), each with the
  SHA-256 of its stored payload.

The observation ticks between transitions (an ``observed`` event every fifteen seconds while a position is
open) are counted on each position, not listed: a day of one position is 5,760 of them, and a bounded
export would otherwise hold minutes of ticks and none of the transitions. A position's reconstruction reads
them all.

``payload_sha256`` is computed when the export is taken, over the canonical JSON of the payload as stored
(``audit_export.digest_of``), so an exported event can be checked against its database row without the
export shipping every book. Rows here are shaped from the stored documents and nothing is recalculated.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

PAPER_SECTIONS: dict[str, tuple[str, ...]] = {
    "paper_rehearsals": ("id", "created_at", "opportunity_id", "symbol", "direction", "size_usd", "status", "plan",
                         "risk_verdict", "fill", "market", "evidence_digest"),
    "paper_positions": ("id", "opportunity_id", "symbol", "created_at", "updated_at", "status", "side", "style",
                        "lifecycle_version", "entry_time", "entry_price", "quantity", "notional_usdc", "stop", "target",
                        "expiry", "exit_time", "exit_reason", "exit_price", "gross_pnl_usdc", "fees_usdc",
                        "funding_usdc", "net_usdc", "funding_status", "observations", "observation_gap", "events",
                        "observation_events", "first_event_at", "last_event_at", "evidence_sha256", "evidence_digest"),
    "paper_position_events": ("id", "position_id", "symbol", "created_at", "kind", "status", "evaluated_through",
                              "fill_price", "fill_quantity", "fill_cost_usdc", "fee_usdc", "exit_reason",
                              "funding_usdc", "funding_rows_added", "net_usdc", "kill_switch", "payload_sha256"),
}

# Stored beside the row it fingerprints, so it can be checked against the artefact it describes.
PAPER_STORED_DIGESTS = ("evidence_sha256",)
# Computed when the export is taken, over a payload as stored.
COMPUTED_DIGEST_COLUMNS = ("payload_sha256",)

SECTION_NOTES = {
    "paper_rehearsals": "A rehearsal prices a paper fill from the mark and spread it read; no order was placed.",
    "paper_positions": ("Figures as the position's lifecycle state holds them. For an open position the net is its "
                        "estimate if closed at the latest observed book. Observation ticks are counted in "
                        "observation_events, not listed."),
    "paper_position_events": ("Lifecycle transitions only: opened, closed and funding settled. payload_sha256 is the "
                              "SHA-256 of the stored payload's canonical JSON, computed when the export was taken."),
}


def decode(value: Any) -> Any:
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def position_row(stored: Mapping[str, Any]) -> dict[str, Any]:
    """One managed paper position as the export lists it, from its stored row and lifecycle state."""
    state = _mapping(decode(stored.get("position_state")))
    closed = state.get("status") == "closed"
    return {
        "id": stored.get("id"), "opportunity_id": stored.get("opportunity_id"), "symbol": stored.get("symbol"),
        "created_at": stored.get("created_at"), "updated_at": stored.get("updated_at"),
        "status": state.get("status"), "side": state.get("side"), "style": state.get("style"),
        "lifecycle_version": state.get("version"), "entry_time": state.get("entry_time"),
        "entry_price": state.get("entry_price"), "quantity": state.get("quantity"), "notional_usdc": state.get("notional"),
        "stop": state.get("stop"), "target": state.get("target"), "expiry": state.get("expiry"),
        "exit_time": state.get("exit_time") if closed else None, "exit_reason": state.get("exit_reason") if closed else None,
        "exit_price": state.get("exit_price") if closed else None, "gross_pnl_usdc": state.get("gross_pnl_usdc"),
        "fees_usdc": state.get("fees_usdc"), "funding_usdc": state.get("funding_usdc"),
        "net_usdc": state.get("net_estimate_usdc"), "funding_status": _mapping(state.get("funding")).get("status"),
        "observations": state.get("observations"), "observation_gap": state.get("observation_gap"),
        "events": stored.get("events"), "observation_events": stored.get("observation_events"),
        "first_event_at": stored.get("first_event_at"), "last_event_at": stored.get("last_event_at"),
        "evidence_sha256": stored.get("evidence_sha256"), "evidence_digest": stored.get("evidence_digest"),
    }


def _fill(kind: str, state: Mapping[str, Any]) -> dict[str, Any]:
    """The fill a transition recorded: the entry for ``opened``, the whole exit for ``closed``, none otherwise."""
    fees, slippage = _mapping(state.get("fees")), _mapping(state.get("slippage"))
    if kind == "opened":
        return {"fill_price": state.get("entry_price"), "fill_quantity": state.get("quantity"),
                "fill_cost_usdc": _mapping(slippage.get("entry")).get("cost_usdc"), "fee_usdc": fees.get("entry_usdc")}
    if kind == "closed" and state.get("status") == "closed":
        exit_fill = _mapping(slippage.get("exit"))
        return {"fill_price": state.get("exit_price"), "fill_quantity": exit_fill.get("quantity", state.get("quantity")),
                "fill_cost_usdc": exit_fill.get("cost_usdc"), "fee_usdc": fees.get("exit_usdc")}
    return {"fill_price": None, "fill_quantity": None, "fill_cost_usdc": None, "fee_usdc": None}


def event_row(stored: Mapping[str, Any]) -> dict[str, Any]:
    """One lifecycle transition as the export lists it, with the SHA-256 of its stored payload."""
    from .audit_export import digest_of  # the export's one canonical form; imported here because it imports this module

    payload = decode(stored.get("payload"))
    kind = str(stored.get("kind"))
    body = _mapping(payload)
    state = body if kind == "opened" else _mapping(body.get("position"))
    closed = state.get("status") == "closed"
    return {
        "id": stored.get("id"), "position_id": stored.get("position_id"), "symbol": stored.get("symbol"),
        "created_at": stored.get("created_at"), "kind": kind, "status": state.get("status"),
        "evaluated_through": state.get("evaluated_through"), **_fill(kind, state),
        "exit_reason": state.get("exit_reason") if closed else None, "funding_usdc": state.get("funding_usdc"),
        "funding_rows_added": None if kind == "opened" else body.get("funding_rows_added"),
        "net_usdc": state.get("net_estimate_usdc"), "kill_switch": body.get("kill_switch"),
        "payload_sha256": digest_of(payload),
    }
