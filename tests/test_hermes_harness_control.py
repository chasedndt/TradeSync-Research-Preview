"""The host control process applies each switch command once. Every test uses a fake runner; none runs wsl.exe."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_module_by_path  # noqa: E402

control = load_module_by_path("hermes_harness_control_tool", "tools/hermes_harness_control.py")
gateway = control.gateway
ROOT = Path(__file__).resolve().parents[1]
CID = "0d2a6a6e-7d2e-4f7a-9a55-1c8f1b8a4e01"


@pytest.fixture(autouse=True)
def _no_runtime_env(monkeypatch, tmp_path):
    # Never the operator's runtime.env: the token helper must find nothing to send.
    monkeypatch.delenv("STATE_API_OPERATOR_TOKEN", raising=False)
    monkeypatch.setenv("TRADESYNC_RUNTIME_ENV", str(tmp_path / "no-runtime.env"))


@pytest.fixture
def host_state(tmp_path):
    return control.HostState(tmp_path / "harness-control-state.json")


def no_sleep(seconds: float) -> None:
    return None


def command(desired="stopped", status="pending", command_id=CID):
    return {"id": command_id, "desired_state": desired, "status": status, "requested_at": "2026-09-15T18:20:00+00:00",
            "operator": "chase"}


class FakeRunner:
    """Answers each WSL command by what it asks and records it; anything unexpected fails the test."""

    def __init__(self, *, running=True, stop=None, start=None, wake=None, states=("inactive",)):
        self.running = running
        self.answers = {"stop": stop or gateway.Completed(0, "✓ Stopped hermes-gateway service\n"),
                        "start": start or gateway.Completed(0), "wake": wake or gateway.Completed(0)}
        self.states = list(states)
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout):
        argv = list(argv)
        self.calls.append(argv)
        if argv == gateway.running_argv():
            if isinstance(self.running, BaseException):
                raise self.running
            return gateway.Completed(0, "Ubuntu\ndocker-desktop\n" if self.running else "docker-desktop\n")
        if argv == gateway.is_active_argv():
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return gateway.Completed(0 if state == "active" else 3, f"{state}\n")
        for key, expected in (("stop", gateway.stop_argv()), ("start", gateway.start_argv()), ("wake", gateway.wake_argv())):
            if argv == expected:
                answer = self.answers[key]
                if isinstance(answer, BaseException):
                    raise answer
                return answer
        raise AssertionError(f"unexpected command {argv}")

    def ran(self, key: str) -> int:
        expected = {"stop": gateway.stop_argv(), "start": gateway.start_argv(), "wake": gateway.wake_argv()}[key]
        return sum(1 for call in self.calls if call == expected)


class Response:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code, self._body = status, body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise control.httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=None)


class FakeStateApi:
    """state-api's switch routes as the host sees them, holding the one command a test queued."""

    def __init__(self, queued=None, *, report_failures=0, claim_status=200):
        self.command = queued
        self.claims: list[str] = []
        self.reports: list[dict] = []
        self.report_failures, self.claim_status = report_failures, claim_status

    def get(self, url, **kwargs):
        assert url.endswith("/state/agents/harness/control/command"), url
        return Response(200, {"command": self.command, "poll_interval_s": 10})

    def post(self, url, json=None, **kwargs):
        if url.endswith("/claim"):
            self.claims.append(json["command_id"])
            if self.claim_status == 200 and self.command:
                self.command = {**self.command, "status": "applying"}
            return Response(self.claim_status, {"claimed": True} if self.claim_status == 200 else {"detail": "superseded"})
        if url.endswith("/report"):
            if self.report_failures:
                self.report_failures -= 1
                raise control.httpx.ConnectError("state-api is restarting")
            self.reports.append(json)
            if self.command and self.command["id"] == json["command_id"]:
                self.command = None  # a command with a result is no longer handed out
            return Response(200, {"recorded": True})
        raise AssertionError(url)


def test_a_stop_runs_hermes_gateway_stop_once_and_reports_what_systemd_says(host_state) -> None:
    api, run = FakeStateApi(command("stopped")), FakeRunner(states=("inactive",))
    assert control.run_pass(api, host_state, run, no_sleep) == "applied"
    assert api.claims == [CID] and run.ran("stop") == 1 and run.ran("start") == 0
    [report] = api.reports
    assert (report["command_id"], report["status"], report["exit_status"], report["is_active"]) == (CID, "applied", 0, "inactive")
    assert report["command"] == ("wsl.exe -d Ubuntu --cd /home/operator/runtimes/hermes-home -- env "
                                 "HERMES_HOME=/home/operator/runtimes/hermes-home "
                                 "/home/operator/runtimes/hermes-home/hermes-agent/venv/bin/hermes gateway stop")
    assert report["detail"].startswith("the gateway is stopped") and "Stopped hermes-gateway service" in report["detail"]
    assert control.run_pass(api, host_state, run, no_sleep) == "idle" and run.ran("stop") == 1


