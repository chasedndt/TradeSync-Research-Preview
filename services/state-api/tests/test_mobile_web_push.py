"""The VAPID public key is served, the private key never leaves the environment, and a subscription is recorded.

Nothing here sends a notification; app/mobile_web_push_sender.py does, and test_mobile_web_push_sender.py covers it.
"""

import base64
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from Crypto.PublicKey import ECC
from fastapi.testclient import TestClient

from app import mobile_vapid as vapid
from app import mobile_web_push as web_push
from app import mobile_web_push_store as store
from app.main import app, state

KEY = "k" * 40
WHEN = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
ENDPOINT = "https://fcm.googleapis.com/fcm/send/this-part-is-a-capability-token"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# A real key pair and a real browser key, made in memory for this run: the pair check refuses invented bytes.
_SERVER, _BROWSER = ECC.generate(curve="P-256"), ECC.generate(curve="P-256")
PUBLIC = b64(_SERVER.public_key().export_key(format="raw"))
PRIVATE = b64(int(_SERVER.d).to_bytes(32, "big"))
P256DH = b64(_BROWSER.public_key().export_key(format="raw"))
AUTH = b64(bytes(range(16)))


@asynccontextmanager
async def nothing():
    yield


class Pool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def keys(public=PUBLIC, private=PRIVATE):
    return patch.dict("os.environ", {vapid.PUBLIC_ENV: public, vapid.PRIVATE_ENV: private})


def test_the_key_pair_is_87_and_43_characters_as_a_browser_and_a_sender_need_them():
    assert len(PUBLIC) == 87 and len(PRIVATE) == 43
    assert vapid.decode(PUBLIC, vapid.PUBLIC_KEY_BYTES) is not None
    assert vapid.decode(PRIVATE, vapid.PRIVATE_KEY_BYTES) is not None
    assert vapid.decode(PRIVATE, vapid.PUBLIC_KEY_BYTES) is None


def test_without_a_key_pair_the_status_says_so_and_nothing_pretends_to_work():
    with keys("", ""):
        body = TestClient(app).get("/state/mobile-alerts/web-push").json()
    assert body["configured"] is False and body["public_key"] is None
    assert body["public_key_state"] == "missing" and body["private_key_state"] == "missing"
    assert vapid.PUBLIC_ENV in body["problem"] and "cannot subscribe" in body["problem"]
    assert body["sender_implemented"] is True and body["sender_ready"] is False and "ntfy" in body["delivery"]
    assert body["sender_problem"] == body["problem"]


def test_the_public_key_is_served_and_the_private_key_is_never_in_an_answer():
    with keys():
        body = TestClient(app).get("/state/mobile-alerts/web-push").json()
        assert vapid.private_key_state() == "ok" and vapid.configured() is True
    assert body["configured"] is True and body["public_key"] == PUBLIC and body["problem"] is None
    assert body["private_key_state"] == "ok"
    assert PRIVATE not in json.dumps(body)


def test_a_malformed_key_is_reported_without_repeating_the_value():
    with keys("not-a-real-vapid-key", PRIVATE):
        body = TestClient(app).get("/state/mobile-alerts/web-push").json()
    assert body["configured"] is False and body["public_key"] is None
    assert body["public_key_state"] == "malformed" and "87 characters" in body["problem"]
    assert "not-a-real-vapid-key" not in json.dumps(body)

    with keys(PUBLIC, "short"):
        body = TestClient(app).get("/state/mobile-alerts/web-push").json()
    assert body["configured"] is False and body["private_key_state"] == "malformed"
    assert "43 characters" in body["problem"] and "short" not in json.dumps(body).replace("shorter", "")


def test_a_public_key_that_is_not_an_uncompressed_point_is_refused():
    with keys(b64(bytes([2]) + bytes(range(64))), PRIVATE):
        assert vapid.public_key() is None and vapid.configured() is False


def test_subscription_routes_fail_closed_without_the_control_key():
    client, device, subscription = TestClient(app), uuid.uuid4(), uuid.uuid4()
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": ""}):
        assert client.get("/state/mobile-alerts/web-push/subscriptions").status_code == 503
        assert client.post(f"/state/mobile-alerts/devices/{device}/web-push/subscriptions",
                           json={"endpoint": ENDPOINT}).status_code == 503
        assert client.delete(f"/state/mobile-alerts/web-push/subscriptions/{subscription}").status_code == 503
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        wrong = {"X-API-Key": "wrong"}
        assert client.get("/state/mobile-alerts/web-push/subscriptions", headers=wrong).status_code == 403
        assert client.delete(f"/state/mobile-alerts/web-push/subscriptions/{subscription}",
                             headers=wrong).status_code == 403


