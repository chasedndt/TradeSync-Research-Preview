"""Real-SQL acceptance for the operator onboarding branch, on a THROWAWAY PostgreSQL only.

The database must have ops/sql/schema.sql and every migration through 037 applied. The script refuses the compose
PostgreSQL port (5432) and a database named tradesync. Everything runs inside one transaction that is rolled back.
No request leaves the process: ntfy publishing is replaced by a local fake, and any HTTP client that is not an
in-process ASGI client refuses to be built.

Covers the public settings store (save, no-op save, clear, audit order, the database's shape check), the TradingView
receipts query, and phone notifications end to end through the real preferences route: the confirmed-receipt rule,
control_events_enabled_at, kill-switch engage and resume queued once each as generic messages, the shared budget,
all-day quiet hours, opt-out enforced at delivery, events from before the opt-in never sent, and the paper lifecycle
producer after its helpers were extracted.

    python tools/qa_operator_onboarding_sql.py --dsn postgresql://qa@127.0.0.1:55437/tradesync_qa
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import httpx
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))
sys.path.insert(0, str(ROOT / "services" / "state-api"))

from app import mobile_alerts as mobile  # noqa: E402
from app import public_settings_store as settings_store  # noqa: E402
from app import tradingview_setup  # noqa: E402
from app.public_settings import WALLETCONNECT  # noqa: E402

KEY = "QA-fixture-control-key-used-only-inside-this-process"
PROJECT = "0123456789abcdef0123456789abcdef"
RealAsyncClient = httpx.AsyncClient


class LocalOnlyClient(RealAsyncClient):
    def __init__(self, *args, **kwargs):
        if not isinstance(kwargs.get("transport"), httpx.ASGITransport):
            raise RuntimeError("only in-process ASGI requests are allowed in this acceptance")
        super().__init__(*args, **kwargs)


httpx.AsyncClient = LocalOnlyClient


async def main(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    port, database = await conn.fetchval("select current_setting('port')"), await conn.fetchval("select current_database()")
    if port == "5432" or database == "tradesync":
        await conn.close()
        raise SystemExit(f"refusing: port {port} and database {database} look like the running stack")
    outer = conn.transaction()
    await outer.start()

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield conn

    pool = Pool()
    try:
        await settings(pool, conn)
        await receipts(pool, conn)
        await notifications(pool, conn)
    finally:
        await outer.rollback()
        await conn.close()
        print("Rolled back; nothing kept.")


async def settings(pool, conn) -> None:
    first, later = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(seconds=1)
    assert await settings_store.save(pool, WALLETCONNECT, PROJECT, "qa", first) == (True, None)
    row = await settings_store.read(pool, WALLETCONNECT)
    assert row["value"] == PROJECT and row["updated_by"] == "qa"
    assert await settings_store.save(pool, WALLETCONNECT, PROJECT, "someone else", first) == (False, PROJECT)
    assert await settings_store.save(pool, WALLETCONNECT, None, "qa", later) == (True, PROJECT)
    assert await settings_store.read(pool, WALLETCONNECT) is None
    history = await settings_store.changes(pool, WALLETCONNECT)
    assert [(h["previous"], h["next"]) for h in history] == [(PROJECT, None), (None, PROJECT)], history
    try:
        async with conn.transaction():
            await settings_store.save(pool, WALLETCONNECT, "not-a-project-id", "qa", later)
        raise AssertionError("the database accepted a malformed project ID")
    except asyncpg.CheckViolationError:
        pass
    print("PASS settings: save, no-op save, clear, audit newest first, malformed ID refused by the database")


async def receipts(pool, conn) -> None:
    payload = {"schema_version": "tradingview_alert_v1", "indicator": "QA indicator", "ticker": "BTCUSD", "interval": "15",
               "action": "", "alert": {"note": "qa", "secret": "must-not-be-returned"}}
    await conn.execute(
        "INSERT INTO quarantine_intake (source, accepted, content_digest, payload, reasons, received_at) "
        "VALUES ('tradingview', false, $1, $2::jsonb, $3::jsonb, clock_timestamp())",
        f"qa-{uuid.uuid4()}", json.dumps(payload), json.dumps([{"code": "qa_reason", "detail": "qa detail"}]))
    found, error = await tradingview_setup.latest_receipts(pool, 3)
    assert error is None and found[0]["indicator"] == "QA indicator" and found[0]["accepted"] is False
    assert found[0]["reasons"] == [{"code": "qa_reason", "detail": "qa detail"}] and "must-not-be-returned" not in json.dumps(found)
    print("PASS receipts: newest TradingView receipt with verdict and reasons, no payload returned")


async def count(conn, sql, *args) -> int:
    return await conn.fetchval(sql, *args)


async def notifications(pool, conn) -> None:
    os.environ["MOBILE_ALERTS_CONTROL_KEY"] = KEY
    sent = []

    async def fake_publish(topic, kind, identity):
        sent.append(mobile.message(kind, identity))
        return "qa-provider-acceptance-not-phone-receipt"

    mobile.publish = fake_publish
    # The paper producer reads managed_paper_events; a temporary table stands in for it.
    await conn.execute("CREATE TEMP TABLE managed_paper_events (id uuid PRIMARY KEY, kind text, created_at timestamptz DEFAULT clock_timestamp()) ON COMMIT DROP")
    device = uuid.uuid4()
    await conn.execute("INSERT INTO mobile_alert_devices (id, label, platform, topic) VALUES ($1, 'QA', 'android', $2)", device, "tradesync-" + "b" * 48)
    key = lambda event: f"control:paper_kill_switch:{event}"  # noqa: E731
    app = FastAPI()
    mobile.register(app, SimpleNamespace(pool=pool))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa", headers={"X-API-Key": KEY}) as client:
        endpoint = f"/state/mobile-alerts/devices/{device}/preferences"
        body = {"control_events": True, "paper_events": True, "quiet_enabled": False, "daily_budget": 3}
        assert (await client.post(endpoint, json=body)).status_code == 409
        await conn.execute("UPDATE mobile_alert_devices SET operator_confirmed_at = now() WHERE id = $1", device)
        before = uuid.uuid4()
        await conn.execute("INSERT INTO paper_kill_switch_events (id, created_at, action, operator, reason) VALUES ($1, now() - interval '1 minute', 'kill', 'qa', 'before the opt-in')", before)
        saved = await client.post(endpoint, json=body)
        assert saved.status_code == 200, saved.text
        enabled = await conn.fetchrow("SELECT control_events_enabled_at, paper_events_enabled_at FROM mobile_alert_devices WHERE id = $1", device)
        assert enabled["control_events_enabled_at"] is not None and enabled["paper_events_enabled_at"] is not None

        kill, resume, opened = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await conn.execute("INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES ($1, 'kill', 'qa', 'qa engaged'), ($2, 'resume', 'qa', 'qa cleared')", kill, resume)
        await conn.execute("INSERT INTO managed_paper_events (id, kind) VALUES ($1, 'opened')", opened)
        assert await mobile.worker_tick(pool) is None
        keys = {r["dedupe_key"] for r in await conn.fetch("SELECT dedupe_key FROM mobile_alert_outbox WHERE device_id = $1", device)}
        assert keys == {key(kill), key(resume), f"paper:{opened}"}, keys
        assert len(sent) == 1 and sent[0].startswith("TradeSync needs attention. Open your dashboard. Reference ")
        await mobile.produce_control_events(pool)
        await mobile.produce_paper_events(pool)
        assert await count(conn, "SELECT count(*) FROM mobile_alert_outbox WHERE device_id = $1", device) == 3
        assert await count(conn, "SELECT count(*) FROM mobile_alert_outbox WHERE dedupe_key = $1", key(before)) == 0

        third = uuid.uuid4()
        await conn.execute("INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES ($1, 'kill', 'qa', 'qa engaged again')", third)
        await mobile.produce_control_events(pool)
        assert await conn.fetchval("SELECT last_error FROM mobile_alert_outbox WHERE dedupe_key = $1", key(third)) == "BudgetSuppressed"

        assert (await client.post(endpoint, json={"control_events": False, "paper_events": True, "quiet_enabled": False, "daily_budget": 3})).status_code == 200
        assert await conn.fetchval("SELECT control_events_enabled_at FROM mobile_alert_devices WHERE id = $1", device) is None
        for _ in range(3):
            await mobile.dispatch_one(pool)
        outbox = {r["dedupe_key"]: (r["status"], r["last_error"]) for r in await conn.fetch("SELECT dedupe_key, status, last_error FROM mobile_alert_outbox WHERE device_id = $1", device)}
        controls = [outbox[key(kill)], outbox[key(resume)]]
        # One control message was delivered before the opt-out; whichever is left is stopped by it.
        assert all(status == "provider_accepted" or error == "PreferenceSuppressed" for status, error in controls), controls
        assert any(error == "PreferenceSuppressed" for _, error in controls), controls
        assert outbox[f"paper:{opened}"][0] == "provider_accepted", outbox
        accepted = await count(conn, "SELECT count(*) FROM mobile_alert_outbox WHERE device_id = $1 AND status = 'provider_accepted'", device)
        assert accepted == len(sent), (accepted, len(sent))

        quiet_body = {"control_events": True, "quiet_enabled": True, "quiet_start": 8, "quiet_end": 8, "daily_budget": 50}
        assert (await client.post(endpoint, json=quiet_body)).status_code == 200
        fourth = uuid.uuid4()
        await conn.execute("INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES ($1, 'resume', 'qa', 'qa cleared again')", fourth)
        await mobile.produce_control_events(pool)
        assert await conn.fetchval("SELECT last_error FROM mobile_alert_outbox WHERE dedupe_key = $1", key(fourth)) == "PreferenceSuppressed"
    assert all("kill" not in text.lower() and "resume" not in text.lower() for text in sent)
    print("PASS notifications: confirmed receipt required; engage and resume queued once each as the generic message; "
          "paper lifecycle beside them; shared budget; opt-out enforced at delivery; all-day quiet; no event from before the opt-in. "
          f"{len(sent)} fake provider acceptances, no network.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(main(parser.parse_args().dsn))
