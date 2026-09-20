"""Web Push on a real database: migration 038's new constraints, delivery through the real dispatcher, the budget.

Part of tools/qa_mobile_web_push_sql.py; everything here runs inside that script's one rolled-back transaction.
Inside one transaction now() does not move, so a wait is served by moving a row's next attempt back.
"""

import os

import asyncpg

from app import mobile_ack_token as tokens
from app import mobile_alerts as mobile
from app import mobile_delivery as delivery
from app import mobile_vapid
from app import mobile_web_push_store as push_store
from app.mobile_message import message
from app.mobile_policy import Preferences
from qa_mobile_support import new_device, outbox, refused
from qa_web_push_fakes import FakeBrowser
from web_push_receiver import b64

SUBSCRIPTION = "SELECT * FROM mobile_web_push_subscriptions WHERE endpoint = $1"
DUE = "UPDATE mobile_alert_outbox SET next_attempt_at = now() - interval '1 second' WHERE id = $1"


async def schema(conn) -> None:
    device = await new_device(conn, "QA schema web push")
    row = await mobile.enqueue(conn, device, "test", "qa:schema-a")
    other = await mobile.enqueue(conn, device, "test", "qa:schema-b")
    update = "UPDATE mobile_alert_outbox SET {} WHERE id = $1"
    assert await refused(conn, update.format("transport = 'sms'"), row)
    assert await refused(conn, update.format("ack_token_hash = repeat('a', 64)"), row)
    assert await refused(conn, update.format("ack_token_hash = 'not-a-digest', ack_token_expires_at = now()"), row)
    await conn.execute(update.format("ack_token_hash = repeat('b', 64), ack_token_expires_at = now()"), row)
    assert await refused(conn, update.format("ack_token_hash = repeat('b', 64), ack_token_expires_at = now()"), other,
                         error=asyncpg.UniqueViolationError)
    target = FakeBrowser("fcm.googleapis.com", "QA schema")
    subscription = await conn.fetchval(
        "INSERT INTO mobile_web_push_subscriptions (device_id, endpoint, endpoint_digest, p256dh, auth) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        device, target.endpoint, push_store.digest(target.endpoint), target.p256dh, b64(target.auth_secret))
    change = "UPDATE mobile_web_push_subscriptions SET {} WHERE id = $1"
    assert await refused(conn, change.format("expired_at = now()"), subscription)
    assert await refused(conn, change.format("last_status = 99"), subscription)
    assert await refused(conn, change.format("last_error = ''"), subscription)
    await conn.execute("DELETE FROM mobile_alert_outbox WHERE device_id = $1", device)
    print("PASS schema: transport is ntfy or web_push; a tap token digest is 64 hex characters, has an expiry, and is "
          "unique; an expired browser needs a reason; a browser's last result is an HTTP status and a short name")


async def dispatch(pool, conn, event):
    await mobile.dispatch_one(pool)
    return await outbox(conn, event)


async def delivery_through_the_dispatcher(pool, conn, service, provider, client) -> dict:
    device = await new_device(conn, "QA Web Push phone")
    phone, tablet = FakeBrowser("fcm.googleapis.com", "Chrome on Android"), FakeBrowser("web.push.apple.com", "Safari on iOS")
    service.add(phone, tablet)
    for target in (phone, tablet):
        saved = await client.post(f"/state/mobile-alerts/devices/{device}/web-push/subscriptions", json=target.subscription())
        assert saved.status_code == 200 and saved.json()["created"] is True, saved.text

    first = await mobile.enqueue(conn, device, "test", "qa:wp-accepted")
    calls = provider.calls
    row = await dispatch(pool, conn, first)
    assert (row["status"], row["transport"], row["provider_id"], row["attempts"]) == \
        ("provider_accepted", "web_push", "web_push 2/2", 1), dict(row)
    token = phone.shown[-1]["ack"]
    assert tablet.shown[-1]["ack"] == token and row["ack_token_hash"] == tokens.digest(token) != token
    assert (row["ack_token_expires_at"] - row["attempted_at"]).total_seconds() == tokens.LIFETIME_SECONDS
    reference = str(first)[:8]
    assert phone.shown[-1] == {"title": "TradeSync", "body": message("test", first), "tag": f"tradesync-{reference}",
                               "path": "/", "reference": reference, "ack": token}
    for target in (phone, tablet):
        health = await conn.fetchrow(SUBSCRIPTION, target.endpoint)
        assert (health["last_status"], health["expired_at"]) == (201, None) and health["accepted_at"] is not None
    assert provider.calls == calls

    second = await mobile.enqueue(conn, device, "test", "qa:wp-mixed")
    service.plan(phone, 410)
    service.plan(tablet, 503)
    row = await dispatch(pool, conn, second)
    assert (row["status"], row["transport"], row["last_error"]) == ("retry", "web_push", "PushServiceUnavailable"), dict(row)
    gone, busy = await conn.fetchrow(SUBSCRIPTION, phone.endpoint), await conn.fetchrow(SUBSCRIPTION, tablet.endpoint)
    assert gone["last_status"] == 410 and gone["expired_at"] is not None and "HTTP 410" in gone["expired_reason"]
    assert busy["last_status"] == 503 and busy["expired_at"] is None
    await conn.execute(DUE, second)
    posted_to_phone = service.posted[phone.endpoint]
    row = await dispatch(pool, conn, second)
    assert (row["status"], row["provider_id"], row["attempts"]) == ("provider_accepted", "web_push 1/1", 2), dict(row)
    assert service.posted[phone.endpoint] == posted_to_phone, "an expired browser was sent to again"
    second_token = tablet.shown[-1]["ack"]
    assert row["ack_token_hash"] == tokens.digest(second_token) and second_token != token

    third = await mobile.enqueue(conn, device, "attention", "qa:wp-gone")
    service.plan(tablet, 410)
    row = await dispatch(pool, conn, third)
    assert (row["status"], row["last_error"], row["transport"]) == ("retry", "SubscriptionsGone", "web_push"), dict(row)
    await conn.execute(DUE, third)
    requests, calls = service.requests, provider.calls
    row = await dispatch(pool, conn, third)
    assert (row["status"], row["transport"], row["ack_token_hash"]) == ("provider_accepted", "ntfy", None), dict(row)
    assert (service.requests, provider.calls) == (requests, calls + 1)

    revived = await client.post(f"/state/mobile-alerts/devices/{device}/web-push/subscriptions", json=tablet.subscription())
    assert revived.status_code == 200 and revived.json()["created"] is False, revived.text
    assert (await conn.fetchrow(SUBSCRIPTION, tablet.endpoint))["expired_at"] is None
    fourth = await mobile.enqueue(conn, device, "test", "qa:wp-refused")
    service.plan(tablet, 403)
    row = await dispatch(pool, conn, fourth)
    assert (row["status"], row["attempts"], row["transport"]) == ("dead_letter", 1, "web_push"), dict(row)
    assert "HTTP 403" in row["dead_letter_reason"]
    refused_browser = await conn.fetchrow(SUBSCRIPTION, tablet.endpoint)
    assert refused_browser["last_status"] == 403 and refused_browser["expired_at"] is None

    fifth, waits = await mobile.enqueue(conn, device, "test", "qa:wp-ladder"), []
    for attempt in range(1, delivery.MAX_ATTEMPTS + 1):
        service.plan(tablet, 503)
        row = await dispatch(pool, conn, fifth)
        assert row["attempts"] == attempt and row["transport"] == "web_push", dict(row)
        if attempt < delivery.MAX_ATTEMPTS:
            waits.append(round((row["next_attempt_at"] - row["attempted_at"]).total_seconds()))
            await conn.execute(DUE, fifth)
    assert waits == [15, 30, 60, 120] and row["status"] == "dead_letter", (waits, dict(row))
    assert row["dead_letter_reason"] == "No delivery after 5 attempts. Last error PushServiceUnavailable (HTTP 503)."

    contact = os.environ.pop(mobile_vapid.SUBJECT_ENV)
    try:
        sixth = await mobile.enqueue(conn, device, "test", "qa:wp-no-contact")
        requests, calls = service.requests, provider.calls
        row = await dispatch(pool, conn, sixth)
        assert (row["status"], row["transport"]) == ("provider_accepted", "ntfy"), dict(row)
        assert (service.requests, provider.calls) == (requests, calls + 1)
    finally:
        os.environ[mobile_vapid.SUBJECT_ENV] = contact
    assert service.sizes == {86 + 512 + 16}, service.sizes
    print("PASS delivery: two browsers sealed and signed separately, one generic payload and one token stored as its "
          "digest; 410 expires a browser with its reason and it is never sent to again, 503 retried, a retry reaching "
          "the browser left; every browser gone falls back to ntfy; re-subscribing revives; 403 dead-lettered at once; "
          "503 five times waits 15, 30, 60, 120s then dead-letters; no contact means ntfy; every push 614 octets")
    return {"device": device, "tablet": tablet, "first": first, "first_token": token,
            "second": second, "second_token": second_token}


async def budget(pool, conn, service, delivered) -> dict:
    device, tablet = delivered["device"], delivered["tablet"]
    before = await mobile.budget_used(conn, device)
    alert = await mobile.enqueue(conn, device, "attention", "qa:wp-budget")
    row = await dispatch(pool, conn, alert)
    assert (row["status"], row["transport"]) == ("provider_accepted", "web_push"), dict(row)
    used = await mobile.budget_used(conn, device)
    assert used == before + 1
    requests = service.requests
    spent = Preferences(quiet_enabled=False, daily_budget=used)
    assert await mobile.queue_or_suppress(conn, device, "qa:wp-budget-over", spent, used) == used
    over = await conn.fetchrow("SELECT * FROM mobile_alert_outbox WHERE device_id = $1 AND dedupe_key = 'qa:wp-budget-over'", device)
    assert (over["status"], over["last_error"], over["transport"], over["attempts"]) == ("expired", "BudgetSuppressed", None, 0)
    await mobile.dispatch_one(pool)
    assert service.requests == requests
    print(f"PASS budget: an alert carried by Web Push counts against the phone's budget ({before} to {used}), and the "
          "next one over it is suppressed before any push is made")
    return {"third": alert, "third_token": tablet.shown[-1]["ack"]}
