"""What the agent harness kill switch means, as pure functions: the refusal, the host's progress, and whether reality agrees.

They read the control row (``harness_control_store``), the Hermes heartbeat (``hermes_link.status_now``)
and when the host control process last checked in, so every case is tested without a database, a
gateway or WSL. Times in sentences are UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

POLL_INTERVAL_S = 10
# The host control process polls every ten seconds; a request still unclaimed after this long is flagged.
HOST_SILENT_S = 60
# `hermes gateway stop` waits 90 s for systemd, systemd gives the gateway 210 s to drain (TimeoutStopSec),
# and the host checks `is-active` for up to 240 s after the command returns.
APPLYING_LIMIT_S = 420
# The heartbeat runs every 15 s; a started gateway that has not answered after this long is flagged.
START_GRACE_S = 90
ANSWERING = frozenset({"live", "degraded"})

MISSING_TEXT = "The agent harness switch is missing (is migration 034 applied?), so TradeSync does not call Hermes."
NOTE = (
    "A stop applies to TradeSync at once: every TradeSync call to Hermes is refused from the next call. The host control "
    "process (Task Scheduler task TradeSync-Hermes-Harness-Control) then stops the Hermes gateway itself, which pauses every "
    "Hermes cron job and the Discord bots until it is started again. The heartbeat keeps running, so a gateway that still "
    "answers is visible. The ChaseOS coordination daemon is separate and is never controlled here."
)


def unreadable_text(kind: str) -> str:
    return f"The agent harness switch could not be read ({kind}), so TradeSync does not call Hermes."


def parse(value: Any) -> datetime | None:
    """A timezone-aware datetime from a datetime or an ISO string; None for anything else."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso(value: Any) -> str | None:
    parsed = parse(value)
    return parsed.astimezone(timezone.utc).isoformat() if parsed else None


def stamp(value: Any) -> str:
    parsed = parse(value)
    return f"{parsed.astimezone(timezone.utc):%Y-%m-%d %H:%M:%S} UTC" if parsed else "an unrecorded time"


def span(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total} s"
    if total < 3600:
        return f"{total // 60} min"
    return f"{total // 3600} h {total % 3600 // 60} min"


def refusal_text(row: Mapping[str, Any] | None) -> str | None:
    """Why TradeSync must not call Hermes, or None while the harness is running."""
    if row is None:
        return MISSING_TEXT
    if row["desired_state"] != "stopped":
        return None
    reason = str(row["reason"]).strip().rstrip(".")
    return (f"The agent harness was stopped by {row['operator']} at {stamp(row['requested_at'])} ({reason}). "
            "TradeSync does not call Hermes until it is started again.")


def host_status(row: Mapping[str, Any]) -> str:
    """For the current command: none (nothing asked yet), pending, applying, applied or failed."""
    command = row.get("command_id")
    if command is None:
        return "none"
    if row.get("result_command_id") == command:
        return str(row["result_status"])
    return "applying" if row.get("claimed_command_id") == command else "pending"


def host_view(row: Mapping[str, Any], last_poll_at: datetime | None, now: datetime) -> dict[str, Any]:
    status = host_status(row)
    result = None
    if row.get("result_command_id") is not None:
        result = {
            "command_id": str(row["result_command_id"]), "status": row["result_status"], "command": row.get("result_command"),
            "exit_status": row.get("result_exit_status"), "is_active": row.get("result_is_active"),
            "detail": row.get("result_detail"), "at": iso(row.get("result_at")),
            "for_current_command": row["result_command_id"] == row.get("command_id"),
        }
    claimed = status != "pending" and row.get("claimed_command_id") is not None and row.get("claimed_command_id") == row.get("command_id")
    polled = parse(last_poll_at)
    return {
        "status": status,
        "command_id": str(row["command_id"]) if row.get("command_id") is not None else None,
        "claimed_at": iso(row.get("claimed_at")) if claimed else None,
        "result": result,
        "last_poll_at": iso(polled),
        "seconds_since_poll": round((now - polled).total_seconds(), 1) if polled else None,
        "poll_interval_s": POLL_INTERVAL_S,
    }


def desired_view(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"state": row["desired_state"], "operator": row["operator"], "reason": row["reason"],
            "requested_at": iso(row["requested_at"]),
            "command_id": str(row["command_id"]) if row.get("command_id") is not None else None}


def gateway_view(link: Mapping[str, Any]) -> dict[str, Any]:
    return {key: link.get(key) for key in ("status", "last_seen_at", "seconds_since_seen", "last_error", "consecutive_failures")}


def event_view(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(event["id"]), "created_at": iso(event["created_at"]), "kind": event["kind"],
        "command_id": str(event["command_id"]), "desired_state": event["desired_state"],
        "previous_state": event.get("previous_state"), "operator": event.get("operator"), "reason": event.get("reason"),
        "command": event.get("command"), "exit_status": event.get("exit_status"), "is_active": event.get("is_active"),
        "detail": event.get("detail"),
    }


