#!/usr/bin/env python
"""Isolated, rolled-back SQL acceptance for migration 031 and the paper entry lock.

Two database connections, driven through psql:

* Session A runs one script inside one transaction: a throwaway schema, then 023,
  026 and 031 UP, 031 DOWN, 031 UP again. It checks the seeds, the append-only
  triggers and the check constraints, including funding adjustments. It then runs
  state-api's own statements, imported from its modules and prepared as they are,
  against seeded rows: reconciliation, marks and gaps, and the booking of a funding
  adjustment. That booking must move cash and funding by exactly the adjustment,
  once. Finally it takes advisory lock 230914 (the entry lock), holds it, and rolls
  back. ON_ERROR_STOP ends the session, uncommitted, on the first failed check.
* Session B, a separate connection per step, must see A holding the lock, fail to take
  it, block while waiting for it, acquire it only after A's rollback, and finally find
  the throwaway schema gone.

Unqualified names resolve only inside the throwaway schema (``SET LOCAL search_path``),
so nothing in the public schema is read or written; the advisory lock is the only shared
object touched, for a few seconds.

    python tools/qa_paper_risk_sql.py                  # docker exec into tradesync-full-postgres-1
    python tools/qa_paper_risk_sql.py --container qa-paper-risk-throwaway
"""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
import uuid

from qa_paper_risk_script import ENTRY_LOCK, session_a_script


def psql_command(args: argparse.Namespace) -> list[str]:
    flags = ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
    if args.local:
        host, port, user, database = args.local.split(":")
        return [args.psql_bin, *flags, "-h", host, "-p", port, "-U", user, "-d", database]
    return ["docker", "exec", "-i", args.container, "sh", "-c", "psql " + " ".join(flags) + ' -U "$POSTGRES_USER" -d "$POSTGRES_DB"']


