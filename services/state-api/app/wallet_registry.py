"""Audited public-address wallet registry; never key custody or proof of ownership.

The Cockpit may remember which Hyperliquid accounts the operator wants to
observe.  It must never accept or persist a recovery phrase, private key,
signature, or WalletConnect session.  A connected browser wallet contributes
the same durable fact as a manually entered watch address: a public EVM address.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
CONNECTORS = {"phantom", "browser_wallet", "walletconnect", "watch_only"}
MAX_NAME = 80
MAX_REASON = 240

router = APIRouter(tags=["wallets"])


class WalletChange(BaseModel):
    address: str
    label: str = "Hyperliquid account"
    connector: Literal["phantom", "browser_wallet", "walletconnect", "watch_only"]
    operator: str
    reason: str = "Added from Execution Readiness"


class WalletDisconnect(BaseModel):
    operator: str
    reason: str


def public_address(value: str) -> str:
    """Return the canonical public address without ever repeating bad input."""
    text = (value or "").strip()
    if not ADDRESS.fullmatch(text):
        raise ValueError(
            "Enter a public EVM address: 0x plus 40 hexadecimal characters. "
            "A recovery phrase or private key is never accepted here."
        )
    return text.lower()


def bounded(value: str, name: str, maximum: int) -> str:
    text = (value or "").strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{name} must be between 1 and {maximum} characters.")
    return text


def view(row) -> dict:
    data = dict(row)
    for key in ("id",):
        data[key] = str(data[key])
    for key in ("added_at", "last_seen_at"):
        if data.get(key):
            data[key] = data[key].isoformat()
    return data


def register(app, state) -> None:
    def pool():
        if getattr(state, "pool", None) is None:
            raise HTTPException(503, "Wallet registry database unavailable; no wallet was read or changed.")
        return state.pool

    @router.get("/state/wallets")
    async def wallets():
        async with pool().acquire() as conn:
            rows = await conn.fetch(
                "SELECT id,address,label,connector,status,added_by,added_at,last_seen_at "
                "FROM wallet_connections ORDER BY status, last_seen_at DESC, id"
            )
        return {
            "wallets": [view(row) for row in rows],
            "authority": "address_only",
            "execution_authority": False,
            "note": "Public addresses only. A listed wallet is not proof of ownership and cannot sign through this registry.",
        }

    @router.post("/state/wallets")
    async def add_wallet(change: WalletChange):
        try:
            address = public_address(change.address)
            label = bounded(change.label, "Label", MAX_NAME)
            operator = bounded(change.operator, "Operator", MAX_NAME)
            reason = bounded(change.reason, "Reason", MAX_REASON)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        if change.connector not in CONNECTORS:
            raise HTTPException(400, "Unsupported wallet connector.")

        db = pool()
        async with db.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", 400917)
                previous = await conn.fetchrow(
                    "SELECT id,label,connector,status FROM wallet_connections WHERE address=$1 FOR UPDATE", address
                )
                if previous:
                    action = "renamed" if previous["label"] != label else "reconnected"
                    row = await conn.fetchrow(
                        "UPDATE wallet_connections SET label=$2,connector=$3,status='active',last_seen_at=now() "
                        "WHERE address=$1 RETURNING id,address,label,connector,status,added_by,added_at,last_seen_at",
                        address, label, change.connector,
                    )
                else:
                    action = "added"
                    row = await conn.fetchrow(
                        "INSERT INTO wallet_connections(address,label,connector,added_by) VALUES($1,$2,$3,$4) "
                        "RETURNING id,address,label,connector,status,added_by,added_at,last_seen_at",
                        address, label, change.connector, operator,
                    )
                await conn.execute(
                    "INSERT INTO wallet_connection_events(wallet_id,action,operator,reason,connector) VALUES($1,$2,$3,$4,$5)",
                    row["id"], action, operator, reason, change.connector,
                )
        return {"wallet": view(row), "action": action, "authority": "address_only", "execution_authority": False}

    @router.post("/state/wallets/{identity}/disconnect")
    async def disconnect_wallet(identity: uuid.UUID, change: WalletDisconnect):
        try:
            operator = bounded(change.operator, "Operator", MAX_NAME)
            reason = bounded(change.reason, "Reason", MAX_REASON)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        async with pool().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "UPDATE wallet_connections SET status='disconnected',last_seen_at=now() WHERE id=$1 AND status='active' "
                    "RETURNING id,address,label,connector,status,added_by,added_at,last_seen_at", identity,
                )
                if row is None:
                    raise HTTPException(404, "Active wallet connection not found.")
                await conn.execute(
                    "INSERT INTO wallet_connection_events(wallet_id,action,operator,reason,connector) VALUES($1,'disconnected',$2,$3,$4)",
                    identity, operator, reason, row["connector"],
                )
        return {"wallet": view(row), "action": "disconnected", "authority": "address_only", "execution_authority": False}

    app.include_router(router)
