"""While the agent harness is stopped, every TradeSync caller of Hermes refuses and says why, and none of them calls it."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import agent_connector, editions, fleet_live, harness_gate, hermes_jobs, horizon_reading, horizons, reading_schedule
from app import harness_control_store as store
from app.main import app, state

client = TestClient(app)
REASON = "Pausing Hermes for maintenance"
MEASURED = datetime.now(timezone.utc) - timedelta(minutes=1)
JOB = "6a1fdf7894c7"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def stopped(monkeypatch):
    store.reset_memory()
    monkeypatch.setattr(state, "pool", None)
    monkeypatch.setattr(horizon_reading, "_memory", {})
    run(store.request(None, "stopped", "chase", REASON))
    yield
    store.reset_memory()


def no_http() -> MagicMock:
    """Stands in for httpx.AsyncClient and fails the test if a caller tries to open one."""
    return MagicMock(side_effect=AssertionError("Hermes was called while the agent harness is stopped"))


def test_the_refusal_names_who_stopped_it_and_why() -> None:
    reason = run(harness_gate.refusal(None))
    assert "stopped by chase" in reason and REASON in reason and "TradeSync does not call Hermes" in reason


def test_a_switch_that_cannot_be_read_is_a_refusal() -> None:
    class Unreachable:
        def acquire(self):
            raise ConnectionError("database down")

    assert "could not be read (ConnectionError)" in run(harness_gate.refusal(Unreachable()))
    malformed = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield MagicMock(fetchrow=AsyncMock(return_value={"unexpected": True}))

    malformed.acquire = acquire
    assert "could not be read (KeyError)" in run(harness_gate.refusal(malformed))


def test_a_timeframe_reading_does_not_start_and_its_route_answers_423() -> None:
    outlook = {"available": True}
    result = run(horizon_reading.start(None, "BTC-PERP", "short", outlook, {}, MEASURED))
    assert result["status"] == "stopped" and REASON in result["detail"] and horizon_reading._memory == {}
    entry = {"at": MEASURED.timestamp(), "outlook": outlook, "evaluation": {}}
    with patch.object(horizons, "part_or_error", AsyncMock(return_value=(entry, None))):
        response = client.post("/state/market/horizons/reading?symbol=BTC-PERP&scope=short")
    assert response.status_code == 423 and REASON in response.json()["detail"] and horizon_reading._memory == {}


def test_a_reading_already_started_when_the_harness_stops_finishes_without_asking() -> None:
    row_id = run(horizon_reading._insert(None, "BTC-PERP", "lower", MEASURED))
    with patch.object(agent_connector, "configured", return_value=True), patch.object(horizon_reading.httpx, "AsyncClient", no_http()):
        run(horizon_reading.run_reading(None, "BTC-PERP", "lower", row_id, {"available": True}, {}))
    view = run(horizon_reading.latest(None, "BTC-PERP"))["lower"]
    assert view["status"] == "unavailable" and REASON in view["attempt"]["detail"]


def test_a_scheduled_reading_is_skipped_with_the_reason_before_anything_is_measured() -> None:
    part = AsyncMock()
    with patch.object(agent_connector, "configured", return_value=True), patch.object(horizons, "part_or_error", part):
        result, detail = run(reading_schedule.start_scheduled(None, "http://md", "BTC-PERP", "short"))
    assert result == "skipped" and REASON in detail
    part.assert_not_awaited()


def test_the_thesis_briefing_is_not_drafted_and_the_edition_records_why() -> None:
    outlook = {"breadth": {"summary": ""}, "leads": [], "key_events": [], "notes": []}
    with patch.object(agent_connector, "configured", return_value=True), patch.object(editions.httpx, "AsyncClient", no_http()):
        briefing = run(editions.hermes_briefing(outlook, None))
    assert briefing["status"] == "stopped" and REASON in briefing["detail"]


class FleetConn:
    """The job is known; the control row is read through the store's own statement and says stopped."""

    def __init__(self, control):
        self.control = control
        self.fetchval = AsyncMock(return_value=1)
        self.fetch = AsyncMock(return_value=[])
        self.execute = AsyncMock()
        self.inserted: list[tuple] = []

    async def fetchrow(self, sql, *args):
        if sql == store.CURRENT_SQL:
            return self.control
        self.inserted.append(args)
        return {"id": "11111111-1111-1111-1111-111111111111", "requested_at": datetime(2026, 9, 15, tzinfo=timezone.utc)}


def fleet_pool(conn: FleetConn) -> MagicMock:
    pool = MagicMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool.acquire = acquire
    return pool


def test_a_gateway_only_directive_is_refused_with_423_and_the_gateway_is_never_asked() -> None:
    conn = FleetConn(run(store.current(None)))
    get_job = AsyncMock()
    with patch.object(state, "pool", fleet_pool(conn)), patch.object(hermes_jobs, "available", return_value=True), \
            patch.object(hermes_jobs, "get_job", get_job):
        for kind in ("pause", "resume", "run_now"):
            response = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": kind})
            assert response.status_code == 423 and REASON in response.json()["detail"], kind
    get_job.assert_not_awaited()
    assert conn.inserted == []


def test_a_schedule_or_enabled_change_waits_for_the_host_bridge_instead_of_the_gateway() -> None:
    conn = FleetConn(run(store.current(None)))
    get_job = AsyncMock()
    with patch.object(state, "pool", fleet_pool(conn)), patch.object(hermes_jobs, "available", return_value=True), \
            patch.object(hermes_jobs, "get_job", get_job):
        response = client.post("/state/fleet/directives", json={"job_id": JOB, "kind": "set_enabled", "enabled": False})
    body = response.json()
    assert response.status_code == 200 and body["status"] == "pending" and body["channel"] == "bridge"
    assert REASON in body["detail"] and body["detail"].endswith("Left for the host bridge.")
    get_job.assert_not_awaited()


def test_the_fleet_page_reads_job_state_from_the_bridge_without_asking_the_gateway() -> None:
    list_jobs = AsyncMock()
    reason = run(harness_gate.refusal(None))
    with patch.object(hermes_jobs, "list_jobs", list_jobs):
        rows, meta = run(fleet_live.overlay([{"job_id": JOB}], refusal=reason))
        with patch.object(state, "pool", fleet_pool(FleetConn(run(store.current(None))))):
            page = client.get("/state/fleet/jobs").json()
    list_jobs.assert_not_awaited()
    assert rows[0]["state_source"] == "bridge" and meta["status"] == "stopped" and meta["detail"] == reason
    assert page["live_state"]["status"] == "stopped" and REASON in page["live_state"]["detail"]


def test_the_ask_route_refuses_core_scorer_and_every_other_asker_with_423() -> None:
    ask = AsyncMock()
    with patch.object(agent_connector, "configured", return_value=True), patch.object(agent_connector, "ask", ask):
        response = client.post("/state/agents/harness/ask", json={"intent": "summarise", "prompt": "What did the desk say?"})
    assert response.status_code == 423 and REASON in response.json()["detail"] and response.json()["harness"] == "stopped"
    ask.assert_not_awaited()
