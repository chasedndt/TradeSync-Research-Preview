"""Bounded reads for the scans that cover whole tables, and a record of what they cost.

Every research reading in this service scans the attribution or outcome history
end to end. Three things about that were left to chance:

- the pool's five-second ``command_timeout`` cancelled them mid-flight. A
  cancelled parallel query is the last thing PostgreSQL logged before each of the
  crash resets of 13 and 15 September. Cancelling one does not crash a stock
  16.15 (measured: see the change record), but nothing here ever needed these
  reads cancelled at five seconds either, and a cancel mid-scan wastes the whole
  scan and leaves its temporary files to clean up;
- they ran with parallel workers inside a container limited to half a CPU, where
  the workers compete with their own leader for that half;
- nothing recorded how long they took, so a read that had begun timing out
  looked exactly like a read that was merely slow.

``fetch`` runs one statement with parallelism off, a server-side statement
timeout that ends it cleanly at a stated limit, a client timeout a little longer
so the server's own limit is the one that fires, and the duration kept under a
name for ``/state/learning/status`` to report.

Read-only by construction: it opens a transaction, sets two local settings and
runs the one statement it was given.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

# Generous next to the tens of milliseconds these reads take once they select
# only the columns they use, and far short of a page load anyone would wait for.
DEFAULT_TIMEOUT_S = 30.0
# The client waits a little longer than the server, so a slow read ends as a
# clean server-side statement timeout instead of a cancel racing the query.
CLIENT_GRACE_S = 5.0

readings: dict[str, dict[str, Any]] = {}


def _record(name: str, started: float, *, rows: int | None = None, error: BaseException | None = None) -> None:
    duration = round(time.monotonic() - started, 3)
    entry = readings.setdefault(name, {"runs": 0, "failures": 0, "slowest_s": 0.0})
    entry.update(
        runs=entry["runs"] + 1,
        failures=entry["failures"] + (1 if error is not None else 0),
        last_duration_s=duration,
        slowest_s=max(entry["slowest_s"], duration),
        rows=rows,
        last_error=None if error is None else f"{type(error).__name__}: {error}"[:200],
        at=datetime.now(timezone.utc).isoformat(),
    )


def _settings(timeout_s: float) -> str:
    """The two settings every heavy read runs under, as one statement.

    Both are ``SET LOCAL``: they last for this transaction and change nothing
    about the server's configuration.
    """
    return (
        "SET LOCAL max_parallel_workers_per_gather = 0; "
        f"SET LOCAL statement_timeout = {int(max(1.0, timeout_s) * 1000)}"
    )


async def fetch(conn, name: str, sql: str, *args, timeout_s: float = DEFAULT_TIMEOUT_S) -> list:
    """One bounded read, with no parallel workers and its duration recorded."""
    started = time.monotonic()
    try:
        async with conn.transaction():
            await conn.execute(_settings(timeout_s))
            rows = await conn.fetch(sql, *args, timeout=timeout_s + CLIENT_GRACE_S)
    except BaseException as exc:
        _record(name, started, error=exc)
        raise
    _record(name, started, rows=len(rows))
    return rows


async def fetchval(conn, name: str, sql: str, *args, timeout_s: float = DEFAULT_TIMEOUT_S) -> Any:
    """One bounded single-value read, recorded the same way."""
    started = time.monotonic()
    try:
        async with conn.transaction():
            await conn.execute(_settings(timeout_s))
            value = await conn.fetchval(sql, *args, timeout=timeout_s + CLIENT_GRACE_S)
    except BaseException as exc:
        _record(name, started, error=exc)
        raise
    _record(name, started, rows=None if value is None else 1)
    return value


def status() -> dict[str, Any]:
    """What the heavy reads have cost, for the operator's status page."""
    return {
        "reads": readings,
        "statement_timeout_s": DEFAULT_TIMEOUT_S,
        "parallel_workers": "off for these reads (SET LOCAL, this transaction only)",
        "note": (
            "Durations of the whole-table research scans. A failure here is the read, not the database: "
            "the reading is served stale or recomputed, and nothing is written."
        ),
    }