def test_an_endpoint_must_be_https_public_and_carry_no_credentials():
    assert web_push.checked_endpoint(f"  {ENDPOINT}  ") == ENDPOINT
    for bad in ("http://fcm.googleapis.com/fcm/send/abcdefghijklmno",
                "https://user:secret@fcm.googleapis.com/fcm/send/abcdefghij",
                "https://127.0.0.1/fcm/send/abcdefghijklmnop",
                "https://localhost/fcm/send/abcdefghijklmnopqr",
                "https://[::1]/fcm/send/abcdefghijklmnopqrst",
                "https://box.local/fcm/send/abcdefghijklmnopqr",
                "https://a.b/x", "", "x" * 2100):
        with pytest.raises(ValueError):
            web_push.checked_endpoint(bad)


def test_the_browsers_two_public_values_must_be_the_right_shape():
    assert web_push.checked_material(f" {P256DH} ", f" {AUTH} ") == (P256DH, AUTH)
    for p256dh, auth in ((AUTH, AUTH), (P256DH, P256DH), ("", AUTH), (P256DH, "")):
        with pytest.raises(ValueError):
            web_push.checked_material(p256dh, auth)


def test_a_subscription_is_shown_by_its_push_service_and_a_digest_never_as_a_url():
    row = {"id": uuid.UUID(int=1), "device_id": uuid.UUID(int=2), "device_label": "My phone", "platform": "ios",
           "device_enabled": True, "endpoint": ENDPOINT, "endpoint_digest": store.digest(ENDPOINT),
           "label": "iPhone Safari", "created_at": WHEN, "last_seen_at": WHEN}
    shown = json.dumps(store.display(row))
    assert "this-part-is-a-capability-token" not in shown and ENDPOINT not in shown
    assert store.display(row)["push_service"] == "fcm.googleapis.com"
    assert store.display(row)["created_at"] == "2026-09-16T12:00:00+00:00"
    assert len(store.digest(ENDPOINT)) == 12 and store.digest(ENDPOINT) == store.digest(ENDPOINT)
    assert store.digest(ENDPOINT) != store.digest(ENDPOINT + "x")


class SubscribeConn:
    """Answers the subscribe route: the device is enabled, it has no browsers yet, and the row is saved."""

    def __init__(self, existing=0):
        self.existing, self.saved, self.counted = existing, [], []

    def transaction(self):
        return nothing()

    async def fetchval(self, sql, *args):
        if "count(*)" in sql:
            self.counted.append(args)
            return self.existing
        return True

    async def fetchrow(self, sql, *args):
        self.saved.append(args)
        return {"id": uuid.UUID(int=5), "device_id": args[0], "endpoint_digest": args[2], "label": args[5],
                "created_at": WHEN, "last_seen_at": WHEN, "inserted": True}


def subscribe(conn, monkeypatch, body=None):
    monkeypatch.setattr(state, "pool", Pool(conn))
    return TestClient(app).post(f"/state/mobile-alerts/devices/{uuid.uuid4()}/web-push/subscriptions",
                                json=body or {"endpoint": ENDPOINT, "keys": {"p256dh": P256DH, "auth": AUTH},
                                              "label": "iPhone Safari"},
                                headers={"X-API-Key": KEY})


def test_subscribing_is_refused_while_no_key_pair_is_configured(monkeypatch):
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), keys("", ""):
        refused = subscribe(SubscribeConn(), monkeypatch)
    assert refused.status_code == 503 and vapid.PUBLIC_ENV in refused.json()["detail"]


def test_a_recorded_subscription_returns_a_digest_and_says_where_alerts_now_go(monkeypatch):
    conn = SubscribeConn()
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), keys():
        answer = subscribe(conn, monkeypatch)
    body = answer.json()
    assert answer.status_code == 200 and body["status"] == "subscription_recorded"
    assert body["endpoint_digest"] == store.digest(ENDPOINT) and body["push_service"] == "fcm.googleapis.com"
    assert "instead of the ntfy app" in body["note"] and "goes back to ntfy" in body["note"]
    assert ENDPOINT not in json.dumps(body)
    # The endpoint is stored whole, with its digest beside it, and the browser's values unchanged.
    assert conn.saved[0][1:] == (ENDPOINT, store.digest(ENDPOINT), P256DH, AUTH, "iPhone Safari")
    # The limit counts the phone's other active browsers, so this browser re-subscribing is never refused.
    assert conn.counted[0][1] == ENDPOINT and "expired_at IS NULL" in store.COUNT_SQL


