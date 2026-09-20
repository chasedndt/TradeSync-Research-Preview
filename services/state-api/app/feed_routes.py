"""Macro headlines and the free contextual provider feeds.

Moved out of ``app/main.py`` unchanged. Both are secondary context: they inform
an operator and never grant scoring, approval or execution authority, and a feed
that fails answers with its status rather than taking the page down with it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app import error_responses
from app.context_feed import context_feed
from app.macro_feed import macro_feed

logger = logging.getLogger("state-api")
router = APIRouter()


class MacroHeadlineResponse(BaseModel):
    title: str
    source: str
    category: str
    url: str
    published_at: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None


class MacroFeedResponse(BaseModel):
    headlines: List[MacroHeadlineResponse]
    status: Dict[str, Any]
    cached: bool
    ts: str


def register(app, state) -> None:
    """Attach the macro and secondary-context routes."""

    @router.get("/state/macro/headlines", response_model=MacroFeedResponse, tags=["macro"])
    async def get_macro_headlines(
        refresh: bool = Query(False, description="Force refresh from sources"),
        limit: int = Query(20, le=50, description="Max headlines to return"),
        category: Optional[str] = Query(None, description="Filter by category (crypto, macro)")
    ):
        """
        Get macro news headlines from RSS feeds.

        Phase 3C MVP: Simple RSS aggregation for trading context.
        """
        try:
            headlines = await macro_feed.fetch_headlines(force_refresh=refresh)

            # Filter by category if specified
            if category:
                headlines = [h for h in headlines if h.category == category]

            # Apply limit
            headlines = headlines[:limit]

            return MacroFeedResponse(
                headlines=[MacroHeadlineResponse(**h.to_dict()) for h in headlines],
                status=macro_feed.get_status(),
                cached=not refresh,
                ts=datetime.now(timezone.utc).isoformat()
            )
        except Exception as e:
            logger.error(f"Error fetching macro headlines: {e}", extra={"trace_id": "macro"})
            ref = error_responses.reference(e, "macro headlines")
            return MacroFeedResponse(
                headlines=[],
                # The type and a log reference, never the exception's text (L4).
                status={"error": f"{type(e).__name__}; log reference {ref}", **macro_feed.get_status()},
                cached=False,
                ts=datetime.now(timezone.utc).isoformat()
            )

    @router.get("/state/macro/status", tags=["macro"])
    async def get_macro_status():
        """Get macro feed service status."""
        return macro_feed.get_status()

    @router.get("/state/context/overview", tags=["context"])
    async def get_context_overview(
        refresh: bool = Query(False, description="Force a refresh of enabled context feeds")
    ):
        """Return cached secondary context without granting scoring or execution authority."""
        return await context_feed.fetch_overview(force_refresh=refresh)

    @router.get("/state/context/status", tags=["context"])
    async def get_context_status():
        """Return configuration and cache policy for secondary context feeds."""
        return context_feed.get_status()

    app.include_router(router)
