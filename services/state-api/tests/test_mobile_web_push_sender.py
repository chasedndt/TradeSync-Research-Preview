"""One Web Push attempt: sealed per browser, signed per push service, generic on the lock screen, and judged honestly.

No request leaves the process: ``post`` is replaced by a fake push service that checks the VAPID signature and
opens the message with the browser's own private key, the way a real push service and browser would.
"""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from Crypto.PublicKey import ECC

from app import mobile_ack_token, mobile_delivery, mobile_vapid
from app import mobile_web_push_sender as sender
from app.mobile_message import message
from web_push_receiver import b64, browser, decrypt, verify_vapid

EVENT = uuid.UUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301")
SUBJECT = "mailto:operator@example.invalid"
_SERVER = ECC.generate(curve="P-256")
PUBLIC, PRIVATE = b64(_SERVER.public_key().export_key(format="raw")), b64(int(_SERVER.d).to_bytes(32, "big"))


def keys():
    return patch.dict("os.environ", {mobile_vapid.PUBLIC_ENV: PUBLIC, mobile_vapid.PRIVATE_ENV: PRIVATE,
                                     mobile_vapid.SUBJECT_ENV: SUBJECT})


def subscription(host="fcm.googleapis.com"):
    key, p256dh, auth = browser()
    row = {"id": uuid.uuid4(), "endpoint": f"https://{host}/fcm/send/{uuid.uuid4().hex}", "endpoint_digest": "d" * 12,
           "p256dh": p256dh, "auth": b64(auth)}
    return row, key, auth


class PushService:
    """Accepts, refuses or loses each push as planned, after checking it as a real push service would."""

    def __init__(self, *answers):
        self.answers, self.received = list(answers), []

    async def __call__(self, endpoint, body, headers):
        origin = "https://" + endpoint.split("/")[2]
        self.received.append({"endpoint": endpoint, "body": body, "headers": headers,
                              "claims": verify_vapid(headers["Authorization"], origin, time.time())})
        answer = self.answers.pop(0) if self.answers else 201
        if isinstance(answer, BaseException):
            raise answer
        return answer


class Pool:
    def __init__(self):
        self.executed = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def run(coroutine):
    return asyncio.run(coroutine)


def test_the_payload_is_the_ntfy_sentence_a_reference_a_path_and_the_tap_token_and_nothing_else():
    token = mobile_ack_token.new_token()
    body = json.loads(sender.payload("attention", EVENT, token))
    assert body == {"title": "TradeSync", "body": message("attention", EVENT), "tag": "tradesync-3f2504e0",
                    "path": "/", "reference": "3f2504e0", "ack": token}
    assert len(token) == 43 and mobile_ack_token.well_formed(token)


def test_a_browser_opens_what_it_is_sent_and_every_push_is_the_same_size():
    row, key, auth = subscription()
    service = PushService(201, 201)
    with keys(), patch.object(sender, "post", service):
        for kind in ("test", "attention"):
            result = run(sender.attempt(row, sender.payload(kind, EVENT, "a" * 43), SUBJECT, PUBLIC,
                                        mobile_vapid.signing_key()))
            assert result == sender.Result(sender.ACCEPTED, 201)
    test, attention = service.received
    assert len(test["body"]) == len(attention["body"]) == 86 + sender.PADDED_BYTES + 16
    assert json.loads(decrypt(attention["body"], key, auth))["body"] == message("attention", EVENT)
    assert attention["claims"]["aud"] == "https://fcm.googleapis.com" and attention["claims"]["sub"] == SUBJECT
    assert attention["headers"]["Content-Encoding"] == "aes128gcm" and attention["headers"]["Urgency"] == "high"
    assert attention["headers"]["TTL"] == str(mobile_delivery.EXPIRY_SECONDS) == "600"


@pytest.mark.parametrize("status,outcome,error", [
    (201, "accepted", None), (202, "accepted", None), (404, "gone", "SubscriptionGone"), (410, "gone", "SubscriptionGone"),
    (429, "retry", "PushServiceRateLimited"), (500, "retry", "PushServiceUnavailable"),
    (503, "retry", "PushServiceUnavailable"), (400, "refused", "PushServiceRefused"),
    (401, "refused", "PushServiceRefused"), (403, "refused", "PushServiceRefused"),
    (413, "refused", "PushServiceRefused"), (301, "refused", "PushServiceRefused"),
])
def test_each_answer_from_a_push_service_means_one_thing(status, outcome, error):
    result = sender.classify(status)
    assert (result.outcome, result.status, result.error) == (outcome, status, error)
    assert (result.reason is not None) == (outcome == "gone")
    if outcome == "gone":
        assert f"HTTP {status}" in result.reason and "https://" not in result.reason


