"""Public operator settings the Cockpit saves and reads back: today, the WalletConnect project ID.

The WalletConnect (Reown) project ID identifies TradeSync to the WalletConnect relay when a wallet is paired by
QR on Execution Readiness. It is public, not a secret: the relay receives it with every pairing and anyone
watching the browser's traffic can read it. It cannot sign, move funds or read a wallet, so it may be saved and
shown. Secrets never go here. They stay in runtime.env, and the dashboard only learns whether one is configured.

- ``GET /state/settings/walletconnect``: the saved project ID or null, who saved it and when, and the latest
  changes.
- ``PUT /state/settings/walletconnect``: save it, or clear it with an empty ``project_id``. Anything but 32
  hexadecimal characters is refused without repeating it, so a key pasted by mistake is not echoed back. Each
  change keeps an audit row with who made it, when and the value it replaced (``ops/migrations/037``); saving
  the value already saved changes nothing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import public_settings_store as store

router = APIRouter(tags=["settings"])

WALLETCONNECT = "walletconnect_project_id"
PROJECT_ID = re.compile(r"[0-9a-fA-F]{32}")
PROJECT_SITE = "https://dashboard.reown.com"
MAX_NAME = 80
NOTE = ("A public identifier for WalletConnect pairing, not a secret: the relay receives it with every pairing. "
        "It cannot sign, move funds or read a wallet. Reown's free Starter plan provides one.")


class ProjectIdChange(BaseModel):
    # Plain strings, checked in the route: a length or pattern constraint here would repeat a mistaken paste
    # back in the validation error.
    project_id: str | None = None
    changed_by: str = ""


def checked_project_id(value: str | None) -> str | None:
    """The ID to save, or None to clear it. Raises ValueError with a sentence that never repeats the input."""
    text = (value or "").strip()
    if not text:
        return None
    if not PROJECT_ID.fullmatch(text):
        raise ValueError("A WalletConnect project ID is 32 characters, digits and the letters a to f, as Reown's dashboard "
                         "shows it. Nothing was saved. A project ID is never a wallet key or recovery phrase.")
    return text


def checked_name(value: str) -> str:
    name = value.strip()
    if not name or len(name) > MAX_NAME:
        raise ValueError(f"Enter your name, up to {MAX_NAME} characters; it is recorded with the change. Nothing was saved.")
    return name


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def settings_view(row: dict[str, Any] | None, changes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "walletconnect_settings_v1",
        "project_id": row["value"] if row else None,
        "updated_by": row["updated_by"] if row else None,
        "updated_at": _iso(row["updated_at"]) if row else None,
        "changes": [{"changed_by": change["changed_by"], "changed_at": _iso(change["changed_at"]),
                     "previous": change["previous"], "next": change["next"]} for change in changes],
        "project_site": PROJECT_SITE,
        "public": True,
        "note": NOTE,
    }


def register(app, state) -> None:
    def pool():
        if getattr(state, "pool", None) is None:
            raise HTTPException(status_code=503, detail="Settings database unavailable; nothing was read or saved.")
        return state.pool

    @router.get("/state/settings/walletconnect")
    async def get_walletconnect():
        db = pool()
        return settings_view(await store.read(db, WALLETCONNECT), await store.changes(db, WALLETCONNECT))

    @router.put("/state/settings/walletconnect")
    async def put_walletconnect(change: ProjectIdChange):
        try:
            value, changed_by = checked_project_id(change.project_id), checked_name(change.changed_by)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        db, now = pool(), datetime.now(timezone.utc)
        changed, previous = await store.save(db, WALLETCONNECT, value, changed_by, now)
        view = settings_view(await store.read(db, WALLETCONNECT), await store.changes(db, WALLETCONNECT))
        return {**view, "changed": changed, "previous": previous, "changed_by": changed_by,
                "changed_at": _iso(now) if changed else None}

    app.include_router(router)