def test_a_start_runs_the_service_as_the_logon_script_does_and_waits_for_it_to_be_active(host_state) -> None:
    api, run = FakeStateApi(command("running")), FakeRunner(states=("activating", "active"))
    slept: list[float] = []
    assert control.run_pass(api, host_state, run, slept.append) == "applied"
    assert run.ran("start") == 1 and run.ran("stop") == 0 and run.ran("wake") == 0 and slept == [5.0]
    assert gateway.start_argv()[1:] == ["-d", "Ubuntu", "--", "systemctl", "--user", "start", "hermes-gateway.service"]
    [report] = api.reports
    assert report["status"] == "applied" and report["is_active"] == "active"
    assert report["command"] == "wsl.exe -d Ubuntu -- systemctl --user start hermes-gateway.service"


def test_stopping_while_wsl_is_down_starts_nothing(host_state) -> None:
    api, run = FakeStateApi(command("stopped")), FakeRunner(running=False)
    assert control.run_pass(api, host_state, run, no_sleep) == "applied"
    assert run.calls == [gateway.running_argv()]
    [report] = api.reports
    assert report["is_active"] == "not running" and report["exit_status"] is None and "WSL was not started" in report["detail"]


def test_starting_when_wsl_will_not_start_is_reported_failed_and_never_run_again(host_state) -> None:
    api = FakeStateApi(command("running"))
    run = FakeRunner(running=False, wake=gateway.Completed(4294967295, "", "Wsl/Service/E_UNEXPECTED\n"))
    assert control.run_pass(api, host_state, run, no_sleep) == "failed"
    [report] = api.reports
    assert report["status"] == "failed" and "WSL did not start" in report["detail"] and "E_UNEXPECTED" in report["detail"]
    assert run.ran("start") == 0 and run.ran("wake") == 1
    api.command = command("running")  # handed out again, as if its result had not been recorded
    calls = len(run.calls)
    assert control.run_pass(api, host_state, run, no_sleep) == "handled"
    assert len(run.calls) == calls and api.claims == [CID] and len(api.reports) == 1


def test_when_wsl_exe_cannot_be_run_the_command_fails_with_the_reason(host_state) -> None:
    api = FakeStateApi(command("running"))
    run = FakeRunner(running=OSError("wsl.exe not found"), start=FileNotFoundError("wsl.exe not found"), states=("unknown",))
    assert control.run_pass(api, host_state, run, no_sleep) == "failed"
    assert "wsl.exe could not be run (FileNotFoundError" in api.reports[0]["detail"]


def test_an_undelivered_report_is_sent_on_the_next_poll_without_running_the_command_again(host_state) -> None:
    api, run = FakeStateApi(command("stopped"), report_failures=1), FakeRunner(states=("inactive",))
    with pytest.raises(control.httpx.ConnectError):
        control.run_pass(api, host_state, run, no_sleep)
    assert run.ran("stop") == 1 and api.reports == []
    assert control.run_pass(api, control.HostState(host_state.path), run, no_sleep) == "idle"
    assert run.ran("stop") == 1 and [r["status"] for r in api.reports] == ["applied"]


def test_a_command_begun_before_a_restart_is_reported_failed_and_not_run_again(tmp_path) -> None:
    path = tmp_path / "state.json"
    control.HostState(path).begin(command("stopped"))  # the process died here, mid-command
    api, run = FakeStateApi(command("stopped", status="applying")), FakeRunner(states=("deactivating",))
    assert control.run_pass(api, control.HostState(path), run, no_sleep) == "idle"
    assert run.ran("stop") == 0 and api.claims == []
    [report] = api.reports
    assert report["status"] == "failed" and "not run again" in report["detail"] and report["is_active"] == "deactivating"


def test_a_command_already_being_applied_with_no_record_here_is_not_run(host_state) -> None:
    api, run = FakeStateApi(command("stopped", status="applying")), FakeRunner(states=("active",))
    assert control.run_pass(api, host_state, run, no_sleep) == "not run again"
    assert api.claims == [] and run.ran("stop") == 0
    [report] = api.reports
    assert report["status"] == "failed" and "it was not run again" in report["detail"] and report["is_active"] == "active"


def test_a_refused_claim_runs_nothing(host_state) -> None:
    api, run = FakeStateApi(command("stopped"), claim_status=409), FakeRunner()
    assert control.run_pass(api, host_state, run, no_sleep) == "not claimed"
    assert run.calls == [] and api.reports == []


