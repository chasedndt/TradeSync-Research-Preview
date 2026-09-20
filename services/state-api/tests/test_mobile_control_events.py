"""Kill-switch notifications: opted-in phones only, generic text, once per event, the shared quiet-hours and budget rule."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import mobile_alerts as mobile
from app import mobile_control_events as control
from app.main import app, state
from app.mobile_policy import Preferences

KEY = "k" * 40
ENABLED_AT = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)


@asynccontextmanager
async def nothing():
    yield


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


class ProducerConn:
    """Answers the producer's reads: the opted-in phones, then each phone's new events from a source."""

    def __init__(self, devices, events):
        self.devices, self.events, self.calls = devices, events, []

    def transaction(self):
        return nothing()

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.devices if "FROM mobile_alert_devices" in sql else self.events.get(args[1], [])


def phone(preferences, enabled_at=ENABLED_AT):
    return {"id": uuid.uuid4(), "notification_preferences": json.dumps(preferences), "control_events_enabled_at": enabled_at}


def produce(conn):
    queued = []

    async def queue_or_suppress(_conn, device_id, key, _preferences, used):
        queued.append((device_id, key, used))
        return used + 1

    budget = AsyncMock(return_value=3)
    handled = asyncio.run(control.produce(Pool(conn), queue_or_suppress, budget))
    return handled, queued, budget


def test_only_phones_opted_in_to_control_events_are_considered():
    opted_in, paper_only = phone({"control_events": True}), phone({"paper_events": True})
    kill, resume = {"id": uuid.uuid4()}, {"id": uuid.uuid4()}
    conn = ProducerConn([opted_in, paper_only], {opted_in["id"]: [kill, resume], paper_only["id"]: [{"id": uuid.uuid4()}]})
    handled, queued, budget = produce(conn)
    assert handled == 2
    assert queued == [
        (opted_in["id"], f"control:paper_kill_switch:{kill['id']}", 3),
        (opted_in["id"], f"control:paper_kill_switch:{resume['id']}", 4),
    ]
    budget.assert_awaited_once()
    assert budget.await_args.args[1] == opted_in["id"]


def test_the_producer_locks_then_reads_engage_and_resume_since_the_opt_in_without_requeueing():
    opted_in = phone({"control_events": True})
    conn = ProducerConn([opted_in], {})
    produce(conn)
    (kind, lock_sql, lock_args), _, (_, events_sql, events_args) = conn.calls
    assert kind == "execute" and "pg_advisory_xact_lock" in lock_sql and lock_args == (control.PRODUCER_LOCK,)
    # The same lock as the paper producer, so the two never count one phone's budget at once.
    assert f"pg_advisory_xact_lock({control.PRODUCER_LOCK})" in inspect.getsource(mobile.produce_paper_events)
    assert "action IN ('kill', 'resume')" in events_sql and "created_at >= $1" in events_sql and "interval '10 minutes'" in events_sql
    assert "NOT EXISTS" in events_sql and "'control:paper_kill_switch:' || e.id::text" in events_sql
    assert events_args == (ENABLED_AT, opted_in["id"])


class QueueConn:
    def __init__(self):
        self.enqueued, self.executed = [], []

    async def fetchval(self, sql, *args):
        self.enqueued.append(args)
        return uuid.UUID(int=len(self.enqueued))

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def test_an_event_becomes_the_generic_attention_message_or_is_dropped_for_quiet_hours_or_budget():
    conn, device = QueueConn(), uuid.uuid4()
    key = f"control:paper_kill_switch:{uuid.uuid4()}"
    awake = Preferences(control_events=True, quiet_enabled=False, daily_budget=2)
    assert asyncio.run(mobile.queue_or_suppress(conn, device, key, awake, 1)) == 2
    assert conn.enqueued[0][1:] == (device, key, "attention") and conn.executed == []
    assert asyncio.run(mobile.queue_or_suppress(conn, device, key + "-b", awake, 2)) == 2
    assert conn.executed[-1][1][1] == "BudgetSuppressed"
    asleep = Preferences(control_events=True, quiet_enabled=True, quiet_start=8, quiet_end=8)
    assert asyncio.run(mobile.queue_or_suppress(conn, device, key + "-c", asleep, 0)) == 0
    assert conn.executed[-1][1][1] == "PreferenceSuppressed"
    text = mobile.message("attention", uuid.uuid4())
    assert text.startswith("TradeSync needs attention. Open your dashboard. Reference ")
    assert not any(word in text.lower() for word in ("kill", "resume", "switch", "paper", "btc", "operator"))


class DispatchConn:
    def __init__(self, preferences):
        self.preferences, self.executed = preferences, []
        self.row = {"id": uuid.UUID(int=7), "device_id": uuid.UUID(int=8), "kind": "attention",
                    "dedupe_key": f"control:paper_kill_switch:{uuid.UUID(int=9)}", "attempts": 1}

    async def execute(self, sql, *args):
        self.executed.append(sql)

    async def fetchrow(self, sql, *args):
        if sql.startswith("WITH candidate"):
            return self.row
        return {"notification_preferences": json.dumps(self.preferences), "enabled": True}

    async def fetchval(self, sql, *args):
        return "tradesync-" + "a" * 48


def dispatch(preferences):
    conn = DispatchConn(preferences)
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), patch.object(mobile, "publish", AsyncMock(return_value="provider-id")) as send:
        asyncio.run(mobile.dispatch_one(Pool(conn)))
    return conn, send


def test_delivery_checks_the_control_opt_in_again_before_sending():
    conn, send = dispatch({"control_events": False, "paper_events": True, "quiet_enabled": False})
    send.assert_not_awaited()
    assert any("PreferenceSuppressed" in sql for sql in conn.executed)
    conn, send = dispatch({"control_events": True, "quiet_enabled": False})
    send.assert_awaited_once()
    assert any("status='provider_accepted'" in sql for sql in conn.executed)


class PreferencesConn:
    def __init__(self, confirmed_at, stored=None):
        self.confirmed_at, self.stored, self.updates = confirmed_at, stored or {}, []

    def transaction(self):
        return nothing()

    async def fetchrow(self, sql, *args):
        return {"notification_preferences": json.dumps(self.stored), "operator_confirmed_at": self.confirmed_at}

    async def execute(self, sql, *args):
        self.updates.append((sql, args))


def save_preferences(monkeypatch, conn, body):
    monkeypatch.setattr(state, "pool", Pool(conn))
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        return TestClient(app).post(f"/state/mobile-alerts/devices/{uuid.uuid4()}/preferences", json=body, headers={"X-API-Key": KEY})


def test_a_phone_must_confirm_a_received_test_before_kill_switch_alerts(monkeypatch):
    conn = PreferencesConn(confirmed_at=None)
    response = save_preferences(monkeypatch, conn, {"control_events": True})
    assert response.status_code == 409 and conn.updates == []


def test_opting_in_records_when_and_opting_out_clears_it(monkeypatch):
    conn = PreferencesConn(confirmed_at=ENABLED_AT, stored={"control_events": True})
    assert save_preferences(monkeypatch, conn, {"control_events": False}).status_code == 200
    sql, args = conn.updates[0]
    assert "control_events_enabled_at=CASE WHEN NOT $5 THEN NULL WHEN NOT $6 THEN now() ELSE control_events_enabled_at END" in sql
    assert args[2:] == (False, False, False, True) and json.loads(args[1])["control_events"] is False
    conn = PreferencesConn(confirmed_at=ENABLED_AT)
    assert save_preferences(monkeypatch, conn, {"control_events": True}).status_code == 200
    assert conn.updates[0][1][2:] == (False, False, True, False)
