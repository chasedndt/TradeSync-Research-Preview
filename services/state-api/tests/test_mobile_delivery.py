"""Bounded retries, dead letters that keep their reason, and acknowledgement recorded against the outbox row."""

import asyncio
import inspect
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import mobile_alerts as mobile
from app import mobile_delivery as delivery
from app.main import app, state

KEY = "k" * 40
WHEN = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


@asynccontextmanager
async def nothing():
    yield


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


class RecordingConn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def test_the_wait_between_attempts_doubles_from_fifteen_seconds_and_is_capped():
    assert [delivery.backoff_seconds(n) for n in range(1, 6)] == [15, 30, 60, 120, 120]
    with pytest.raises(ValueError):
        delivery.backoff_seconds(0)


def test_the_whole_retry_ladder_fits_inside_the_window_a_row_is_enqueued_with():
    # Otherwise a failing row would quietly expire instead of reaching its dead letter.
    assert delivery.total_backoff_seconds() == 15 + 30 + 60 + 120
    assert delivery.total_backoff_seconds() < delivery.EXPIRY_SECONDS
    assert delivery.EXPIRY_SECONDS == 600 and "interval '10 minutes'" in inspect.getsource(mobile.enqueue)


def test_a_failure_is_tried_again_until_the_attempt_limit_and_then_dead_lettered():
    first = delivery.outcome(1, "TimeoutError")
    assert (first.status, first.retry_in_seconds, first.reason) == ("retry", 15, None)
    assert delivery.outcome(delivery.MAX_ATTEMPTS - 1, "TimeoutError").status == "retry"
    last = delivery.outcome(delivery.MAX_ATTEMPTS, "TimeoutError")
    assert last.status == "dead_letter" and last.retry_in_seconds == 0
    assert "after 5 attempts" in last.reason and "TimeoutError" in last.reason


def test_a_refusal_that_will_not_change_is_not_tried_again_but_rate_limiting_is():
    refused = delivery.outcome(1, "HTTPStatusError", 404)
    assert refused.status == "dead_letter" and "HTTP 404" in refused.reason
    assert delivery.outcome(1, "HTTPStatusError", 429).status == "retry"
    assert delivery.outcome(1, "HTTPStatusError", 503).status == "retry"
    assert delivery.permanent(400) and delivery.permanent(413)
    assert not delivery.permanent(429) and not delivery.permanent(500) and not delivery.permanent(None)


def test_a_dead_letter_reason_names_only_a_status_code_and_an_exception_class():
    """The ledger is displayed, so a reason must never carry a topic, a URL or a provider's body."""
    for reason in (delivery.outcome(1, "HTTPStatusError", 404).reason,
                   delivery.outcome(delivery.MAX_ATTEMPTS, "ConnectError", 500).reason,
                   delivery.EXHAUSTED_SWEEP_REASON):
        lowered = reason.lower()
        assert "ntfy" not in lowered and "http://" not in lowered and "https://" not in lowered
        assert "tradesync-" not in lowered


def test_the_claim_is_bounded_by_the_attempt_limit_and_takes_a_lease():
    assert delivery.CLAIM_SQL.startswith("WITH candidate")
    assert "o.attempts<$1" in delivery.CLAIM_SQL
    assert "attempted_at=now()" in delivery.CLAIM_SQL
    assert f"interval '{delivery.LEASE_SECONDS} seconds'" in delivery.CLAIM_SQL
    assert "SKIP LOCKED" in delivery.CLAIM_SQL


def test_the_sweep_expires_old_rows_then_dead_letters_the_ones_that_can_never_run_again():
    conn = RecordingConn()
    asyncio.run(delivery.sweep(conn))
    (expired, expired_args), (exhausted, exhausted_args), (spent, spent_args) = conn.executed
    assert "status='expired'" in expired and expired_args == ()
    assert "status='dead_letter'" in exhausted and "dead_letter_reason=coalesce" in exhausted
    assert exhausted_args == (delivery.MAX_ATTEMPTS, delivery.EXHAUSTED_SWEEP_REASON)
    # A row still inside its lease is mid-attempt and is left alone.
    assert "lease_until IS NULL OR lease_until < now()" in exhausted
    # A tap token that has run out is dropped, digest and all.
    assert "ack_token_hash=NULL" in spent and "ack_token_expires_at <= now()" in spent and spent_args == ()


