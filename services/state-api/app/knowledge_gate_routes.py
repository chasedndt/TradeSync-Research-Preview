"""The ChaseOS Gate: what an approval may authorise, and binding one approval to one paper candidate.

Moved out of ``app/main.py`` unchanged.
"""

import json

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.execution_flags import execution_gate_enabled, paper_mode_enabled
from tradesync_core.control_envelope import (
    CLOSED_AUTHORITY,
    ControlEnvelopeError,
    build_paper_control_envelope,
)
from tradesync_core.timeparse import parse_utc

router = APIRouter()


class GateApproval(BaseModel):
    """One authenticated ChaseOS decision, presented by the operator."""

    quarantine_id: str
    approval_id: str
    approval_digest: str
    approval_decision_id: str
    approved_at_utc: str
    validity_hours: int = 4


def register(app, state, *, extract_trade_candidate) -> None:
    """Attach the Gate status and paper-evaluation approval routes."""

    @router.get("/state/knowledge/gate/status", tags=["knowledge"])
    async def get_gate_status():
        """What the ChaseOS Gate can and cannot authorise.

        The Gate is an approval mechanism, not a knowledge one. It is deliberately
        narrow: an approval binds to exactly one candidate and authorises exactly
        one paper evaluation. There is no approval this system will accept that
        authorises an order, a wallet, a credential, a signature, or a live
        dispatch, and the ceiling below is the one actually enforced rather than a
        description of it.
        """
        unconsumed = consumed = 0
        if state.pool:
            async with state.pool.acquire() as conn:
                unconsumed = await conn.fetchval(
                    "SELECT count(*) FROM control_envelopes WHERE consumed_at IS NULL"
                )
                consumed = await conn.fetchval(
                    "SELECT count(*) FROM control_envelopes WHERE consumed_at IS NOT NULL"
                )

        return {
            "control_plane": "chaseos",
            "mode": "paper_only",
            # Verbatim from the library, not restated here. A copy would drift.
            "authority_ceiling": CLOSED_AUTHORITY,
            "scope": "once",
            "envelopes": {"unconsumed": unconsumed, "consumed": consumed},
            "execution_gate_open": execution_gate_enabled(),
            "paper_mode": paper_mode_enabled(),
            "note": (
                "An approval authorises one paper evaluation of one candidate. "
                "Single use is enforced by a unique constraint on approval_id, not "
                "by convention. TradeSync remains usable when the Gate is offline; "
                "what stops is approval, not observation."
            ),
        }

    @router.post("/state/knowledge/gate/authorize-paper-evaluation", tags=["knowledge"])
    async def authorize_paper_evaluation(approval: GateApproval):
        """Bind a ChaseOS approval to one extracted candidate. Fails closed.

        The candidate is re-extracted from its quarantined receipt rather than
        accepted from the caller, so an approval cannot be attached to a candidate
        that was edited after the operator looked at it. The envelope carries a hash
        of exactly what was approved.

        Replaying an approval is refused by a unique constraint, not by a check that
        could race. Single use is a fact about history, so it is enforced where
        history lives.
        """
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        # Re-extract rather than trust: the caller supplies an approval, never a
        # candidate.
        extracted = await extract_trade_candidate(
            approval.quarantine_id, validity_hours=approval.validity_hours
        )
        candidate = extracted["candidate"]

        try:
            envelope = build_paper_control_envelope(
                candidate,
                approval_id=approval.approval_id,
                approval_digest=approval.approval_digest,
                approval_decision_id=approval.approval_decision_id,
                approved_at_utc=approval.approved_at_utc,
            )
        except ControlEnvelopeError as exc:
            raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}")

        try:
            async with state.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO control_envelopes (
                        envelope_id, approval_id, approval_decision_id, approval_digest,
                        approved_at, candidate_id, candidate_hash, candidate,
                        authority, source_quarantine_id
                    ) VALUES ($1,$2,$3,$4,$5::timestamptz,$6,$7,$8::jsonb,$9::jsonb,$10::uuid)
                    """,
                    envelope["envelope_id"],
                    envelope["approval"]["approval_id"],
                    envelope["approval"]["approval_decision_id"],
                    envelope["approval"]["approval_digest"],
                    parse_utc(envelope["approval"]["approved_at_utc"], "approved_at_utc"),
                    candidate["candidate_id"],
                    envelope["candidate_hash"],
                    json.dumps(candidate),
                    json.dumps(envelope["authority"]),
                    approval.quarantine_id,
                )
        except asyncpg.UniqueViolationError:
            # Scope is "once". A replay is refused rather than authorising a second
            # evaluation on the same decision.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"approval {approval.approval_id} has already been bound; its "
                    "scope is 'once' and it cannot authorise a second evaluation"
                ),
            )

        return {
            "envelope_id": envelope["envelope_id"],
            "candidate_id": candidate["candidate_id"],
            "candidate_hash": envelope["candidate_hash"],
            "authority": envelope["authority"],
            "authorizes": envelope["approval"]["authorizes"],
            "scope": envelope["approval"]["scope"],
            "consumed": False,
            "note": (
                "Authorises one paper evaluation of this exact candidate. Not an "
                "order, wallet, credential, signature or live dispatch."
            ),
        }

    app.include_router(router)