def agreement(row: Mapping[str, Any], link: Mapping[str, Any], host: Mapping[str, Any], now: datetime) -> dict[str, str]:
    """Whether what was asked for is what is happening: agree, pending, disagree or unknown, with one sentence."""
    status = host["status"]
    if status == "pending":
        return _waiting(row, host, now)
    if status == "applying":
        return _applying(row, host, now)
    if status == "failed":
        return _failed(row, host)
    if row["desired_state"] == "stopped":
        return _stopped(host, link)
    return _running(host, link, now)


def _verdict(state: str, message: str) -> dict[str, str]:
    return {"state": state, "message": message}


def _waiting(row: Mapping[str, Any], host: Mapping[str, Any], now: datetime) -> dict[str, str]:
    verb = "Stop" if row["desired_state"] == "stopped" else "Start"
    requested = parse(row["requested_at"]) or now
    waited = (now - requested).total_seconds()
    if waited <= HOST_SILENT_S:
        return _verdict("pending", f"{verb} requested at {stamp(requested)}; waiting for the host control process to apply it.")
    polled = host.get("seconds_since_poll")
    checked = f"it last checked in {span(polled)} ago" if polled is not None else "it has not checked in since the State API started"
    return _verdict("disagree", f"{verb} was requested at {stamp(requested)}, {span(waited)} ago, and the host control process has "
                                f"not picked it up ({checked}). Check that the TradeSync-Hermes-Harness-Control task is running.")


def _applying(row: Mapping[str, Any], host: Mapping[str, Any], now: datetime) -> dict[str, str]:
    stopping = row["desired_state"] == "stopped"
    doing = "Stopping" if stopping else "Starting"
    began = parse(host.get("claimed_at")) or now
    waited = (now - began).total_seconds()
    if waited <= APPLYING_LIMIT_S:
        drain = " The gateway finishes in-flight work before it exits; systemd allows it 210 s." if stopping else ""
        return _verdict("pending", f"{doing}: the host control process began at {stamp(began)}.{drain}")
    return _verdict("disagree", f"{doing} began at {stamp(began)}, {span(waited)} ago, and no result has been reported. "
                                "See dashboard-runtime\\logs\\hermes_harness_control.log on this PC.")


def _failed(row: Mapping[str, Any], host: Mapping[str, Any]) -> dict[str, str]:
    stopping = row["desired_state"] == "stopped"
    result = host.get("result") or {}
    held = " TradeSync's own calls to Hermes stay refused." if stopping else ""
    return _verdict("disagree", f"{'Stop' if stopping else 'Start'} failed at {stamp(result.get('at'))}: "
                                f"{result.get('detail') or 'no detail was reported'} (systemd reports "
                                f"{result.get('is_active') or 'unknown'}).{held}")


def _stopped(host: Mapping[str, Any], link: Mapping[str, Any]) -> dict[str, str]:
    result = host.get("result") or {}
    applied = parse(result.get("at"))
    seen = parse(link.get("last_seen_at"))
    systemd = result.get("is_active") or "unknown"
    if link.get("status") == "not_configured":
        return _verdict("agree", f"Stopped at {stamp(applied)} (systemd reports {systemd}); TradeSync has no heartbeat on the "
                                 "gateway to confirm it.")
    if seen and applied and seen > applied:
        return _verdict("disagree", f"Stopped at {stamp(applied)}, but the gateway answered at {stamp(seen)}. Something started it "
                                    "again (a Windows logon runs Hermes Gateway.vbs, and a WSL restart starts the enabled service). "
                                    "Stop it again.")
    return _verdict("agree", f"Stopped at {stamp(applied)} (systemd reports {systemd}); the gateway has not answered since.")


def _running(host: Mapping[str, Any], link: Mapping[str, Any], now: datetime) -> dict[str, str]:
    result = host.get("result") if host["status"] == "applied" else None
    started = parse(result.get("at")) if result else None
    status, seen = link.get("status"), parse(link.get("last_seen_at"))
    if status == "not_configured":
        return _verdict("unknown", "Running. TradeSync has no heartbeat on the gateway: AGENT_HARNESS_URL is unset.")
    if status in ANSWERING and (started is None or (seen is not None and seen >= started)):
        return _verdict("agree", f"Started at {stamp(started)}; the gateway answers." if started else "Running; the gateway answers.")
    if status == "checking":
        return _verdict("unknown", "Running is requested; waiting for the gateway's first heartbeat.")
    if started and (now - started).total_seconds() <= START_GRACE_S:
        return _verdict("pending", f"Started at {stamp(started)}; waiting for the gateway's first heartbeat.")
    since = f"since {stamp(seen)}" if seen else "since the State API started"
    cause = (f" It was started at {stamp(started)} (systemd reported {result.get('is_active') or 'unknown'})."
             if started and result else " Nothing in TradeSync stopped it.")
    return _verdict("disagree", f"Running is requested, but the gateway has not answered {since}.{cause} Start again runs its service.")
