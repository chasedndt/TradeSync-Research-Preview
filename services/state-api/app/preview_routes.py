"""A preview: a plan for one opportunity, checked against the risk rules, and the decision it records.

Moved out of ``app/main.py`` unchanged, with its legacy ``/preview`` alias.
"""

import json
import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.deprecation import apply_deprecation_headers
from tradesync_core import RiskGuardian, normalize_venue

logger = logging.getLogger("state-api")
router = APIRouter()


class PreviewRequest(BaseModel):
    opportunity_id: str
    size_usd: float = 1000.0
    venue: str = "hyperliquid"

class PreviewResponse(BaseModel):
    decision_id: Optional[str] = None
    plan: Dict[str, Any]
    risk_verdict: Dict[str, Any]
    suggested_adjustments: Optional[Dict[str, Any]] = None


def register(app, state, *, market_data_url: str) -> None:
    """Attach ``/actions/preview`` and its legacy alias."""
    MARKET_DATA_URL = market_data_url

    @router.post("/actions/preview", response_model=PreviewResponse)
    async def preview_action(req: PreviewRequest):
        """Generates an execution plan and validates it against risk rules."""
        req.venue = normalize_venue(req.venue)
        risk_engine = RiskGuardian()

        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        try:
            async with state.pool.acquire() as conn:
                # 1. Fetch Opportunity
                row = await conn.fetchrow("SELECT * FROM opportunities WHERE id = $1", req.opportunity_id)
                if not row:
                    raise HTTPException(status_code=404, detail="Opportunity not found")
                opportunity = dict(row)
                symbol = opportunity["symbol"]

                # 2. Idempotency Check: Existing Decision for this venue?
                existing_decision = await conn.fetchrow("""
                    SELECT id, requested, risk FROM decisions WHERE opportunity_id = $1 AND venue = $2
                """, req.opportunity_id, req.venue)

                plan = {
                    "action": "Market Order",
                    "symbol": symbol,
                    "size_usd": req.size_usd,
                    "venue": req.venue,
                    "slippage_tolerance": 0.01
                }

                if existing_decision:
                    return PreviewResponse(
                        decision_id=str(existing_decision["id"]),
                        plan=json.loads(existing_decision["requested"]) if isinstance(existing_decision["requested"], str) else existing_decision["requested"],
                        risk_verdict=json.loads(existing_decision["risk"]) if isinstance(existing_decision["risk"], str) else existing_decision["risk"],
                        suggested_adjustments=None
                    )

                # 3. Fetch Latest Signal for this symbol
                sig_row = await conn.fetchrow("""
                    SELECT * FROM signals 
                    WHERE symbol = $1 
                    ORDER BY created_at DESC LIMIT 1
                """, symbol)
                latest_signal = dict(sig_row) if sig_row else None

                # 4. Check for existing decisions (count for cooldown/limit rules)
                recent_decisions = await conn.fetchval("""
                    SELECT count(*) FROM decisions
                    WHERE EXISTS (SELECT 1 FROM opportunities o WHERE o.id = decisions.opportunity_id AND o.symbol = $1)
                """, symbol)

                # Phase 3C: 4b. Fetch microstructure data for risk assessment
                microstructure = None
                margin_utilization = 0.0
                symbol_exposure_usd = 0.0

                try:
                    async with httpx.AsyncClient() as client:
                        # Fetch market snapshot with microstructure
                        market_resp = await client.get(
                            f"{MARKET_DATA_URL}/snapshot/{req.venue}/{symbol}",
                            timeout=2.0
                        )
                        if market_resp.status_code == 200:
                            market_data = market_resp.json()
                            microstructure = market_data.get("microstructure")

                        # Fetch current exposure (if available)
                        exposure_resp = await client.get(
                            "http://exec-hl-svc:8004/exec/hl/positions",
                            timeout=2.0
                        )
                        if exposure_resp.status_code == 200:
                            positions = exposure_resp.json()
                            for pos in positions:
                                if pos.get("symbol") == symbol:
                                    symbol_exposure_usd = abs(pos.get("notional", 0))
                            # Rough margin utilization (simplified)
                            total_notional = sum(abs(p.get("notional", 0)) for p in positions)
                            margin_utilization = total_notional / 50000.0  # Assuming $50k account
                except Exception as e:
                    logger.warning(f"Failed to fetch market/exposure data for risk check: {e}", extra={"trace_id": "preview"})

                # 5. Check Risk (Phase 3C: with microstructure data)
                verdict = risk_engine.check(
                    symbol=symbol,
                    size_usd=req.size_usd,
                    opportunity=opportunity,
                    latest_signal=latest_signal,
                    recent_decisions_count=recent_decisions,
                    microstructure=microstructure,
                    margin_utilization=margin_utilization,
                    symbol_exposure_usd=symbol_exposure_usd
                )

                decision_id = None
                if verdict.allowed:
                    # 6. Idempotent Decision Insert (Safety unique constraint)
                    decision_id = await conn.fetchval("""
                        INSERT INTO decisions (opportunity_id, venue, requested, risk)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (opportunity_id, venue) DO NOTHING
                        RETURNING id
                    """, req.opportunity_id, req.venue, json.dumps(plan), verdict.model_dump_json())

                    if not decision_id:
                        decision_id = await conn.fetchval("""
                            SELECT id FROM decisions WHERE opportunity_id = $1 AND venue = $2
                        """, req.opportunity_id, req.venue)

                    # 7. Update Status
                    await conn.execute("""
                        UPDATE opportunities SET status = 'previewed' 
                        WHERE id = $1 AND status = 'new'
                    """, req.opportunity_id)

                return PreviewResponse(
                    decision_id=str(decision_id) if decision_id else None,
                    plan=plan,
                    risk_verdict=verdict.model_dump(),
                    suggested_adjustments=verdict.suggested_adjustment
                )

        except HTTPException:
            raise
        except Exception as e:
            print(f"Preview error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/preview", response_model=PreviewResponse, tags=["legacy"])
    async def preview_action_alias(response: Response, req: PreviewRequest):
        apply_deprecation_headers(response, "/actions/preview")
        return await preview_action(req)

    app.include_router(router)