def test_a_slow_drain_is_waited_for_and_a_gateway_still_active_after_a_stop_is_a_failure(tmp_path) -> None:
    api = FakeStateApi(command("stopped"))
    slow = FakeRunner(stop=TimeoutError("did not finish"), states=("deactivating", "deactivating", "inactive"))
    slept: list[float] = []
    assert control.run_pass(api, control.HostState(tmp_path / "a.json"), slow, slept.append) == "applied"
    assert slept == [5.0, 5.0] and "did not return within 150 s" in api.reports[0]["detail"] and api.reports[0]["exit_status"] is None
    stubborn_api = FakeStateApi(command("stopped", command_id="5b0b4f6c-6f55-4a86-8f1e-5d3c1a7e9f02"))
    assert control.run_pass(stubborn_api, control.HostState(tmp_path / "b.json"), FakeRunner(states=("active",)), no_sleep) == "failed"
    assert stubborn_api.reports[0]["detail"].startswith("the gateway is still active after hermes gateway stop")


def test_a_quiet_poll_touches_no_wsl_and_failures_back_off_to_a_minute(host_state) -> None:
    run = FakeRunner()
    assert control.run_pass(FakeStateApi(None), host_state, run, no_sleep) == "idle" and run.calls == []
    assert [control.backoff(n) for n in (0, 1, 2, 3, 9)] == [10.0, 20.0, 40.0, 60.0, 60.0]


def test_the_real_runner_hides_its_window_decodes_wsl_output_and_raises_timeouterror(monkeypatch) -> None:
    seen: dict = {}

    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, "Ubuntu\r\ndocker-desktop\r\n".encode("utf-16-le"), b"")

    def slow_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    monkeypatch.setattr(gateway, "subprocess", SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired,
                                                               CREATE_NO_WINDOW=no_window))
    done = gateway.run_command(gateway.running_argv(), 5)
    assert done.stdout.split() == ["Ubuntu", "docker-desktop"] and seen["capture_output"] is True and seen["timeout"] == 5
    assert seen["creationflags"] == no_window
    monkeypatch.setattr(gateway, "subprocess", SimpleNamespace(run=slow_run, TimeoutExpired=subprocess.TimeoutExpired,
                                                               CREATE_NO_WINDOW=no_window))
    with pytest.raises(TimeoutError):
        gateway.run_command(gateway.is_active_argv(), 1)


def test_wsl_and_systemd_answers_are_read_without_starting_the_distro() -> None:
    def broken(argv, timeout):
        raise OSError("wsl.exe not found")

    assert gateway.distro_running(lambda argv, timeout: gateway.Completed(4294967295, "There are no running distributions.\n")) is False
    assert gateway.distro_running(broken) is None
    assert gateway.is_active(lambda argv, timeout: gateway.Completed(3, "failed\n")) == "failed"
    assert gateway.is_active(lambda argv, timeout: gateway.Completed(1, "", "Wsl/Service/E_UNEXPECTED")) == "unknown"
    assert gateway.observe(lambda argv, timeout: gateway.Completed(0, "docker-desktop\n")) == "not running"
    assert gateway.apply("paused", broken, no_sleep).status == "failed"


def test_check_mode_reads_wsl_and_the_switch_and_changes_nothing(monkeypatch, capsys) -> None:
    posted: list = []

    class Client:
        def __init__(self, *args, headers=None, **kwargs):
            assert headers == {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url, **kwargs):
            assert url.endswith("/state/agents/harness/control")
            return Response(200, {"desired": {"state": "running", "operator": "migration 034", "requested_at": "2026-09-15T18:00:00+00:00"},
                                  "host": {"status": "none"}, "agreement": {"state": "agree", "message": "Running; the gateway answers."}})

        def post(self, *args, **kwargs):
            posted.append(args)

    monkeypatch.setattr(control.httpx, "Client", Client)
    run = FakeRunner(states=("active",))
    assert control.check(run) == 0
    out = capsys.readouterr().out
    assert "WSL distro Ubuntu: running" in out and "hermes-gateway.service: active" in out and "switch: running" in out
    assert posted == [] and run.ran("stop") == run.ran("start") == run.ran("wake") == 0


@pytest.mark.skipif(shutil.which("powershell") is None, reason="Windows PowerShell parses the registration script")
def test_the_registration_script_parses_and_registers_the_logon_task_only_when_run() -> None:
    script = ROOT / "tools" / "register-hermes-harness-control-task.ps1"
    parse = (f"$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$errors)"
             " | Out-Null; $errors.Count")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", parse], capture_output=True, text=True, timeout=120)
    assert result.stdout.strip() == "0", result.stdout + result.stderr
    body = script.read_text(encoding="utf-8").split("#>", 1)[1]
    assert "Register-ScheduledTask" in body and "pythonw.exe" in body and "-AtLogOn" in body and "-RestartCount" in body
    assert "Start-ScheduledTask" not in body and "Stop-ScheduledTask" not in body
