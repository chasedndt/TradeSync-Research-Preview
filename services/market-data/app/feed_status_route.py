"""``GET /feeds/status``: every market-data feed's heartbeat, as counted in memory since the service started."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .feed_status import REGISTRY
from .stream_status import refresh_feed_detail

router = APIRouter()


@router.get("/feeds/status")
async def feeds_status() -> dict[str, Any]:
    # The market stream's per-channel freshness is computed at the moment of reading, not when it last changed.
    refresh_feed_detail()
    return REGISTRY.snapshot()
