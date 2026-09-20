"""The bounded reads: no parallel workers, a server-side limit, and a record of the cost."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import heavy_query


class Conn:
    """An asyncpg-shaped connection that records the statements it was given."""

    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.statements, self.timeout = rows or [], error, [], None
        self.transactions = 0

    def transaction(self):
        conn = self

        class Transaction:
            async def __aenter__(self):
                conn.transactions += 1

            async def __aexit__(self, *_):
                return False

        return Transaction()

    async def execute(self, sql, *args):
        self.statements.append(sql)

    async def fetch(self, sql, *args, timeout=None):
        self.statements.append(sql)
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.rows

    async def fetchval(self, sql, *args, timeout=None):
        self.statements.append(sql)
        self.timeout = timeout
        return 7


@pytest.fixture(autouse=True)
def clean_readings():
    heavy_query.readings.clear()
    yield
    heavy_query.readings.clear()


@pytest.mark.asyncio
async def test_every_heavy_read_turns_parallel_workers_off_inside_its_own_transaction():
    conn = Conn(rows=[1, 2, 3])
    rows = await heavy_query.fetch(conn, "test:read", "SELECT 1", timeout_s=12)
    assert rows == [1, 2, 3] and conn.transactions == 1
    settings = conn.statements[0]
    assert "SET LOCAL max_parallel_workers_per_gather = 0" in settings
    assert "SET LOCAL statement_timeout = 12000" in settings


@pytest.mark.asyncio
async def test_the_client_waits_longer_than_the_server_so_the_server_s_limit_fires_first():
    conn = Conn()
    await heavy_query.fetch(conn, "test:read", "SELECT 1", timeout_s=20)
    assert conn.timeout == 20 + heavy_query.CLIENT_GRACE_S


@pytest.mark.asyncio
async def test_a_read_is_recorded_with_what_it_cost():
    await heavy_query.fetch(Conn(rows=[1]), "test:read", "SELECT 1")
    reading = heavy_query.readings["test:read"]
    assert reading["runs"] == 1 and reading["failures"] == 0 and reading["rows"] == 1
    assert reading["last_duration_s"] >= 0 and reading["last_error"] is None and reading["at"]


@pytest.mark.asyncio
async def test_a_failed_read_is_recorded_and_still_raised():
    with pytest.raises(TimeoutError):
        await heavy_query.fetch(Conn(error=TimeoutError("query timed out")), "test:read", "SELECT 1")
    reading = heavy_query.readings["test:read"]
    assert reading["runs"] == 1 and reading["failures"] == 1
    assert "TimeoutError" in reading["last_error"]


@pytest.mark.asyncio
async def test_the_slowest_run_is_kept_across_runs():
    conn = Conn(rows=[1])
    await heavy_query.fetch(conn, "test:read", "SELECT 1")
    await heavy_query.fetch(conn, "test:read", "SELECT 1")
    reading = heavy_query.readings["test:read"]
    assert reading["runs"] == 2 and reading["slowest_s"] >= reading["last_duration_s"]


@pytest.mark.asyncio
async def test_a_single_value_read_is_bounded_the_same_way():
    conn = Conn()
    assert await heavy_query.fetchval(conn, "test:count", "SELECT count(*) FROM t") == 7
    assert "SET LOCAL max_parallel_workers_per_gather = 0" in conn.statements[0]
    assert heavy_query.readings["test:count"]["runs"] == 1


def test_the_status_says_what_the_reads_cost_and_claims_nothing_else():
    status = heavy_query.status()
    assert status["statement_timeout_s"] == heavy_query.DEFAULT_TIMEOUT_S
    assert "off for these reads" in status["parallel_workers"]
    assert "nothing is written" in status["note"]


def test_an_implausible_timeout_still_produces_a_positive_server_limit():
    assert "statement_timeout = 1000" in heavy_query._settings(0)
    assert "statement_timeout = 1000" in heavy_query._settings(-5)
