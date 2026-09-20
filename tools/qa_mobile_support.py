"""Shared harness for the mobile real-SQL acceptance: no request leaves the process, and nothing is kept.

Importing this module installs the guard. From then on any httpx client that is not an in-process ASGI client
refuses to be built, so a real ntfy publish, or any other outbound request, fails loudly instead of leaving the
machine. Import it before anything that could build a client.
"""

import base64
import secrets
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import asyncpg
import httpx

KEY = "QA-fixture-control-key-used-only-inside-this-process"
RealAsyncClient = httpx.AsyncClient


class LocalOnlyClient(RealAsyncClient):
    def __init__(self, *args, **kwargs):
        if not isinstance(kwargs.get("transport"), httpx.ASGITransport):
            raise RuntimeError("only in-process ASGI requests are allowed in this acceptance")
        super().__init__(*args, **kwargs)


httpx.AsyncClient = LocalOnlyClient


class ProviderRefusal(Exception):
    def __init__(self, status_code):
        super().__init__("qa provider refusal")
        self.response = SimpleNamespace(status_code=status_code)


class Provider:
    """Stands in for ntfy. Each call takes the next planned outcome; nothing leaves the process."""

    def __init__(self):
        self.plan, self.calls = [], 0

    async def publish(self, topic, kind, event_id):
        self.calls += 1
        outcome = self.plan.pop(0) if self.plan else "accept"
        if outcome == "accept":
            return f"qa-provider-acceptance-{self.calls}"
        raise outcome


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


async def throwaway_connection(dsn):
    """A connection to a throwaway database, or SystemExit.

    Refuses the compose PostgreSQL port (5432), a database named tradesync, a database without migration 038, and
    one that already holds mobile outbox rows.
    """
    conn = await asyncpg.connect(dsn)
    port, database = await conn.fetchval("select current_setting('port')"), await conn.fetchval("select current_database()")
    if port == "5432" or database == "tradesync":
        await conn.close()
        raise SystemExit(f"refusing: port {port} and database {database} look like the running stack")
    if await conn.fetchval("select count(*) from schema_migrations where version = '038'") != 1:
        await conn.close()
        raise SystemExit("refusing: migration 038 is not applied to this database")
    if await conn.fetchval("select count(*) from mobile_alert_outbox") != 0:
        await conn.close()
        raise SystemExit("refusing: expected a fresh throwaway database with no mobile outbox rows")
    print(f"Throwaway PostgreSQL {await conn.fetchval('show server_version')} on port {port}, database {database}")
    return conn


async def new_device(conn, label):
    device = uuid.uuid4()
    await conn.execute("INSERT INTO mobile_alert_devices (id, label, platform, topic) VALUES ($1, $2, 'android', $3)",
                       device, label, "tradesync-" + secrets.token_hex(24))
    return device


async def outbox(conn, event_id):
    return await conn.fetchrow("SELECT * FROM mobile_alert_outbox WHERE id = $1", event_id)


async def refused(conn, sql, *args, error=asyncpg.CheckViolationError) -> bool:
    try:
        async with conn.transaction():
            await conn.execute(sql, *args)
    except error:
        return True
    return False