def test_an_unknown_push_service_or_an_unusable_key_is_never_posted_to():
    service = PushService()
    unknown, _, _ = subscription(host="push.example.invalid")
    broken, _, _ = subscription()
    broken["p256dh"] = b64(bytes([4]) + bytes(range(64)))
    with keys(), patch.object(sender, "post", service):
        key = mobile_vapid.signing_key()
        assert run(sender.attempt(unknown, b"{}", SUBJECT, PUBLIC, key)) is sender.NOT_ALLOWED
        assert run(sender.attempt(broken, b"{}", SUBJECT, PUBLIC, key)) is sender.UNUSABLE_KEY
    assert service.received == []


def test_a_lost_connection_is_worth_retrying_but_cancellation_is_not_swallowed():
    row, _, _ = subscription()
    with keys():
        key = mobile_vapid.signing_key()
        with patch.object(sender, "post", PushService(TimeoutError("private detail"))):
            assert run(sender.attempt(row, b"{}", SUBJECT, PUBLIC, key)) == sender.Result("retry", None, "TimeoutError")
        with patch.object(sender, "post", AsyncMock(side_effect=asyncio.CancelledError)), pytest.raises(asyncio.CancelledError):
            run(sender.attempt(row, b"{}", SUBJECT, PUBLIC, key))


def test_the_row_is_accepted_when_any_browser_accepted_and_otherwise_fails_as_hopefully_as_the_answers_allow():
    accepted, retry, refused, gone = (sender.classify(201), sender.classify(503), sender.classify(403),
                                      sender.classify(410))
    assert sender.summary([gone, accepted, refused]) == "web_push 1/3"
    for results, name, status in (([refused, retry, gone], "PushServiceUnavailable", 503),
                                  ([gone, refused], "PushServiceRefused", 403)):
        with pytest.raises(sender.WebPushUndelivered) as failed:
            sender.summary(results)
        assert mobile_delivery.failure(failed.value) == (name, status)
    with pytest.raises(sender.WebPushUndelivered) as all_gone:
        sender.summary([gone, sender.UNUSABLE_KEY])
    assert mobile_delivery.failure(all_gone.value) == ("SubscriptionsGone", None)
    # Through the delivery policy: a 4xx refusal is a dead letter at once, the rest are retried.
    assert mobile_delivery.outcome(1, "PushServiceRefused", 403).status == "dead_letter"
    assert mobile_delivery.outcome(1, "PushServiceUnavailable", 503).status == "retry"
    assert mobile_delivery.outcome(1, "SubscriptionsGone", None).status == "retry"
    # A redirect is never followed and counts as refused, but it is not final: tried again until the attempts run out.
    assert sender.classify(301).outcome == sender.REFUSED
    assert mobile_delivery.outcome(1, "PushServiceRefused", 301).status == "retry"
    assert mobile_delivery.outcome(mobile_delivery.MAX_ATTEMPTS, "PushServiceRefused", 301).status == "dead_letter"


def test_every_browser_gets_its_own_sealed_copy_and_its_own_result_and_a_gone_one_is_expired_with_its_reason():
    (first, first_key, first_auth), (second, _, _) = subscription(), subscription(host="web.push.apple.com")
    pool, service = Pool(), PushService(201, 410)
    with keys(), patch.object(sender, "post", service):
        assert run(sender.deliver(pool, [first, second], "test", EVENT, "b" * 43)) == "web_push 1/2"
    assert {item["claims"]["aud"] for item in service.received} == {"https://fcm.googleapis.com", "https://web.push.apple.com"}
    opened = json.loads(decrypt(service.received[0]["body"], first_key, first_auth))
    assert opened["ack"] == "b" * 43 and opened["body"] == message("test", EVENT)
    (_, accepted), (_, expired) = pool.executed
    assert accepted == (first["id"], 201, None, True, None)
    assert expired[:4] == (second["id"], 410, "SubscriptionGone", False) and "HTTP 410" in expired[4]
    recorded = json.dumps([list(map(str, args)) for _, args in pool.executed])
    assert PRIVATE not in recorded and first["endpoint"] not in recorded


def test_posting_follows_no_redirect_and_reads_no_proxy_settings():
    response = MagicMock(status_code=201)
    with patch("app.mobile_web_push_sender.httpx.AsyncClient") as factory:
        client = MagicMock(post=AsyncMock(return_value=response))
        factory.return_value.__aenter__.return_value = client
        assert run(sender.post("https://fcm.googleapis.com/fcm/send/x", b"sealed", {"TTL": "600"})) == 201
    assert factory.call_args.kwargs == {"timeout": sender.TIMEOUT_SECONDS, "trust_env": False, "follow_redirects": False}
    assert client.post.call_args.kwargs == {"content": b"sealed", "headers": {"TTL": "600"}}