def test_a_malformed_subscription_is_refused_before_anything_is_stored(monkeypatch):
    conn = SubscribeConn()
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), keys():
        refused = subscribe(conn, monkeypatch, {"endpoint": "http://example.com/push/abcdefghij",
                                                "keys": {"p256dh": P256DH, "auth": AUTH}})
    assert refused.status_code == 422 and conn.saved == []


def test_one_phone_cannot_accumulate_unlimited_browsers(monkeypatch):
    conn = SubscribeConn(existing=web_push.MAX_PER_DEVICE)
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}), keys():
        refused = subscribe(conn, monkeypatch)
    assert refused.status_code == 409 and conn.saved == []


class RemoveConn:
    def __init__(self, digest):
        self.digest = digest

    async def fetchval(self, sql, *args):
        return self.digest


def test_removing_a_subscription_that_is_not_there_is_a_plain_404(monkeypatch):
    monkeypatch.setattr(state, "pool", Pool(RemoveConn(None)))
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        missing = TestClient(app).delete(f"/state/mobile-alerts/web-push/subscriptions/{uuid.uuid4()}",
                                         headers={"X-API-Key": KEY})
    assert missing.status_code == 404

    monkeypatch.setattr(state, "pool", Pool(RemoveConn("0123456789ab")))
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": KEY}):
        removed = TestClient(app).delete(f"/state/mobile-alerts/web-push/subscriptions/{uuid.uuid4()}",
                                         headers={"X-API-Key": KEY})
    assert removed.status_code == 200 and removed.json()["endpoint_digest"] == "0123456789ab"


def test_only_the_push_services_browsers_use_are_accepted_and_a_lookalike_host_is_not():
    for host in ("web.push.apple.com", "updates.push.services.mozilla.com", "wns2-par02p.notify.windows.com"):
        assert web_push.checked_endpoint(f"https://{host}/push/abcdefghijklmnop") == f"https://{host}/push/abcdefghijklmnop"
    for host in ("push.example.invalid", "notify.windows.com.evil.invalid", "fcm.googleapis.com.evil.invalid",
                 "evilfcm.googleapis.com"):
        with pytest.raises(ValueError, match="not a push service TradeSync sends to"):
            web_push.checked_endpoint(f"https://{host}/push/abcdefghijklmnop")


def test_a_browser_key_that_is_not_on_the_curve_is_refused_before_it_is_stored():
    with pytest.raises(ValueError, match="not a P-256 public key"):
        web_push.checked_material(b64(bytes([4]) + bytes(range(64))), AUTH)


def test_the_public_key_is_withheld_while_the_pair_does_not_match_and_the_contact_is_reported_only_by_state():
    stranger = ECC.generate(curve="P-256")
    with keys(PUBLIC, b64(int(stranger.d).to_bytes(32, "big"))):
        mismatched = TestClient(app).get("/state/mobile-alerts/web-push").json()
    assert mismatched["configured"] is False and mismatched["public_key"] is None
    assert "not the two halves of one key pair" in mismatched["problem"]

    contact = "mailto:operator@example.invalid"
    with keys(), patch.dict("os.environ", {vapid.SUBJECT_ENV: ""}):
        waiting = TestClient(app).get("/state/mobile-alerts/web-push").json()
    with keys(), patch.dict("os.environ", {vapid.SUBJECT_ENV: contact}):
        ready = TestClient(app).get("/state/mobile-alerts/web-push")
    assert waiting["configured"] is True and waiting["sender_ready"] is False and waiting["subject_state"] == "missing"
    assert vapid.SUBJECT_ENV in waiting["sender_problem"] and "Apple" in waiting["sender_problem"]
    assert ready.json()["sender_ready"] is True and ready.json()["sender_problem"] is None
    assert ready.json()["subject_state"] == "ok" and contact not in ready.text and "operator@" not in ready.text


def test_a_subscription_shows_the_result_of_its_last_push_and_whether_it_expired():
    row = {"id": uuid.UUID(int=1), "device_id": uuid.UUID(int=2), "endpoint": ENDPOINT,
           "endpoint_digest": store.digest(ENDPOINT), "created_at": WHEN, "last_seen_at": WHEN, "last_attempt_at": WHEN,
           "last_status": 410, "last_error": "SubscriptionGone", "accepted_at": None, "expired_at": WHEN,
           "expired_reason": "The push service answered HTTP 410: this subscription no longer exists."}
    shown = store.display(row)
    assert shown["active"] is False and shown["last_status"] == 410 and shown["expired_at"] == WHEN.isoformat()
    assert shown["expired_reason"].startswith("The push service answered HTTP 410")
    assert store.display({**row, "expired_at": None, "expired_reason": None})["active"] is True
    assert ENDPOINT not in json.dumps(shown)
