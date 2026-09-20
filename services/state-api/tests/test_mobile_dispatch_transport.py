"""Which transport carries an attempt, and that both land on one row through one retry and dead-letter path."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from app import mobile_ack_token, mobile_alerts as mobile, mobile_delivery, mobile_vapid
from app import mobile_web_push_sender as sender

KEY = "k" * 40
TOPIC = "tradesync-" + "a" * 48
BROWSER = {"id": uuid.UUID(int=9), "endpoint": "https://fcm.googleapis.com/fcm/send/x", "endpoint_digest": "e" * 12,
           "p256dh": "p", "auth": "a"}


class Conn:
    """Answers the dispatcher: one claimed test row, its topic, and the phone's active browsers."""

    def __init__(self, browsers=(), attempts=1):
        self.browsers, self.executed, self.fetched = list(browsers), [], []
        self.row = {"id": uuid.UUID(int=7), "device_id": uuid.UUID(int=8), "kind": "test", "dedupe_key": "test:1",
                    "attempts": attempts}

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchrow(self, sql, *args):
        return self.row if sql.startswith("WITH candidate") else None

    async def fetchval(self, sql, *args):
        return TOPIC

    async def fetch(self, sql, *args):
        self.fetched.append(args)
        return self.browsers

    def issued(self):
        return next(args for sql, args in self.executed if sql == mobile_ack_token.ISSUE_SQL)

    def written(self, marker):
        return next(args for sql, args in self.executed if marker in sql and sql != mobile_ack_token.ISSUE_SQL)


def dispatch(conn, *, ready, deliver=None, publish=None):
    publish = publish or AsyncMock(return_value="ntfy-id")
    deliver = deliver or AsyncMock(return_value="web_push 1/1")
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), \
            patch.object(mobile_vapid, "sender_ready", return_value=ready), \
            patch.object(mobile, "publish", publish), patch.object(sender, "deliver", deliver):
        asyncio.run(mobile.dispatch_one(conn))
    return publish, deliver


def test_a_phone_with_a_subscribed_browser_is_sent_web_push_with_a_token_stored_only_as_its_digest():
    conn = Conn([BROWSER])
    publish, deliver = dispatch(conn, ready=True)
    publish.assert_not_called()
    (_, browsers, kind, event, token), _ = deliver.call_args
    assert browsers == [BROWSER] and kind == "test" and event == conn.row["id"]
    assert conn.issued() == (conn.row["id"], "web_push", mobile_ack_token.digest(token))
    assert mobile_ack_token.well_formed(token) and token not in str(conn.executed)
    assert conn.written("provider_accepted") == (conn.row["id"], "web_push 1/1")
    assert conn.fetched == [(conn.row["device_id"], sender.MAX_BROWSERS)]


def test_without_a_browser_or_while_web_push_cannot_send_the_attempt_goes_through_ntfy_with_no_token():
    for browsers, ready in (([], True), ([BROWSER], False)):
        conn = Conn(browsers)
        publish, deliver = dispatch(conn, ready=ready)
        deliver.assert_not_called()
        publish.assert_awaited_once_with(TOPIC, "test", conn.row["id"])
        assert conn.issued() == (conn.row["id"], "ntfy", None)
        assert conn.written("provider_accepted") == (conn.row["id"], "ntfy-id")
        # Nothing is asked about browsers while Web Push cannot send.
        assert conn.fetched == ([] if not ready else [(conn.row["device_id"], sender.MAX_BROWSERS)])


def test_a_web_push_failure_goes_through_the_same_retry_and_dead_letter_policy_as_ntfy():
    for error, status, reason in ((sender.WebPushUndelivered("PushServiceUnavailable", 503), "retry", None),
                                  (sender.WebPushUndelivered("SubscriptionsGone"), "retry", None),
                                  (sender.WebPushUndelivered("PushServiceRefused", 403), "dead_letter", "HTTP 403")):
        conn = Conn([BROWSER])
        dispatch(conn, ready=True, deliver=AsyncMock(side_effect=error))
        written = conn.written("last_error")
        assert written[1:3] == (status, error.error_name)
        assert (reason is None and written[4] is None) or reason in written[4]
    exhausted = Conn([BROWSER], attempts=mobile_delivery.MAX_ATTEMPTS)
    dispatch(exhausted, ready=True, deliver=AsyncMock(side_effect=sender.WebPushUndelivered("PushServiceUnavailable", 503)))
    assert exhausted.written("last_error")[1] == "dead_letter"
    assert "after 5 attempts" in exhausted.written("last_error")[4]


def test_a_failure_is_reduced_to_a_short_name_and_a_status_and_nothing_else():
    class WithResponse(Exception):
        response = type("Response", (), {"status_code": 429})()

    assert mobile_delivery.failure(sender.WebPushUndelivered("PushServiceRefused", 413)) == ("PushServiceRefused", 413)
    assert mobile_delivery.failure(WithResponse("private body")) == ("WithResponse", 429)
    assert mobile_delivery.failure(TimeoutError("https://fcm.googleapis.com/fcm/send/secret")) == ("TimeoutError", None)
