"""The risk policy in force and today's counters.

Moved out of ``app/main.py`` unchanged.
"""

import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from tradesync_core import RiskGuardian

router = APIRouter()


class RiskLimitResponse(BaseModel):
    max_leverage: float
    min_quality: float
    max_open_positions: int
    min_size_usd: float
    max_event_age: int
    max_signal_age: int
    blacklist: List[str]
    daily_notional_limit: float
    current_counters: Dict[str, Any]


def register(app, state) -> None:
    """Attach ``/state/risk/limits``."""

    @router.get("/state/risk/limits", response_model=RiskLimitResponse)
    async def get_risk_limits():
        """Returns the current risk policy and counters."""
        guardian = RiskGuardian()

        # Calculate current daily notional usage
        current_notional = 0.0
        if state.pool:
            try:
                async with state.pool.acquire() as conn:
                    row = await conn.fetchrow("""
                        SELECT SUM((request->>'size_usd')::float) as total
                        FROM exec_orders
                        WHERE status = 'placed' 
                        AND created_at >= CURRENT_DATE
                    """)
                    current_notional = row["total"] or 0.0
            except Exception as e:
                print(f"Error fetching daily notional: {e}")

        return RiskLimitResponse(
            max_leverage=guardian.max_leverage,
            min_quality=guardian.min_quality,
            max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "10")),
            min_size_usd=float(os.getenv("MIN_SIZE_USD", "10.0")),
            max_event_age=guardian.max_event_age,
            max_signal_age=guardian.max_signal_age,
            blacklist=guardian.blacklist,
            daily_notional_limit=float(os.getenv("DAILY_NOTIONAL_LIMIT", "50000.0")),
            current_counters={
                "daily_notional_usage": current_notional,
                "today_date": datetime.utcnow().date().isoformat()
            }
        )

    app.include_router(router)
