"""Where public operator settings live: ``ops/migrations/037``, one row per setting and an audit row per change."""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Serialises changes to public settings, so each audit row's previous value is the one it replaced.
LOCK_KEY = 370915


async def read(pool, name: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT name, value, updated_by, updated_at FROM operator_public_settings WHERE name = $1", name)
    return dict(row) if row else None


async def save(pool, name: str, value: str | None, changed_by: str, now: datetime) -> tuple[bool, str | None]:
    """Save a value, or delete it with None, and keep an audit row: (whether it changed, the value it replaced).

    Saving the value already saved writes nothing, so the audit lists changes only.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", LOCK_KEY)
            previous = await conn.fetchval("SELECT value FROM operator_public_settings WHERE name = $1", name)
            if previous == value:
                return False, previous
            if value is None:
                await conn.execute("DELETE FROM operator_public_settings WHERE name = $1", name)
            else:
                await conn.execute(
                    "INSERT INTO operator_public_settings (name, value, updated_by, updated_at) VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, "
                    "updated_at = EXCLUDED.updated_at",
                    name, value, changed_by, now)
            await conn.execute(
                "INSERT INTO operator_public_settings_audit (name, changed_by, changed_at, previous, next) VALUES ($1, $2, $3, $4, $5)",
                name, changed_by, now, previous, value)
    return True, previous


async def changes(pool, name: str, limit: int = 10) -> list[dict[str, Any]]:
    """The latest changes to one setting, newest first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT changed_by, changed_at, previous, next FROM operator_public_settings_audit "
            "WHERE name = $1 ORDER BY changed_at DESC LIMIT $2", name, limit)
    return [dict(row) for row in rows]
