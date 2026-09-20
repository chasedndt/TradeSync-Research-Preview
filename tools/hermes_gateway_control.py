"""Stop and start the Hermes gateway on this PC the way the operator's own commands do, and read what systemd says after.

Read from the Hermes CLI (``hermes_cli/gateway.py`` in ``~/runtimes/hermes-home/hermes-agent``) on
15 September 2026, with the systemd user unit installed:

- ``hermes gateway stop`` resolves the unit ``hermes-gateway`` for
  ``HERMES_HOME=/home/operator/runtimes/hermes-home``, writes the planned-stop marker
  (``.gateway-planned-stop.json``) naming the running gateway, then runs
  ``systemctl --user stop hermes-gateway`` and waits up to 90 s. With the marker the gateway treats
  SIGTERM as a deliberate stop: it finishes in-flight work (systemd allows ``TimeoutStopSec=210``),
  records ``gateway_state`` stopped and exits cleanly, so the unit ends ``inactive``. A bare
  ``systemctl --user stop`` sends the same SIGTERM without the marker; the gateway then exits 1, the
  unit ends ``failed`` and ``gateway_state`` still says running. Stopping therefore runs the
  operator's CLI itself (``~/.local/bin/hermes`` is ``hermes-agent/venv/bin/hermes``) with the unit's
  ``HERMES_HOME``, from the unit's working directory.
- ``hermes gateway start`` checks the user D-Bus session, rewrites the unit file when the definition
  it would generate differs from the installed one, then runs ``systemctl --user start
  hermes-gateway``. The generated definition takes its Windows ``PATH`` entries and ``node`` from the
  shell that runs it, so run from a hidden Windows task it could rewrite the operator's unit.
  Starting therefore runs ``systemctl --user start hermes-gateway.service``, exactly as the logon
  script ``%USERPROFILE%\\.hermes\\gateway.cmd`` does, and leaves the unit file alone.

No exit status decides the result on its own (the CLI answers 0 when it falls back or times out):
``systemctl --user is-active`` afterwards does. WSL is never started to stop the gateway, because a
distro that is not running has no gateway to stop. Nothing here touches the ChaseOS coordination
daemon (``%USERPROFILE%\\.hermes\\hermes-daemon-loop.cmd``).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Callable, Sequence

DISTRO = "Ubuntu"
HERMES_HOME = "/home/operator/runtimes/hermes-home"
HERMES_CLI = f"{HERMES_HOME}/hermes-agent/venv/bin/hermes"
SERVICE = "hermes-gateway.service"
WSL = shutil.which("wsl.exe") or r"C:\Windows\System32\wsl.exe"

STOP_TIMEOUT_S = 150.0  # the CLI waits 90 s for systemd, after its own start-up
START_TIMEOUT_S = 60.0
WAKE_TIMEOUT_S = 90.0
QUERY_TIMEOUT_S = 30.0
STOP_SETTLE_S = 240.0  # TimeoutStopSec=210, then ExecStopPost cleanup
START_SETTLE_S = 30.0
SETTLE_POLL_S = 5.0

STOPPED = frozenset({"inactive", "failed"})
SYSTEMD_STATES = frozenset({"active", "inactive", "failed", "activating", "deactivating", "reloading", "refreshing", "maintenance"})
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str], float], Completed]
Sleep = Callable[[float], None]


@dataclass(frozen=True)
class Result:
    status: str  # applied or failed
    command: str
    exit_status: int | None
    is_active: str
    detail: str

    def report(self) -> dict:
        return asdict(self)


def stop_argv() -> list[str]:
    return [WSL, "-d", DISTRO, "--cd", HERMES_HOME, "--", "env", f"HERMES_HOME={HERMES_HOME}", HERMES_CLI, "gateway", "stop"]


def start_argv() -> list[str]:
    return [WSL, "-d", DISTRO, "--", "systemctl", "--user", "start", SERVICE]


def is_active_argv() -> list[str]:
    return [WSL, "-d", DISTRO, "--", "systemctl", "--user", "is-active", SERVICE]


def running_argv() -> list[str]:
    return [WSL, "--list", "--running", "--quiet"]


def wake_argv() -> list[str]:
    return [WSL, "-d", DISTRO, "--exec", "/bin/true"]


def shown(argv: Sequence[str]) -> str:
    """The command as recorded: wsl.exe by name rather than by its full Windows path."""
    return " ".join(["wsl.exe", *argv[1:]] if argv and argv[0] == WSL else argv)


def decode(data: bytes | None) -> str:
    """wsl.exe writes its own messages in UTF-16; commands inside the distro write UTF-8."""
    if not data:
        return ""
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="replace").replace("\x00", "").lstrip("\ufeff")
    return data.decode("utf-8", errors="replace")


def run_command(argv: Sequence[str], timeout: float) -> Completed:
    """The real runner: no console window under pythonw, and a timeout raised as TimeoutError."""
    try:
        done = subprocess.run(list(argv), capture_output=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"{shown(argv)} did not finish within {timeout:.0f} s") from None
    return Completed(done.returncode, decode(done.stdout), decode(done.stderr))


def output_tail(done: Completed | None, limit: int = 300) -> str:
    if done is None:
        return ""
    lines = (ANSI.sub("", line).strip() for line in f"{done.stdout}\n{done.stderr}".splitlines())
    return " / ".join(line for line in lines if line)[-limit:]


def distro_running(run: Runner) -> bool | None:
    """Whether the distro is up, asked without starting it; None when WSL cannot say."""
    try:
        done = run(running_argv(), QUERY_TIMEOUT_S)
    except (OSError, TimeoutError):
        return None
    if DISTRO in {line.strip() for line in done.stdout.splitlines()}:
        return True
    if done.returncode == 0 or "no running distributions" in f"{done.stdout} {done.stderr}".lower():
        return False
    return None


def is_active(run: Runner) -> str:
    """``systemctl --user is-active`` for the gateway, or 'unknown' when it cannot be asked."""
    try:
        done = run(is_active_argv(), QUERY_TIMEOUT_S)
    except (OSError, TimeoutError):
        return "unknown"
    first = next((line.strip() for line in done.stdout.splitlines() if line.strip()), "")
    return first if first in SYSTEMD_STATES else "unknown"


def observe(run: Runner) -> str:
    """The gateway's systemd state without starting WSL: 'not running' while the distro is down."""
    return "not running" if distro_running(run) is False else is_active(run)


