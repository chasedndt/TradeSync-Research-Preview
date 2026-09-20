"""Execution of a previewed decision, routed to the venue service, and the order record it leaves.

Moved out of ``app/main.py`` unchanged, with its legacy ``/execute`` alias.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app import error_responses
from app.deprecation import apply_deprecation_headers
from app.execution_flags import execution_gate_enabled, paper_mode_enabled
from tradesync_core import RiskGuardian
from tradesync_core.service_tokens import EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER, caller_headers

router = APIRouter()


class ExecutionError(BaseModel):
    code: str
    message: str

class ExecutionResult(BaseModel):
    ok: bool
    venue: str
    dry_run: bool
    execution_enabled: bool
    status: str # "placed" | "rejected" | "error"
    order_id: Optional[str] = None
    idempotency_key: str
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]
    error: Optional[ExecutionError] = None
    ts: str

class ExecuteRequest(BaseModel):
    decision_id: str
    confirm: bool

# ExecutionResult is used as the response model for execute_action


def register(app, state) -> None:
    """Attach ``/actions/execute`` and its legacy alias."""

    @router.post("/actions/execute", response_model=ExecutionResult)
    async def execute_action(req: ExecuteRequest):
        """Executes a decision (Routes to venue microservice)."""
        if not req.confirm:
            raise HTTPException(status_code=400, detail="Confirmation required")

        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        try:
            async with state.pool.acquire() as conn:
                # 1. Idempotency Check (Simplified: check if decision already has an order)
                existing_order = await conn.fetchrow("""
                    SELECT response FROM exec_orders WHERE decision_id = $1
                """, req.decision_id)
                if existing_order:
                    # Return the previously stored standardized response
                    return ExecutionResult(**json.loads(existing_order["response"]))

                # 2. Re-validate Decision & Risk
                dec_row = await conn.fetchrow("""
                    SELECT d.*, o.symbol, o.status as opp_status, o.quality, o.expires_at, o.dir
                    FROM decisions d
                    JOIN opportunities o ON d.opportunity_id = o.id
                    WHERE d.id = $1
                """, req.decision_id)

                if not dec_row:
                    raise HTTPException(status_code=404, detail="Decision not found")

                # FETCH Risk verdict again or use stored? Prompt says "Always return the same shape".
                # If rejected by risk now, we should still return an ExecutionResult.

                sig_row = await conn.fetchrow("""
                    SELECT * FROM signals WHERE symbol = $1 ORDER BY created_at DESC LIMIT 1
                """, dec_row["symbol"])

                risk_engine = RiskGuardian()
                opp_for_risk = {
                    "status": dec_row["opp_status"],
                    "quality": dec_row["quality"],
                    "expires_at": dec_row["expires_at"]
                }

                requested_data = json.loads(dec_row["requested"]) if isinstance(dec_row["requested"], str) else dec_row["requested"]
                verdict = risk_engine.check(
                    symbol=dec_row["symbol"],
                    size_usd=requested_data["size_usd"],
                    opportunity=opp_for_risk,
                    latest_signal=dict(sig_row) if sig_row else None,
                    phase="execute"
                )

                if not verdict.allowed:
                    # Return standard ExecutionResult for Risk Rejection
                    return ExecutionResult(
                        ok=False,
                        venue=dec_row["venue"],
                        # Nothing was sent to a venue: report the configured mode,
                        # not a literal claiming this was a live action.
                        dry_run=paper_mode_enabled(),
                        execution_enabled=execution_gate_enabled(),
                        status="rejected",
                        idempotency_key=str(req.decision_id),
                        request_payload=requested_data,
                        response_payload={},
                        error=ExecutionError(code="RISK_REJECTION", message=verdict.reason),
                        ts=datetime.utcnow().isoformat()
                    )

                # 3. Venue Routing
                venue = dec_row["venue"]
                exec_result = None
                direction = str(dec_row["dir"]).lower()
                side_by_direction = {"long": "buy", "buy": "buy", "short": "sell", "sell": "sell"}
                order_side = side_by_direction.get(direction)
                if order_side is None:
                    raise HTTPException(status_code=400, detail=f"Unsupported opportunity direction: {direction}")

                exec_url_map = {
                    "hyperliquid": "http://exec-hl-svc:8004/exec/hl/order"
                }

                if venue not in exec_url_map:
                     raise HTTPException(status_code=400, detail=f"Unsupported venue: {venue}")

                async with httpx.AsyncClient() as client:
                    try:
                        resp = await client.post(
                            exec_url_map[venue],
                            json={
                                "symbol": dec_row["symbol"],
                                "side": order_side,
                                "order_type": "market",
                                "size_usd": requested_data["size_usd"],
                                "venue": venue,
                                "idempotency_key": req.decision_id
                            },
                            # exec-hl-svc answers only state-api's caller token (L6).
                            headers=caller_headers(EXEC_TOKEN_ENV, EXEC_TOKEN_HEADER),
                            timeout=5.0
                        )
                        if resp.status_code == 200:
                            exec_result = ExecutionResult(**resp.json())
                        else:
                            # Handle non-200 from exec svc
                            exec_result = ExecutionResult(
                                ok=False,
                                venue=venue,
                                dry_run=paper_mode_enabled(),
                                execution_enabled=execution_gate_enabled(),
                                status="error",
                                idempotency_key=str(req.decision_id),
                                request_payload=requested_data,
                                response_payload={"http_status": resp.status_code, "body": resp.text},
                                error=ExecutionError(code="RPC_FAIL", message=f"Venue service returned {resp.status_code}"),
                                ts=datetime.utcnow().isoformat()
                            )
                    except Exception as e:
                        ref = error_responses.reference(e, "execute: venue call")
                        exec_result = ExecutionResult(
                            ok=False,
                            venue=venue,
                            dry_run=paper_mode_enabled(),
                            execution_enabled=execution_gate_enabled(),
                            status="error",
                            idempotency_key=str(req.decision_id),
                            request_payload=requested_data,
                            response_payload={},
                            error=ExecutionError(code="UNKNOWN", message=f"Venue service call failed ({type(e).__name__}); log reference {ref}"),
                            ts=datetime.utcnow().isoformat()
                        )

                # 4. Persist Execution Order
                # The row's id is always a fresh UUID. The venue's order id is the
                # venue's to format ("sim_hl_..." in paper mode, a number on
                # Hyperliquid), so it is kept in txid and in the stored response.
                # Used as the key of this uuid column it failed every insert: no
                # row was kept, the caller was told the order failed, and a retry
                # found no order for the decision and reached the venue again.
                await conn.execute("""
                    INSERT INTO exec_orders (
                        id, decision_id, venue, request, response, status, dry_run, txid
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8
                    )
                """, str(uuid.uuid4()), req.decision_id, venue,
                     json.dumps(dec_row["requested"]) if isinstance(dec_row["requested"], dict) else dec_row["requested"],
                     exec_result.model_dump_json(),
                     exec_result.status,
                     exec_result.dry_run,
                     exec_result.order_id
                )

                if exec_result.ok and exec_result.status == "placed":
                    await conn.execute("""
                        UPDATE opportunities SET status = 'executed' 
                        WHERE id = $1
                    """, dec_row["opportunity_id"])

                return exec_result

        except HTTPException:
            raise
        except Exception as e:
            # Final fallback for unexpected errors: the type and a log reference, never the text.
            ref = error_responses.reference(e, "execute")
            return ExecutionResult(
                ok=False,
                venue="unknown",
                # The configured mode, as on every other failure path: a literal
                # False here told the caller a failed paper order had been live.
                dry_run=paper_mode_enabled(),
                execution_enabled=execution_gate_enabled(),
                status="error",
                idempotency_key="unknown",
                request_payload={},
                response_payload={},
                error=ExecutionError(code="UNKNOWN", message=f"Unexpected {type(e).__name__}; log reference {ref}"),
                ts=datetime.utcnow().isoformat()
            )

    @router.post("/execute", response_model=ExecutionResult, tags=["legacy"])
    async def execute_action_alias(response: Response, req: ExecuteRequest):
        apply_deprecation_headers(response, "/actions/execute")
        return await execute_action(req)

    app.include_router(router)
