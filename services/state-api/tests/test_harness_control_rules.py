"""What the switch means: the refusal TradeSync's callers give, the host's progress, and whether the gateway agrees."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app import harness_control_rules as rules

NOW = datetime(2026, 9, 15, 18, 30, tzinfo=timezone.utc)
COMMAND = uuid.uuid4()


def control(**fields):
    base = {"desired_state": "running", "operator": "migration 034", "reason": "Installed", "requested_at": NOW - timedelta(days=1),
            "command_id": None, "claimed_command_id": None, "claimed_at": None, "result_command_id": None, "result_status": None,
            "result_command": None, "result_exit_status": None, "result_is_active": None, "result_detail": None, "result_at": None}
    return {**base, **fields}


def requested(desired, ago_s=20, **fields):
    return control(desired_state=desired, operator="chase", reason="Hermes compute needed for a backtest.",
                   requested_at=NOW - timedelta(seconds=ago_s), command_id=COMMAND, **fields)


def applied(desired, at_ago_s, status="applied", is_active="inactive", detail="the gateway is stopped"):
    return requested(desired, ago_s=at_ago_s + 30, claimed_command_id=COMMAND, claimed_at=NOW - timedelta(seconds=at_ago_s + 20),
                     result_command_id=COMMAND, result_status=status, result_command="hermes gateway stop", result_exit_status=0,
                     result_is_active=is_active, result_detail=detail, result_at=NOW - timedelta(seconds=at_ago_s))


def link(status="live", seen_ago_s=None):
    seen = (NOW - timedelta(seconds=seen_ago_s)).isoformat() if seen_ago_s is not None else None
    return {"status": status, "last_seen_at": seen, "seconds_since_seen": seen_ago_s, "last_error": None, "consecutive_failures": 0}


def agreement(row, gateway, last_poll=None):
    return rules.agreement(row, gateway, rules.host_view(row, last_poll, NOW), NOW)


def test_running_refuses_nothing_and_stopped_names_who_when_and_why() -> None:
    assert rules.refusal_text(control()) is None
    assert rules.refusal_text(requested("stopped")) == (
        "The agent harness was stopped by chase at 2026-09-15 18:29:40 UTC (Hermes compute needed for a backtest). "
        "TradeSync does not call Hermes until it is started again.")
    assert rules.refusal_text(None) == rules.MISSING_TEXT and "migration 034" in rules.MISSING_TEXT
    assert rules.unreadable_text("ConnectionError") == (
        "The agent harness switch could not be read (ConnectionError), so TradeSync does not call Hermes.")


def test_the_host_status_follows_the_current_command_only() -> None:
    assert rules.host_status(control()) == "none"
    assert rules.host_status(requested("stopped")) == "pending"
    assert rules.host_status(requested("stopped", claimed_command_id=COMMAND, claimed_at=NOW)) == "applying"
    assert rules.host_status(applied("stopped", 5)) == "applied"
    assert rules.host_status(applied("stopped", 5, status="failed")) == "failed"
    older = uuid.uuid4()
    newer = requested("running", claimed_command_id=older, claimed_at=NOW, result_command_id=older, result_status="applied",
                      result_at=NOW)
    view = rules.host_view(newer, NOW - timedelta(seconds=4), NOW)
    assert view["status"] == "pending" and view["claimed_at"] is None and view["result"]["for_current_command"] is False
    assert view["seconds_since_poll"] == 4.0 and view["poll_interval_s"] == 10


def test_a_request_waits_for_the_host_and_is_flagged_when_the_host_is_silent() -> None:
    assert agreement(requested("stopped", ago_s=20), link())["state"] == "pending"
    silent = agreement(requested("stopped", ago_s=300), link())
    assert silent["state"] == "disagree" and "5 min ago" in silent["message"]
    assert "has not checked in since the State API started" in silent["message"]
    assert "TradeSync-Hermes-Harness-Control" in silent["message"]
    polled = agreement(requested("running", ago_s=300), link(), last_poll=NOW - timedelta(seconds=7))
    assert polled["message"].startswith("Start was requested") and "last checked in 7 s ago" in polled["message"]


def test_applying_is_pending_through_the_drain_and_flagged_after_it() -> None:
    draining = requested("stopped", ago_s=100, claimed_command_id=COMMAND, claimed_at=NOW - timedelta(seconds=90))
    verdict = agreement(draining, link())
    assert verdict["state"] == "pending" and verdict["message"].startswith("Stopping") and "210 s" in verdict["message"]
    stuck = requested("stopped", ago_s=900, claimed_command_id=COMMAND, claimed_at=NOW - timedelta(seconds=800))
    verdict = agreement(stuck, link())
    assert verdict["state"] == "disagree" and "hermes_harness_control.log" in verdict["message"]


def test_a_stop_agrees_until_the_gateway_answers_again() -> None:
    assert agreement(applied("stopped", 60), link("offline", seen_ago_s=75)) == {
        "state": "agree",
        "message": "Stopped at 2026-09-15 18:29:00 UTC (systemd reports inactive); the gateway has not answered since.",
    }
    back = agreement(applied("stopped", 600), link("live", seen_ago_s=10))
    assert back["state"] == "disagree" and "answered at 2026-09-15 18:29:50 UTC" in back["message"]
    assert "Hermes Gateway.vbs" in back["message"] and back["message"].endswith("Stop it again.")
    assert agreement(applied("stopped", 60), link("not_configured"))["state"] == "agree"


def test_a_failed_command_is_a_disagreement_with_its_reason() -> None:
    failed = agreement(applied("stopped", 30, status="failed", is_active="active",
                               detail="the gateway is still active after hermes gateway stop"), link())
    assert failed == {"state": "disagree", "message": (
        "Stop failed at 2026-09-15 18:29:30 UTC: the gateway is still active after hermes gateway stop "
        "(systemd reports active). TradeSync's own calls to Hermes stay refused.")}
    start_failed = agreement(applied("running", 30, status="failed", is_active="failed", detail="WSL did not start"), link("offline"))
    assert start_failed["message"].startswith("Start failed at") and "stay refused" not in start_failed["message"]


def test_running_agrees_while_the_gateway_answers_and_says_so_when_it_does_not() -> None:
    assert agreement(control(), link("live", seen_ago_s=5)) == {"state": "agree", "message": "Running; the gateway answers."}
    down = agreement(control(), link("offline", seen_ago_s=5400))
    assert down["state"] == "disagree" and "has not answered since 2026-09-15 17:00:00 UTC" in down["message"]
    assert "Nothing in TradeSync stopped it." in down["message"]
    assert agreement(control(), link("not_configured"))["state"] == "unknown"
    assert agreement(control(), link("checking"))["state"] == "unknown"


def test_a_start_waits_for_the_first_heartbeat_then_agrees_or_is_flagged() -> None:
    fresh = applied("running", 20, is_active="active", detail="the gateway is running")
    assert agreement(fresh, link("offline", seen_ago_s=4000))["state"] == "pending"
    assert agreement(fresh, link("live", seen_ago_s=5))["message"] == "Started at 2026-09-15 18:29:40 UTC; the gateway answers."
    late = applied("running", 300, is_active="active", detail="the gateway is running")
    silent = agreement(late, link("offline", seen_ago_s=4000))
    assert silent["state"] == "disagree" and "It was started at 2026-09-15 18:25:00 UTC (systemd reported active)." in silent["message"]


def test_times_and_spans_read_plainly() -> None:
    assert rules.stamp("2026-09-15T18:20:05.5+00:00") == "2026-09-15 18:20:05 UTC" and rules.stamp(None) == "an unrecorded time"
    assert (rules.span(42), rules.span(600), rules.span(5400)) == ("42 s", "10 min", "1 h 30 min")
    assert rules.iso(datetime(2026, 9, 15, 18, 0)) == "2026-09-15T18:00:00+00:00" and rules.iso("not a time") is None