def one_shot(command: list[str], sql: str, timeout: float = 90) -> tuple[int, str]:
    result = subprocess.run(command, input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return result.returncode, (result.stdout + result.stderr).strip()


def lock_rows(command: list[str], application: str, granted: bool) -> int:
    code, out = one_shot(command, "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                  f"WHERE l.locktype = 'advisory' AND l.objid = {ENTRY_LOCK} AND l.objsubid = 1 "
                                  f"AND l.granted = {str(granted).lower()} AND a.application_name = '{application}';")
    return int(out.splitlines()[-1]) if code == 0 and out else -1


def a_lock_state(command: list[str], application: str) -> str:
    """'true' while session A holds the entry lock, 'false' while it waits for it, 'none' before it asks."""
    code, out = one_shot(command, "SELECT coalesce(bool_or(l.granted)::text, 'none') FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                  f"WHERE l.locktype = 'advisory' AND l.objid = {ENTRY_LOCK} AND l.objsubid = 1 AND a.application_name = '{application}';")
    return out.splitlines()[-1].strip() if code == 0 and out else "unknown"


def other_holders(command: list[str], application: str) -> str:
    code, out = one_shot(command, "SELECT coalesce(string_agg(l.pid || ' ' || coalesce(nullif(a.application_name, ''), 'unnamed client') || ', ' || a.state "
                                  "|| ' for ' || date_trunc('second', now() - a.xact_start), '; '), 'nobody') FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                  f"WHERE l.locktype = 'advisory' AND l.objid = {ENTRY_LOCK} AND l.objsubid = 1 AND l.granted "
                                  f"AND a.application_name <> '{application}';")
    return out.splitlines()[-1] if code == 0 and out else "unknown"


def terminate_own(command: list[str], application: str) -> None:
    """End this run's own backend, whose transaction then rolls back. No other session is touched."""
    one_shot(command, f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = '{application}';")


class Background:
    def __init__(self, command: list[str], sql: str):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace")
        self.lines: list[str] = []
        self.reader = threading.Thread(target=lambda: self.lines.extend(line.rstrip("\r\n") for line in self.proc.stdout), daemon=True)
        self.reader.start()
        self.proc.stdin.write(sql)
        self.proc.stdin.close()

    def finish(self, timeout: float) -> int:
        code = self.proc.wait(timeout=timeout)
        self.reader.join(timeout=5)
        return code

    def value(self, prefix: str) -> float:
        return float(next(line for line in self.lines if line.startswith(prefix)).split()[1])


def wait_for(predicate, timeout: float, alive=lambda: True) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and alive():
        if predicate():
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--container", default="tradesync-full-postgres-1")
    parser.add_argument("--local", help="host:port:user:database for a throwaway local cluster")
    parser.add_argument("--psql-bin", default="psql")
    parser.add_argument("--hold", type=float, default=12.0, help="seconds session A holds the entry lock")
    parser.add_argument("--lock-wait", type=float, default=420.0, help="seconds session A may queue behind another holder of the entry lock")
    args = parser.parse_args()
    command = psql_command(args)
    run = uuid.uuid4().hex[:12]
    schema, app_a, app_b = f"qa_paper_risk_{run}", f"qa_paper_risk_a_{run}", f"qa_paper_risk_b_{run}"
    failures: list[str] = []

    session_a = Background(command, session_a_script(schema, app_a, args.hold))
    queued = []

    def holding() -> bool:
        state = a_lock_state(command, app_a)
        if state == "false" and not queued:
            queued.append(True)  # another session holds the entry lock; wait behind it rather than contend
            print("WAIT session A is queued for entry lock 230914 behind: " + other_holders(command, app_a), flush=True)
        return state == "true"

    if not wait_for(holding, args.lock_wait, alive=lambda: session_a.proc.poll() is None):
        if session_a.proc.poll() is None:
            terminate_own(command, app_a)  # the client alone may not end psql inside a container
            session_a.proc.kill()
        session_a.finish(120)
        print("\n".join(session_a.lines))
        print("FAIL: session A did not hold the entry lock (a check above failed, or the wait ran out); nothing was committed")
        return 1
    print("PASS session A holds entry lock 230914 inside its uncommitted transaction")

    code, out = one_shot(command, f"SELECT pg_try_advisory_xact_lock({ENTRY_LOCK});")
    (print if out.endswith("f") else failures.append)("PASS session B cannot take the entry lock while A holds it" if out.endswith("f") else f"B try-lock: {out}")
    code, out = one_shot(command, f"SET lock_timeout = '500ms'; SELECT pg_advisory_xact_lock({ENTRY_LOCK});")
    ok = code != 0 and "lock timeout" in out
    (print if ok else failures.append)("PASS session B's blocking attempt times out while A holds it" if ok else f"B lock timeout: {code} {out}")

    waiter = Background(command, f"SET application_name = '{app_b}';\n"
                                 f"SELECT pg_advisory_xact_lock({ENTRY_LOCK});\nSELECT 'B_ACQUIRED_AT ' || extract(epoch FROM clock_timestamp());\n")
    blocked = wait_for(lambda: lock_rows(command, app_b, False) == 1, 60, alive=lambda: waiter.proc.poll() is None)
    (print if blocked else failures.append)("PASS session B waits for the entry lock" if blocked else "B was never seen waiting for the lock")

    a_code = session_a.finish(args.hold + 120)
    b_code = waiter.finish(120)
    print("\n".join(line for line in session_a.lines if line.startswith("PASS")))
    if a_code != 0:
        failures.append("session A: " + " | ".join(session_a.lines[-8:]))
    else:
        acquired, released = waiter.value("B_ACQUIRED_AT"), session_a.value("A_RELEASE_AT")
        ok = b_code == 0 and acquired >= released
        (print if ok else failures.append)(f"PASS session B acquired the lock {acquired - released:.3f}s after A released it" if ok else f"B acquired {acquired} before release {released}")

    code, out = one_shot(command, f"SELECT pg_try_advisory_xact_lock({ENTRY_LOCK});")
    (print if out.endswith("t") else failures.append)("PASS the entry lock is free after A's rollback" if out.endswith("t") else f"final try-lock: {out}")
    code, out = one_shot(command, f"SELECT count(*) FROM pg_namespace WHERE nspname = '{schema}';")
    (print if out.endswith("0") else failures.append)("PASS throwaway schema is gone: nothing was committed" if out.endswith("0") else f"schema still present: {out}")

    for failure in failures:
        print("FAIL: " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