def test_one_failed_attempt_writes_the_next_attempt_time_or_the_dead_letter_and_its_reason():
    conn, event = RecordingConn(), uuid.uuid4()
    asyncio.run(delivery.record_failure(conn, event, delivery.outcome(2, "TimeoutError")))
    sql, args = conn.executed[0]
    assert args == (event, "retry", "TimeoutError", 30.0, None)
    assert "make_interval" in sql and "lease_until=NULL" in sql and "attempted_at=now()" in sql

    asyncio.run(delivery.record_failure(conn, event, delivery.outcome(1, "HTTPStatusError", 404)))
    _, dead = conn.executed[1]
    assert dead[1] == "dead_letter" and dead[3] == 0.0 and "HTTP 404" in dead[4]


class DispatchConn:
    """Answers the delivery worker: the sweep, one claimed row, then the row's topic."""

    def __init__(self, attempts):
        self.executed = []
        self.row = {"id": uuid.UUID(int=7), "device_id": uuid.UUID(int=8), "kind": "test",
                    "dedupe_key": "test:1", "attempts": attempts}

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchrow(self, sql, *args):
        return self.row if sql.startswith("WITH candidate") else None

    async def fetchval(self, sql, *args):
        return "tradesync-" + "a" * 48


def dispatch_failure(attempts, error):
    conn = DispatchConn(attempts)
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), \
            patch.object(mobile, "publish", AsyncMock(side_effect=error)):
        asyncio.run(mobile.dispatch_one(Pool(conn)))
    return next(args for sql, args in conn.executed if "last_error" in sql)


def test_a_failed_send_is_written_through_the_delivery_policy_not_a_fixed_minute():
    retried = dispatch_failure(1, TimeoutError("private detail"))
    assert retried[1:4] == ("retry", "TimeoutError", 15.0) and retried[4] is None
    given_up = dispatch_failure(delivery.MAX_ATTEMPTS, TimeoutError("private detail"))
    assert given_up[1] == "dead_letter" and "after 5 attempts" in given_up[4]
    assert "private detail" not in json.dumps(list(map(str, given_up)))


class AckConn:
    def __init__(self, row):
        self.row, self.written = row, []

    def transaction(self):
        return nothing()

    async def fetchrow(self, sql, *args):
        if sql.startswith("UPDATE"):
            self.written.append(args)
            return {"id": args[0], "status": self.row["status"], "attempts": self.row["attempts"],
                    "acknowledged_at": WHEN, "acknowledged_by": args[1]}
        return self.row


def acknowledge(row, by="operator"):
    conn = AckConn(row)
    return conn, asyncio.run(delivery.acknowledge(conn, uuid.UUID(int=7), by))


def test_only_something_that_was_attempted_can_be_acknowledged():
    conn, missing = acknowledge(None)
    assert missing == {"outcome": "not_found"} and conn.written == []
    conn, queued = acknowledge({"status": "queued", "attempts": 0, "acknowledged_at": None, "acknowledged_by": None})
    assert queued["outcome"] == "never_attempted" and conn.written == []


def test_an_acknowledgement_names_who_said_so_and_the_first_one_is_the_one_kept():
    row = {"status": "provider_accepted", "attempts": 1, "acknowledged_at": None, "acknowledged_by": None}
    conn, device = acknowledge(row, "device")
    assert device["outcome"] == "acknowledged" and device["acknowledged_by"] == "device"
    assert conn.written[0][1] == "device" and "acknowledged_at IS NULL" in delivery.ACKNOWLEDGE_SQL

    already = {"status": "provider_accepted", "attempts": 2, "acknowledged_at": WHEN, "acknowledged_by": "operator"}
    conn, second = acknowledge(already, "device")
    assert second == {"outcome": "already_acknowledged", "acknowledged_at": WHEN, "acknowledged_by": "operator"}
    assert conn.written == []

    with pytest.raises(ValueError):
        asyncio.run(delivery.acknowledge(AckConn(row), uuid.UUID(int=7), "the market"))


