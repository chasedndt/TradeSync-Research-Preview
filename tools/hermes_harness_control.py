"""Apply the agent harness kill switch on this PC: poll state-api, stop or start the Hermes gateway, report what happened.

Runs on the Windows host from logon (Task Scheduler, pythonw; see
tools/register-hermes-harness-control-task.ps1). About every ten seconds it reads
``GET /state/agents/harness/control/command``. A command this host has not handled is claimed
(``POST .../claim``) before anything runs, applied by ``hermes_gateway_control``, and reported
(``POST .../report``) with the command, its exit status and ``systemctl --user is-active``.

A command runs at most once. Its id is written to the state file before it runs; a command that
state-api already shows as being applied, with no record of it here, is reported failed and not
run; and a report that could not be delivered is sent again on later polls without running
anything. Errors back off to a minute, so nothing is retried in a tight loop, and WSL is asked
nothing unless a command is being applied.

Only the WSL messaging gateway is controlled. The ChaseOS coordination daemon
(``%USERPROFILE%\\.hermes\\hermes-daemon-loop.cmd``) is separate, is controlled by ChaseOS Studio or
Task Scheduler, and is never touched here.

Usage (from the repo root, with the project venv):
    pythonw tools/hermes_harness_control.py          # the logon task: poll until stopped
    python tools/hermes_harness_control.py --check   # read-only: WSL, the gateway unit and the switch
    python tools/hermes_harness_control.py --once    # one poll, which applies a pending command
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Under pythonw.exe (no console window) there is no stdout; log to a file instead.
if sys.stdout is None or sys.stderr is None:
    _log = Path(os.getenv("TRADESYNC_LOG_DIR", r"E:\Projects\TradeSync\dashboard-runtime\logs")) / "hermes_harness_control.log"
    _log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_log, "a", encoding="utf-8", buffering=1)

import httpx  # noqa: E402

TOOLS = Path(__file__).resolve().parent
sys.path[:0] = [str(TOOLS), str(TOOLS.parent / "libs" / "tradesync_core")]
import hermes_gateway_control as gateway  # noqa: E402
from tradesync_core.job_errors import redact  # noqa: E402
from tradesync_core.state_api_access import HOST_STATE_API_URL, host_operator_headers  # noqa: E402

STATE_API = os.getenv("STATE_API_URL", HOST_STATE_API_URL).rstrip("/")
STATE_FILE = Path(os.getenv("HERMES_HARNESS_CONTROL_STATE", r"E:\Projects\TradeSync\dashboard-runtime\hermes-harness-control-state.json"))
CONTROL = "/state/agents/harness/control"
POLL_S = 10.0
MAX_BACKOFF_S = 60.0
KEEP = 20
NOT_RERUN = ("state-api shows this command already being applied, but this host has no record of running it (the host "
             "control process restarted mid-command, or its state file was lost); it was not run again")
INTERRUPTED = "the host control process stopped while applying this command; it was not run again"


def log(message: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC [HarnessControl] {message}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def backoff(failures: int, interval: float = POLL_S) -> float:
    """Seconds before the next poll: the interval, doubled for each failure in a row, never over a minute."""
    return interval if failures <= 0 else min(MAX_BACKOFF_S, interval * 2 ** failures)


class HostState:
    """The commands this host has handled, kept on disk so that no command runs twice, even across restarts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries = self._load()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        entries = data.get("handled") if isinstance(data, dict) else None
        return [e for e in entries if isinstance(e, dict) and e.get("command_id")] if isinstance(entries, list) else []

    def _save(self) -> None:
        while len(self.entries) > KEEP and any(e.get("reported") for e in self.entries):
            self.entries.remove(next(e for e in self.entries if e.get("reported")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"handled": self.entries}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def find(self, command_id: str) -> dict | None:
        return next((e for e in self.entries if e["command_id"] == command_id), None)

    def begin(self, command: dict) -> None:
        self.entries.append({"command_id": str(command["id"]), "desired_state": command["desired_state"], "phase": "running",
                             "begun_at": now_iso(), "result": None, "reported": False})
        self._save()

    def finish(self, command_id: str, result: dict) -> None:
        self.find(command_id).update(phase="finished", result=result, finished_at=now_iso())
        self._save()

    def record_unrun(self, command: dict, result: dict) -> None:
        self.entries.append({"command_id": str(command["id"]), "desired_state": command["desired_state"], "phase": "finished",
                             "begun_at": None, "result": result, "reported": False, "finished_at": now_iso()})
        self._save()

    def interrupted(self) -> list[dict]:
        return [e for e in self.entries if e.get("phase") == "running"]

    def unreported(self) -> list[dict]:
        return [e for e in self.entries if e.get("phase") == "finished" and not e.get("reported")]

    def mark_reported(self, command_id: str) -> None:
        self.find(command_id)["reported"] = True
        self._save()


def _detail(response) -> str:
    try:
        return str(response.json().get("detail"))
    except (ValueError, AttributeError):
        return f"HTTP {response.status_code}"


def deliver(client, state: HostState) -> None:
    """Send every result state-api has not recorded yet; a failure leaves it for the next poll."""
    for entry in state.unreported():
        result = {**entry["result"], "detail": redact(entry["result"].get("detail"), limit=600) or ""}
        response = client.post(f"{STATE_API}{CONTROL}/report", json={"command_id": entry["command_id"], **result})
        if response.status_code == 404:
            log(f"state-api does not know command {entry['command_id']}; its result stays in the state file only")
        else:
            response.raise_for_status()
            log(f"reported {entry['command_id']}: {result['status']} (is-active {result['is_active']})")
        state.mark_reported(entry["command_id"])


def run_pass(client, state: HostState, run=gateway.run_command, sleep=time.sleep) -> str:
    """One poll; returns what happened."""
    for entry in state.interrupted():
        state.finish(entry["command_id"], gateway.Result("failed", "(interrupted)", None, gateway.observe(run), INTERRUPTED).report())
    deliver(client, state)
    response = client.get(f"{STATE_API}{CONTROL}/command")
    response.raise_for_status()
    command = response.json().get("command")
    if not command:
        return "idle"
    command_id = str(command["id"])
    if state.find(command_id):
        return "handled"
    if command.get("status") == "applying":
        state.record_unrun(command, gateway.Result("failed", "(not run)", None, gateway.observe(run), NOT_RERUN).report())
        deliver(client, state)
        return "not run again"
    claim = client.post(f"{STATE_API}{CONTROL}/claim", json={"command_id": command_id})
    if claim.status_code in (404, 409):
        log(f"not running {command_id}: {_detail(claim)}")
        return "not claimed"
    claim.raise_for_status()
    state.begin(command)
    log(f"applying {command_id}: {command['desired_state']}, requested by {command.get('operator')}")
    result = gateway.apply(command["desired_state"], run, sleep)
    state.finish(command_id, result.report())
    log(f"{result.status} {command_id}: {result.command} (exit {result.exit_status}, is-active {result.is_active})")
    deliver(client, state)
    return result.status


def poll_once(state: HostState) -> str:
    with httpx.Client(timeout=30.0, trust_env=False, headers=host_operator_headers()) as client:
        return run_pass(client, state)


def check(run=gateway.run_command) -> int:
    """Read-only: whether WSL is up, what systemd says, and what the switch in state-api says. Runs nothing."""
    up = gateway.distro_running(run)
    print(f"WSL distro {gateway.DISTRO}: {'running' if up else 'not running' if up is False else 'unknown'}")
    if up:
        print(f"{gateway.SERVICE}: {gateway.is_active(run)}")
    with httpx.Client(timeout=15.0, trust_env=False, headers=host_operator_headers()) as client:
        try:
            response = client.get(f"{STATE_API}{CONTROL}")
        except httpx.HTTPError as exc:
            print(f"state-api: not reachable ({type(exc).__name__})")
            return 1
    if response.status_code != 200:
        print(f"state-api: HTTP {response.status_code} for {CONTROL}")
        return 1
    body = response.json()
    desired = body["desired"]
    print(f"switch: {desired['state']} (requested by {desired['operator']} at {desired['requested_at']})")
    print(f"host: {body['host']['status']}; {body['agreement']['state']}: {body['agreement']['message']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="read-only status; runs nothing")
    parser.add_argument("--once", action="store_true", help="one poll; applies a pending command")
    parser.add_argument("--interval", type=float, default=POLL_S)
    args = parser.parse_args(argv)
    if args.check:
        return check()
    state = HostState(STATE_FILE)
    if args.once:
        log(poll_once(state))
        return 0
    log(f"started; polling {STATE_API} every {args.interval:.0f} s")
    failures = 0
    while True:
        try:
            outcome = poll_once(state)
            if failures:
                log(f"state-api answering again after {failures} failed polls")
            failures = 0
            if outcome not in ("idle", "handled"):
                log(outcome)
        except Exception as exc:  # the loop outlives any one failure; nothing is run again on the next poll
            failures += 1
            if failures == 1 or failures % 30 == 0:
                log(f"poll failed ({failures} in a row): {type(exc).__name__}: {exc}")
        time.sleep(backoff(failures, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
