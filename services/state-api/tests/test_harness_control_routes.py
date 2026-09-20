"""The switch's routes: validation, the audit, the host's claim and report, the ask gate, and the access guard in front of them."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import agent_connector, harness_control_routes, hermes_link
from app import harness_control_store as store
from app.access_guard import AccessGuard
from app.main import app, state
from tradesync_core.state_api_access import MIN_TOKEN_CHARS, TOKEN_HEADER

client = TestClient(app)
FOREIGN = "https://example.invalid"
COCKPIT = "http://127.0.0.1:3000"
STOP = {"desired_state": "stopped", "operator": "chase", "reason": "Hermes compute needed elsewhere", "confirm": True}
START = {**STOP, "desired_state": "running", "reason": "Back to normal"}
LINK = {"status": "live", "last_seen_at": None, "seconds_since_seen": None, "last_error": None, "consecutive_failures": 0}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    store.reset_memory()
    monkeypatch.setattr(state, "pool", None)
    monkeypatch.setitem(harness_control_routes._host, "last_poll_at", None)
    monkeypatch.setattr(hermes_link, "status_now", lambda: dict(LINK))
    yield
    store.reset_memory()


def run(coro):
    return asyncio.run(coro)


def test_installed_the_switch_reads_running_with_calls_allowed_and_no_history() -> None:
    body = client.get("/state/agents/harness/control").json()
    assert body["schema_version"] == "agent_harness_control_v1"
    assert body["desired"]["state"] == "running" and body["desired"]["operator"] == "migration 034"
    assert body["desired"]["command_id"] is None and body["host"]["status"] == "none" and body["host"]["result"] is None
    assert body["gate"] == {"open": True, "reason": None} and body["agreement"]["state"] == "agree" and body["history"] == []
    gate = client.get("/state/agents/harness/gate").json()
    assert gate["open"] is True and gate["reason"] is None and gate["desired_state"] == "running"
    assert client.get("/state/agents/harness/control/command").json()["command"] is None


@pytest.mark.parametrize("change", [
    {key: value for key, value in STOP.items() if key != "confirm"},
    {**STOP, "confirm": False},
    {**STOP, "reason": "no"},
    {**STOP, "reason": "  ok  "},
    {**STOP, "reason": "x" * 241},
    {**STOP, "operator": "   "},
    {**STOP, "operator": "o" * 81},
    {**STOP, "desired_state": "paused"},
    {key: value for key, value in STOP.items() if key != "desired_state"},
])
def test_a_change_needs_a_state_an_operator_a_meaningful_reason_and_a_confirmation(change) -> None:
    assert client.post("/state/agents/harness/control", json=change).status_code == 422
    assert run(store.history(None)) == [] and run(store.current(None))["desired_state"] == "running"


def test_a_stop_refuses_tradesync_calls_at_once_and_queues_one_command_for_the_host() -> None:
    response = client.post("/state/agents/harness/control", json=STOP)
    body = response.json()
    assert response.status_code == 200 and body["requested"]["previous_state"] == "running"
    assert body["desired"]["state"] == "stopped" and body["desired"]["command_id"] == body["requested"]["command_id"]
    assert body["gate"]["open"] is False and "stopped by chase" in body["gate"]["reason"] and STOP["reason"] in body["gate"]["reason"]
    assert body["host"]["status"] == "pending" and body["agreement"]["state"] == "pending"
    [event] = body["history"]
    assert (event["kind"], event["operator"], event["reason"], event["previous_state"]) == ("requested", "chase", STOP["reason"], "running")
    gate = client.get("/state/agents/harness/gate").json()
    assert gate["open"] is False and gate["desired_state"] == "stopped" and gate["reason"] == body["gate"]["reason"]
    polled = client.get("/state/agents/harness/control/command").json()
    assert polled["command"] == {"id": body["requested"]["command_id"], "desired_state": "stopped", "status": "pending",
                                 "requested_at": body["desired"]["requested_at"], "operator": "chase"}
    assert polled["poll_interval_s"] == 10
    assert client.get("/state/agents/harness/control").json()["host"]["seconds_since_poll"] is not None


def test_the_host_claims_a_command_once_and_reports_it_once() -> None:
    command_id = client.post("/state/agents/harness/control", json=STOP).json()["requested"]["command_id"]

    def claim():
        return client.post("/state/agents/harness/control/claim", json={"command_id": command_id})

    assert claim().status_code == 200
    again = claim()
    assert again.status_code == 409 and "never handed out to run twice" in again.json()["detail"]
    assert client.get("/state/agents/harness/control/command").json()["command"]["status"] == "applying"
    report = {"command_id": command_id, "status": "applied", "command": "wsl.exe -d Ubuntu -- hermes gateway stop",
              "exit_status": 0, "is_active": "inactive", "detail": "the gateway is stopped"}
    first = client.post("/state/agents/harness/control/report", json=report)
    duplicate = client.post("/state/agents/harness/control/report", json={**report, "status": "failed"})
    assert first.json() == {"recorded": True, "duplicate": False, "command_id": command_id}
    assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
    body = client.get("/state/agents/harness/control").json()
    assert body["host"]["status"] == "applied" and body["host"]["result"]["is_active"] == "inactive"
    assert body["host"]["result"]["for_current_command"] is True and body["agreement"]["state"] == "agree"
    assert [event["kind"] for event in body["history"]] == ["applied", "applying", "requested"]
    assert client.get("/state/agents/harness/control/command").json()["command"] is None
    assert claim().status_code == 409


def test_the_host_cannot_claim_or_report_what_was_never_requested() -> None:
    unknown = str(uuid.uuid4())
    assert client.post("/state/agents/harness/control/claim", json={"command_id": unknown}).status_code == 404
    report = {"command_id": unknown, "status": "applied", "command": "x", "exit_status": 0, "is_active": "inactive"}
    assert client.post("/state/agents/harness/control/report", json=report).status_code == 404
    for bad in ({**report, "status": "done"}, {**report, "is_active": "a" * 81}, {**report, "command_id": "not-a-uuid"},
                {**report, "command": ""}):
        assert client.post("/state/agents/harness/control/report", json=bad).status_code == 422
    assert run(store.history(None)) == []


def test_while_stopped_the_ask_route_refuses_before_hermes_and_a_start_lifts_it() -> None:
    ask = AsyncMock()
    prompt = {"intent": "summarise", "prompt": "What did the desk say about BTC?"}
    with patch.object(agent_connector, "configured", return_value=True), patch.object(agent_connector, "ask", ask):
        client.post("/state/agents/harness/control", json=STOP)
        refused = client.post("/state/agents/harness/ask", json=prompt)
        client.post("/state/agents/harness/control", json=START)
        lifted = client.post("/state/agents/harness/ask", json=prompt)
    assert refused.status_code == 423 and refused.json()["harness"] == "stopped" and "stopped by chase" in refused.json()["detail"]
    # Running again, the route answers for itself: there is no database in this test, so 503 before anything is asked.
    assert lifted.status_code == 503 and lifted.json()["detail"] == "DB Pool not ready"
    ask.assert_not_awaited()


def test_a_missing_switch_answers_503_and_keeps_every_hermes_call_refused() -> None:
    store._memory["row"] = None
    missing = client.get("/state/agents/harness/control")
    assert missing.status_code == 503 and "migration 034" in missing.json()["detail"]
    assert client.post("/state/agents/harness/control", json=STOP).status_code == 503
    assert client.get("/state/agents/harness/control/command").status_code == 503
    gate = client.get("/state/agents/harness/gate").json()
    assert gate["open"] is False and "migration 034" in gate["reason"] and gate["desired_state"] is None
    with patch.object(agent_connector, "configured", return_value=True):
        assert client.post("/state/agents/harness/ask", json={"intent": "summarise", "prompt": "x"}).status_code == 423


def test_a_cross_site_page_cannot_stop_or_start_hermes_or_forge_the_host_side() -> None:
    guarded = TestClient(AccessGuard(app, token="", allowed_origins=[]))
    assert guarded.post("/state/agents/harness/control", json=STOP, headers={"Origin": FOREIGN}).status_code == 403
    forged = {"command_id": str(uuid.uuid4()), "status": "applied", "command": "x", "exit_status": 0, "is_active": "inactive"}
    assert guarded.post("/state/agents/harness/control/report", json=forged, headers={"Origin": FOREIGN}).status_code == 403
    assert guarded.post("/state/agents/harness/control/claim", json={"command_id": forged["command_id"]},
                        headers={"Origin": FOREIGN}).status_code == 403
    assert run(store.current(None))["desired_state"] == "running" and run(store.history(None)) == []
    assert guarded.post("/state/agents/harness/control", json=STOP, headers={"Origin": COCKPIT}).status_code == 200


def test_with_an_operator_token_every_switch_change_must_carry_it() -> None:
    token = "t" * MIN_TOKEN_CHARS
    guarded = TestClient(AccessGuard(app, token=token, allowed_origins=[]))
    assert guarded.post("/state/agents/harness/control", json=STOP).status_code == 401
    assert guarded.post("/state/agents/harness/control/claim", json={"command_id": str(uuid.uuid4())}).status_code == 401
    assert guarded.get("/state/agents/harness/control").status_code == 200
    assert run(store.history(None)) == []
    assert guarded.post("/state/agents/harness/control", json=STOP, headers={TOKEN_HEADER: token}).status_code == 200