def test_the_operator_attestation_records_the_acknowledgement_in_the_same_statement():
    source = inspect.getsource(mobile.register)
    assert "status='operator_confirmed', confirmed_at=now(), acknowledged_at=coalesce(acknowledged_at,now())" in source
    assert "acknowledged_by=coalesce(acknowledged_by,'operator')" in source


def test_the_ledger_and_acknowledgement_routes_fail_closed_without_the_control_key():
    client = TestClient(app)
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": ""}):
        assert client.get("/state/mobile-alerts/ledger").status_code == 503
        assert client.post(f"/state/mobile-alerts/events/{uuid.uuid4()}/acknowledge", json={}).status_code == 503
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        assert client.get("/state/mobile-alerts/ledger", headers={"X-API-Key": "wrong"}).status_code == 403
        assert client.post(f"/state/mobile-alerts/events/{uuid.uuid4()}/acknowledge", json={},
                           headers={"X-API-Key": "wrong"}).status_code == 403


class LedgerConn:
    def __init__(self, rows):
        self.rows, self.limit = rows, None

    async def fetch(self, sql, *args):
        self.limit = args[0]
        return self.rows


def test_the_ledger_shows_status_attempts_the_last_error_and_exact_times(monkeypatch):
    row = {"id": uuid.UUID(int=3), "device_id": uuid.UUID(int=4), "device_label": "My phone", "platform": "ios",
           "kind": "attention", "status": "dead_letter", "transport": "web_push", "attempts": 5, "created_at": WHEN,
           "next_attempt_at": WHEN,
           "attempted_at": WHEN, "accepted_at": None, "confirmed_at": None, "acknowledged_at": None,
           "acknowledged_by": None, "dead_lettered_at": WHEN,
           "dead_letter_reason": "No delivery after 5 attempts. Last error TimeoutError.",
           "last_error": "TimeoutError", "expires_at": WHEN}
    conn = LedgerConn([row])
    monkeypatch.setattr(state, "pool", Pool(conn))
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        body = TestClient(app).get("/state/mobile-alerts/ledger?limit=7", headers={"X-API-Key": KEY}).json()
    event = body["events"][0]
    assert conn.limit == 7
    assert event["created_at"] == "2026-09-16T12:00:00+00:00" and event["dead_lettered_at"] == event["created_at"]
    assert event["id"] == str(uuid.UUID(int=3)) and event["device_label"] == "My phone"
    assert event["status"] == "dead_letter" and event["attempts"] == 5 and event["last_error"] == "TimeoutError"
    assert event["acknowledged_at"] is None and event["acknowledged_by"] is None and event["transport"] == "web_push"
    assert "o.transport" in delivery.LEDGER_SQL
    assert body["max_attempts"] == 5 and body["retry_seconds"] == [15, 30, 60, 120]


def test_acknowledging_something_that_was_never_attempted_is_refused_in_plain_words(monkeypatch):
    conn = AckConn({"status": "queued", "attempts": 0, "acknowledged_at": None, "acknowledged_by": None})
    monkeypatch.setattr(state, "pool", Pool(conn))
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        client = TestClient(app)
        refused = client.post(f"/state/mobile-alerts/events/{uuid.uuid4()}/acknowledge",
                              json={"by": "operator"}, headers={"X-API-Key": KEY})
        assert refused.status_code == 409 and "not been attempted" in refused.json()["detail"]
        # A phone acknowledges by tapping, with its token; this route cannot claim to be one.
        device = client.post(f"/state/mobile-alerts/events/{uuid.uuid4()}/acknowledge",
                             json={"by": "device"}, headers={"X-API-Key": KEY})
        assert device.status_code == 422 and "tapping the notification" in device.json()["detail"]
        assert client.post(f"/state/mobile-alerts/events/{uuid.uuid4()}/acknowledge",
                           json={"by": "nobody"}, headers={"X-API-Key": KEY}).status_code == 422