def settle(run: Runner, sleep: Sleep, state: str, moving: frozenset[str], budget_s: float) -> str:
    """Ask again every few seconds while the unit is still moving, up to the budget."""
    waited = 0.0
    while state in moving and waited < budget_s:
        sleep(SETTLE_POLL_S)
        waited += SETTLE_POLL_S
        state = is_active(run)
    return state


def _joined(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


def stop(run: Runner, sleep: Sleep = time.sleep) -> Result:
    argv = stop_argv()
    if distro_running(run) is False:
        return Result("applied", f"(not run: the {DISTRO} WSL distro is not running)", None, "not running",
                      "WSL is not running, so the gateway is not running; WSL was not started")
    done, note = None, ""
    try:
        done = run(argv, STOP_TIMEOUT_S)
    except TimeoutError:
        note = f"hermes gateway stop did not return within {STOP_TIMEOUT_S:.0f} s"
    except OSError as exc:
        return Result("failed", shown(argv), None, "unknown", f"wsl.exe could not be run ({type(exc).__name__}: {exc})")
    state = settle(run, sleep, is_active(run), frozenset({"deactivating"}), STOP_SETTLE_S)
    exit_status = done.returncode if done else None
    if state in STOPPED:
        how = ("the gateway is stopped" if state == "inactive"
               else "the gateway is not running; systemd reports the unit failed because its last exit was an error")
        return Result("applied", shown(argv), exit_status, state, _joined(how, note, output_tail(done)))
    return Result("failed", shown(argv), exit_status, state,
                  _joined(f"the gateway is still {state} after hermes gateway stop", note, output_tail(done)))


def start(run: Runner, sleep: Sleep = time.sleep) -> Result:
    argv = start_argv()
    if distro_running(run) is False:
        try:
            woke = run(wake_argv(), WAKE_TIMEOUT_S)
        except (OSError, TimeoutError) as exc:
            return Result("failed", shown(wake_argv()), None, "unknown",
                          f"WSL did not start ({type(exc).__name__}); the gateway was not started")
        if woke.returncode != 0:
            return Result("failed", shown(wake_argv()), woke.returncode, "unknown",
                          _joined("WSL did not start; the gateway was not started", output_tail(woke)))
    done, note = None, ""
    try:
        done = run(argv, START_TIMEOUT_S)
    except TimeoutError:
        note = f"systemctl --user start did not return within {START_TIMEOUT_S:.0f} s"
    except OSError as exc:
        return Result("failed", shown(argv), None, "unknown", f"wsl.exe could not be run ({type(exc).__name__}: {exc})")
    state = settle(run, sleep, is_active(run), frozenset({"activating", "reloading"}), START_SETTLE_S)
    exit_status = done.returncode if done else None
    if state == "active":
        return Result("applied", shown(argv), exit_status, state, _joined("the gateway is running", note, output_tail(done)))
    return Result("failed", shown(argv), exit_status, state,
                  _joined(f"the gateway is {state} after systemctl --user start", note, output_tail(done)))


def apply(desired: str, run: Runner = run_command, sleep: Sleep = time.sleep) -> Result:
    """Bring the gateway to the desired state: 'stopped' or 'running'."""
    if desired == "stopped":
        return stop(run, sleep)
    if desired == "running":
        return start(run, sleep)
    return Result("failed", "(not run)", None, "unknown", f"unknown desired state {desired!r}; nothing was run")
