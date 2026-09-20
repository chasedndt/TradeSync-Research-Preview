"""An in-memory connection for the read-only reconciliation, audit and metric routes.

Those routes read through ``heavy_query``, which opens a transaction, sets two
local settings and runs one statement. ``FakeConn`` answers the statement by the
first needle that appears in it and records every statement it was given, so a
test can assert both the answer and that the read went through the bounded path.

An unmatched statement answers with no rows rather than raising: these routes
issue several reads and a test is usually interested in one of them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Iterable


class FakeConn:
    """Answers by SQL substring; records what it was asked."""

    def __init__(self, answers: Iterable[tuple[str, Any]] = ()) -> None:
        self.answers = list(answers)
        self.statements: list[str] = []
        self.settings: list[str] = []

    def transaction(self, **_kwargs):
        conn = self

        class Transaction:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *_exc):
                return False

        return Transaction()

    async def execute(self, sql, *args, timeout=None):
        self.settings.append(sql)
        return "OK"

    async def fetch(self, sql, *args, timeout=None):
        self.statements.append(sql)
        for needle, rows in self.answers:
            if needle in sql:
                return list(rows(*args)) if callable(rows) else list(rows)
        return []

    async def fetchval(self, sql, *args, timeout=None):
        self.statements.append(sql)
        return None

    async def fetchrow(self, sql, *args, timeout=None):
        rows = await self.fetch(sql, *args, timeout=timeout)
        return rows[0] if rows else None

    def asked(self, needle: str) -> bool:
        return any(needle in statement for statement in self.statements)

    def bounded(self) -> bool:
        """Every read went through the bounded pattern: workers off, a server limit."""
        return bool(self.settings) and all(
            "max_parallel_workers_per_gather = 0" in setting and "statement_timeout" in setting
            for setting in self.settings
        )


def pool_of(conn: FakeConn):
    @asynccontextmanager
    async def acquire():
        yield conn

    return SimpleNamespace(acquire=acquire)
