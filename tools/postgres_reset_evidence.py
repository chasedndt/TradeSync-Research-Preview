#!/usr/bin/env python
"""Capture what a PostgreSQL crash reset left behind, before the evidence is gone.

PostgreSQL has reset itself in place several times: a backend exits with code 2,
the postmaster terminates every other process and reinitializes, and recovery
takes a few seconds. The container never restarts, so nothing outside the
database notices, and the only record is the container's log. That log lives and
dies with the container: the 13 and 15 September resets could no longer be read
after the 15 September 17:00 UTC recreate, which is why the cause of those
resets is still unestablished.

Run this after any reset, and before anything is rebuilt or recreated. It reads
and writes nothing: docker logs, docker inspect on named fields only, the
container's own cgroup counters, and SELECTs on catalogue and statistics views.
No table data is read and no setting is changed.

    python tools/postgres_reset_evidence.py
    python tools/postgres_reset_evidence.py --out "E:/Visual QA/TradeSync Visual QA/postgres-reset.txt"

What to look for, in order:

1. the first line of each reset: "server process (PID n) exited with exit code n".
   Exit code 2 is the SIGQUIT path, which a backend takes when something signals
   it or when a crash handler fires; any DETAIL line names the statement it was
   running, and that is the single most useful line in the file;
2. what was cancelled or terminated in the minute before it;
3. whether the container was out of memory (it is not, if oom_kill stays 0);
4. how long recovery took, and whether it happened more than once.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone

CONTAINER = "tradesync-full-postgres-1"

# The postmaster's own account of a reset, and the lines that tend to precede it.
RESET = re.compile(
    r"exited with exit code|terminating any other active server processes|"
    r"all server processes terminated|database system was interrupted|redo done|"
    r"database system is ready to accept connections|terminated by signal|out of memory|"
    r"canceling statement|terminating background worker|terminating connection|"
    r"could not resize shared memory|no space left on device|checkpoint complete",
    re.IGNORECASE,
)

SETTINGS = (
    "max_parallel_workers_per_gather", "max_parallel_workers", "max_worker_processes",
    "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size", "jit",
    "dynamic_shared_memory_type", "statement_timeout", "log_min_messages", "log_connections",
    "logging_collector", "restart_after_crash", "temp_file_limit", "log_temp_files",
)

SQL = f"""
\\echo '--- server'
select version(), pg_postmaster_start_time(), now() - pg_postmaster_start_time() as uptime;
\\echo '--- settings that bear on parallel scans and on what the log keeps'
select name, setting, unit, source from pg_settings where name in ({", ".join(f"'{name}'" for name in SETTINGS)}) order by name;
\\echo '--- session and temporary-file counters (a reset discards these)'
select datname, stats_reset, sessions, sessions_abandoned, sessions_fatal, sessions_killed,
       temp_files, pg_size_pretty(temp_bytes) as temp_bytes, deadlocks, xact_rollback
  from pg_stat_database where datname = current_database();
\\echo '--- anything running now, oldest first'
select pid, state, wait_event_type, wait_event, now() - xact_start as xact_age,
       now() - query_start as query_age, left(regexp_replace(query, '\\s+', ' ', 'g'), 120) as query
  from pg_stat_activity where backend_type = 'client backend' and pid <> pg_backend_pid()
  order by xact_start nulls last limit 20;
\\echo '--- the ten largest tables'
select c.relname, pg_size_pretty(pg_total_relation_size(c.oid)) as total
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r'
 order by pg_total_relation_size(c.oid) desc limit 10;
"""


def run(command: list[str], stdin: str | None = None) -> str:
    """One read-only command; its own error text is the evidence when it fails."""
    try:
        done = subprocess.run(command, input=stdin, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"[could not run {' '.join(command[:3])}...: {type(exc).__name__}: {exc}]"
    return (done.stdout or "") + (f"\n[stderr] {done.stderr}" if done.stderr.strip() else "")


def psql(container: str, sql: str) -> str:
    """psql inside the container, using the container's own credentials from its environment.

    Nothing reads or prints those credentials: the shell inside the container
    expands them, and only query results come back.
    """
    return run(
        ["docker", "exec", "-i", container, "sh", "-c",
         'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -q -P pager=off'],
        stdin=sql,
    )


def log_lines(container: str, keep: int) -> list[str]:
    """Timestamped log lines that bear on a reset, newest last."""
    raw = run(["docker", "logs", "-t", container])
    return [line for line in raw.splitlines() if RESET.search(line)][-keep:]


def resets(lines: list[str]) -> list[str]:
    return [line for line in lines if "exited with exit code" in line and "exit code 0" not in line]


def report(container: str, keep: int) -> str:
    parts = [
        f"PostgreSQL reset evidence for {container}",
        f"captured {datetime.now(timezone.utc).isoformat()} (UTC), read-only",
        "",
        "=== container ===",
        run(["docker", "inspect", container, "--format",
             "created={{.Created}} started={{.State.StartedAt}} status={{.State.Status}} "
             "restarts={{.RestartCount}} oom_killed={{.State.OOMKilled}} memory={{.HostConfig.Memory}} "
             "cpus={{.HostConfig.NanoCpus}} shm={{.HostConfig.ShmSize}} log={{json .HostConfig.LogConfig}}"]),
        "=== cgroup: memory ceiling, out-of-memory events, peak, cpu throttling ===",
        run(["docker", "exec", container, "sh", "-c",
             "cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.peak 2>/dev/null; "
             "cat /sys/fs/cgroup/memory.events 2>/dev/null; cat /sys/fs/cgroup/cpu.stat 2>/dev/null; "
             "df -h /dev/shm /var/lib/postgresql/data"]),
        "=== database ===",
        psql(container, SQL),
    ]
    lines = log_lines(container, keep)
    found = resets(lines)
    parts += [
        "=== resets found in the log this container still holds ===",
        "\n".join(found) if found else "(none in this container's log; a recreate discards the previous one's)",
        "",
        f"=== log lines that bear on a reset (last {keep}) ===",
        "\n".join(lines) if lines else "(none)",
    ]
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--container", default=CONTAINER)
    parser.add_argument("--lines", type=int, default=400, help="how many relevant log lines to keep")
    parser.add_argument("--out", help="write the report here as well as to the screen")
    args = parser.parse_args()

    text = report(args.container, args.lines)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"\n[written to {args.out}]")
    return 0 if resets(log_lines(args.container, args.lines)) == [] else 2


if __name__ == "__main__":
    raise SystemExit(main())
