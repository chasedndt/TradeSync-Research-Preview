"""``GET /state/operator/retention``: how long each record is kept, for Settings.

The windows come from ``tradesync_core.retention_policy``. The two paper windows
are the ``keep_days`` defaults of the store functions that delete those rows,
read from their signatures, because those functions are always called with the
default: the window shown is therefore the window applied, and a change to either
default changes this reading with it.

Static facts: no database read, nothing written.
"""

from __future__ import annotations

import inspect
from typing import Callable

from fastapi import APIRouter

from app import paper_correlation_store, paper_reconciliation_store
from app.market_recorder import RETENTION_EVERY_S
from tradesync_core.retention_policy import retention_policy

router = APIRouter(tags=["settings"])


def keep_days_default(function: Callable[..., object]) -> int:
    """The ``keep_days`` a store's delete function applies when called, as it always is, without one."""
    return int(inspect.signature(function).parameters["keep_days"].default)


def register(app, state) -> None:
    @router.get("/state/operator/retention")
    async def retention():
        return retention_policy(
            correlation_keep_days=keep_days_default(paper_correlation_store.prune),
            reconciliation_keep_days=keep_days_default(paper_reconciliation_store.prune_runs),
            recorder_every_s=RETENTION_EVERY_S,
        )

    app.include_router(router)
