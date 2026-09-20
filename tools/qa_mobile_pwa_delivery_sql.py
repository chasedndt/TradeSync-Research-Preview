"""Real-SQL acceptance for the mobile PWA and delivery-reliability branch, on a THROWAWAY PostgreSQL only.

The database must have ops/sql/schema.sql and every migration through 038 applied (ops/apply_schema.py), and no
mobile outbox rows of its own. The script refuses the compose PostgreSQL port (5432) and a database named
tradesync. Everything runs inside one transaction that is rolled back at the end, whatever happens.

No request leaves the process. ntfy publishing is replaced by a local fake, and any HTTP client that is not an
in-process ASGI client refuses to be built. The Web Push checks use a P-256 key pair and a browser key made in
memory for this run and discarded with it; nothing is written anywhere. Sending over Web Push and tapping a
notification are covered by tools/qa_mobile_web_push_sql.py.

Covers migration 038's constraints; bounded retries through the real dispatcher (15, 30, 60, 120 seconds, five
attempts, then a dead letter with its reason; a 404 dead-lettered at once; a 429 retried; the sweep dead-lettering
exhausted rows and leaving one inside its lease alone); the operator's acknowledgement and the ledger through the real routes; and
Web Push subscriptions through the real routes (refused with no key pair, one row per browser, moved rather than
doubled, capped per phone, listed without the endpoint, removed).

    python tools/qa_mobile_pwa_delivery_sql.py --dsn postgresql://qa:qa@127.0.0.1:55461/tradesync_qa
"""

import argparse
import asyncio
import os
import secrets
import sys
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import httpx
from Crypto.PublicKey import ECC
from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))
sys.path.insert(0, str(ROOT / "services" / "state-api"))

# First, so the no-egress guard is installed before anything could build an HTTP client.
from qa_mobile_support import KEY, Pool, Provider, ProviderRefusal, b64, new_device, outbox, refused  # noqa: E402
from qa_mobile_support import throwaway_connection  # noqa: E402

from app import mobile_alerts as mobile  # noqa: E402
from app import mobile_delivery as delivery  # noqa: E402
from app import mobile_ledger, mobile_vapid, mobile_web_push  # noqa: E402
from app import mobile_web_push_store as push_store  # noqa: E402


async def schema(conn) -> None:
    device = await new_device(conn, "QA schema")
    await conn.execute("UPDATE mobile_alert_devices SET enabled = false WHERE id = $1", device)
    insert = ("INSERT INTO mobile_alert_outbox (id, device_id, dedupe_key, kind, status, expires_at, dead_lettered_at, "
              "dead_letter_reason, acknowledged_at, acknowledged_by) VALUES ($1, $2, $3, 'test', $4, now(), $5, $6, $7, $8)")
    await conn.execute(insert, uuid.uuid4(), device, "qa:dead", "dead_letter", datetime.now().astimezone(), "qa reason", None, None)
    await conn.execute(insert, uuid.uuid4(), device, "qa:legacy", "failed", None, None, None, None)
    now = datetime.now().astimezone()
    assert await refused(conn, insert, uuid.uuid4(), device, "qa:bad-status", "nonsense", None, None, None, None)
    assert await refused(conn, insert, uuid.uuid4(), device, "qa:no-reason", "dead_letter", now, None, None, None)
    assert await refused(conn, insert, uuid.uuid4(), device, "qa:ack-no-who", "provider_accepted", None, None, now, None)
    assert await refused(conn, insert, uuid.uuid4(), device, "qa:ack-bad-who", "provider_accepted", None, None, now, "someone")
    push = ("INSERT INTO mobile_web_push_subscriptions (device_id, endpoint, endpoint_digest, p256dh, auth) "
            "VALUES ($1, $2, $3, $4, $5)")
    p256dh, auth = b64(bytes([4]) + secrets.token_bytes(64)), b64(secrets.token_bytes(16))
    endpoint = "https://fcm.googleapis.com/fcm/send/qa-schema-" + secrets.token_hex(12)
    assert await refused(conn, push, device, endpoint.replace("https", "http"), "0123456789ab", p256dh, auth)
    assert await refused(conn, push, device, endpoint, "NOT-A-DIGEST", p256dh, auth)
    await conn.execute(push, device, endpoint, push_store.digest(endpoint), p256dh, auth)
    assert await refused(conn, push, device, endpoint, push_store.digest(endpoint), p256dh, auth,
                         error=asyncpg.UniqueViolationError)
    print("PASS schema: dead_letter status with a reason, legacy 'failed' still valid, unknown status refused, a dead "
          "letter without a reason refused, an acknowledgement needs who and when, push endpoints HTTPS and unique")


async def retries(pool, conn, provider) -> uuid.UUID:
    device = await new_device(conn, "QA retries")
    ladder = await mobile.enqueue(conn, device, "test", "qa:retry-ladder")
    waits = []
    for attempt in range(1, delivery.MAX_ATTEMPTS + 1):
        provider.plan.append(TimeoutError("qa: the provider did not answer"))
        await mobile.dispatch_one(pool)
        row = await outbox(conn, ladder)
        assert row["attempts"] == attempt and row["lease_until"] is None and row["last_error"] == "TimeoutError", dict(row)
        if attempt < delivery.MAX_ATTEMPTS:
            assert row["status"] == "retry" and row["dead_lettered_at"] is None, dict(row)
            waits.append(round((row["next_attempt_at"] - row["attempted_at"]).total_seconds()))
            # now() does not move inside one transaction, so the wait is served by moving the row's time back.
            await conn.execute("UPDATE mobile_alert_outbox SET next_attempt_at = now() - interval '1 second' WHERE id = $1", ladder)
    assert waits == [15, 30, 60, 120], waits
    assert row["status"] == "dead_letter" and row["dead_lettered_at"] is not None, dict(row)
    assert row["dead_letter_reason"] == "No delivery after 5 attempts. Last error TimeoutError.", row["dead_letter_reason"]
    calls = provider.calls
    await mobile.dispatch_one(pool)
    assert provider.calls == calls, "a dead letter was attempted again"

    not_found = await mobile.enqueue(conn, device, "test", "qa:refused")
    provider.plan.append(ProviderRefusal(404))
    await mobile.dispatch_one(pool)
    row = await outbox(conn, not_found)
    assert row["status"] == "dead_letter" and row["attempts"] == 1 and "HTTP 404" in row["dead_letter_reason"], dict(row)

    limited = await mobile.enqueue(conn, device, "test", "qa:rate-limited")
    provider.plan.append(ProviderRefusal(429))
    await mobile.dispatch_one(pool)
    row = await outbox(conn, limited)
    assert row["status"] == "retry" and row["dead_lettered_at"] is None, dict(row)
    park = "UPDATE mobile_alert_outbox SET next_attempt_at = now() + interval '1 hour' WHERE id = $1"
    await conn.execute(park, limited)

    exhausted = await mobile.enqueue(conn, device, "test", "qa:exhausted")
    inflight = await mobile.enqueue(conn, device, "test", "qa:in-flight")
    lapsed = await mobile.enqueue(conn, device, "test", "qa:lapsed")
    await conn.execute("UPDATE mobile_alert_outbox SET status = 'retry', attempts = 5, next_attempt_at = now() + interval '1 hour' WHERE id = $1", exhausted)
    await conn.execute("UPDATE mobile_alert_outbox SET status = 'sending', attempts = 5, lease_until = now() + interval '60 seconds' WHERE id = $1", inflight)
    await conn.execute("UPDATE mobile_alert_outbox SET status = 'sending', attempts = 5, lease_until = now() - interval '1 second' WHERE id = $1", lapsed)
    calls = provider.calls
    await mobile.dispatch_one(pool)
    assert provider.calls == calls
    assert (await outbox(conn, exhausted))["dead_letter_reason"] == delivery.EXHAUSTED_SWEEP_REASON
    assert (await outbox(conn, lapsed))["status"] == "dead_letter"
    assert (await outbox(conn, inflight))["status"] == "sending", "a row inside its lease was swept"
    print(f"PASS retries: waits {waits}s, dead letter after {delivery.MAX_ATTEMPTS} attempts with its reason and never "
          "tried again; 404 dead-lettered at once; 429 retried; exhausted and lapsed rows dead-lettered by the sweep, "
          "a row inside its lease left alone")
    return ladder


async def acknowledgements(pool, conn, provider, dead_letter) -> None:
    app = FastAPI()
    mobile.register(app, SimpleNamespace(pool=pool))
    mobile_ledger.register(app, SimpleNamespace(pool=pool))
    device = await new_device(conn, "QA acknowledgements")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa", headers={"X-API-Key": KEY}) as client:
        waiting = await mobile.enqueue(conn, device, "test", "qa:ack-waiting")
        await conn.execute("UPDATE mobile_alert_outbox SET next_attempt_at = now() + interval '1 hour' WHERE id = $1", waiting)
        early = await client.post(f"/state/mobile-alerts/events/{waiting}/acknowledge", json={"by": "operator"})
        assert early.status_code == 409, early.text

        seen = await mobile.enqueue(conn, device, "test", "qa:ack-operator")
        await mobile.dispatch_one(pool)
        assert (await outbox(conn, seen))["status"] == "provider_accepted"
        # A phone acknowledges by tapping, with its token; this route cannot claim to be one.
        claimed = await client.post(f"/state/mobile-alerts/events/{seen}/acknowledge", json={"by": "device"})
        assert claimed.status_code == 422 and (await outbox(conn, seen))["acknowledged_at"] is None, claimed.text
        first = await client.post(f"/state/mobile-alerts/events/{seen}/acknowledge", json={"by": "operator"})
        assert first.status_code == 200 and first.json()["outcome"] == "acknowledged", first.text
        second = await client.post(f"/state/mobile-alerts/events/{seen}/acknowledge", json={"by": "operator"})
        assert second.json()["outcome"] == "already_acknowledged", second.text
        assert second.json()["acknowledged_at"] == first.json()["acknowledged_at"], second.text
        row = await outbox(conn, seen)
        assert row["acknowledged_by"] == "operator" and row["status"] == "provider_accepted", dict(row)

        attested = await mobile.enqueue(conn, device, "test", "qa:ack-attested")
        await mobile.dispatch_one(pool)
        confirm = await client.post(f"/state/mobile-alerts/events/{attested}/confirm")
        assert confirm.status_code == 200, confirm.text
        row = await outbox(conn, attested)
        assert row["status"] == "operator_confirmed" and row["acknowledged_by"] == "operator", dict(row)
        assert row["acknowledged_at"] == row["confirmed_at"], dict(row)

        ledger = await client.get("/state/mobile-alerts/ledger?limit=200")
        assert ledger.status_code == 200, ledger.text
        body = ledger.json()
        events = {event["id"]: event for event in body["events"]}
        assert events[str(seen)]["acknowledged_by"] == "operator" and datetime.fromisoformat(events[str(seen)]["accepted_at"])
        assert events[str(seen)]["transport"] == "ntfy"
        assert events[str(dead_letter)]["dead_letter_reason"].startswith("No delivery after 5 attempts")
        assert events[str(dead_letter)]["device_label"] == "QA retries"
        assert body["retry_seconds"] == [15, 30, 60, 120] and body["max_attempts"] == 5
    print("PASS acknowledgement: refused before any attempt, a device claim refused on the control route, the "
          "operator's first one kept, the attestation recording it in the same statement; the ledger returns "
          "reasons, labels, the transport and exact ISO times")


async def web_push(pool, conn) -> None:
    app = FastAPI()
    mobile_web_push.register(app, SimpleNamespace(pool=pool))
    one, two = await new_device(conn, "QA phone one"), await new_device(conn, "QA phone two")
    server, browser_key = ECC.generate(curve="P-256"), ECC.generate(curve="P-256")
    public = b64(server.public_key().export_key(format="raw"))
    private = b64(int(server.d).to_bytes(32, "big"))
    p256dh, auth = b64(browser_key.public_key().export_key(format="raw")), b64(secrets.token_bytes(16))
    endpoint = "https://fcm.googleapis.com/fcm/send/qa-" + secrets.token_hex(24)
    body = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}, "label": "QA browser"}
    count = "SELECT count(*) FROM mobile_web_push_subscriptions WHERE endpoint LIKE 'https://fcm.googleapis.com/fcm/send/qa-%' AND endpoint NOT LIKE '%qa-schema-%'"
    for name in (mobile_vapid.PUBLIC_ENV, mobile_vapid.PRIVATE_ENV, mobile_vapid.SUBJECT_ENV):
        os.environ.pop(name, None)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa", headers={"X-API-Key": KEY}) as client:
            status = (await client.get("/state/mobile-alerts/web-push")).json()
            assert status["configured"] is False and status["public_key"] is None and mobile_vapid.PUBLIC_ENV in status["problem"]
            subscribe = f"/state/mobile-alerts/devices/{one}/web-push/subscriptions"
            assert (await client.post(subscribe, json=body)).status_code == 503
            assert await conn.fetchval(count) == 0

            os.environ[mobile_vapid.PUBLIC_ENV], os.environ[mobile_vapid.PRIVATE_ENV] = public, private
            status = await client.get("/state/mobile-alerts/web-push")
            assert status.json()["configured"] is True and status.json()["public_key"] == public and private not in status.text
            first = await client.post(subscribe, json=body)
            assert first.status_code == 200 and first.json()["created"] is True, first.text
            assert first.json()["endpoint_digest"] == push_store.digest(endpoint) and endpoint not in first.text
            again = await client.post(subscribe, json=body)
            assert again.status_code == 200 and again.json()["created"] is False, again.text
            moved = await client.post(f"/state/mobile-alerts/devices/{two}/web-push/subscriptions", json=body)
            assert moved.status_code == 200 and await conn.fetchval(count) == 1
            stored = await conn.fetchrow("SELECT device_id, p256dh, auth FROM mobile_web_push_subscriptions WHERE endpoint = $1", endpoint)
            assert (stored["device_id"], stored["p256dh"], stored["auth"]) == (two, p256dh, auth)

            listing = await client.get("/state/mobile-alerts/web-push/subscriptions")
            ours = [row for row in listing.json()["subscriptions"] if row["endpoint_digest"] == push_store.digest(endpoint)]
            assert len(ours) == 1 and ours[0]["push_service"] == "fcm.googleapis.com" and endpoint not in listing.text

            bad = await client.post(subscribe, json={**body, "endpoint": endpoint.replace("https", "http")})
            assert bad.status_code == 422 and await conn.fetchval(count) == 1
            for _ in range(mobile_web_push.MAX_PER_DEVICE - 1):
                extra = {**body, "endpoint": "https://fcm.googleapis.com/fcm/send/qa-" + secrets.token_hex(24)}
                assert (await client.post(f"/state/mobile-alerts/devices/{two}/web-push/subscriptions", json=extra)).status_code == 200
            capped = {**body, "endpoint": "https://fcm.googleapis.com/fcm/send/qa-" + secrets.token_hex(24)}
            assert (await client.post(f"/state/mobile-alerts/devices/{two}/web-push/subscriptions", json=capped)).status_code == 409
            await conn.execute("UPDATE mobile_alert_devices SET enabled = false WHERE id = $1", one)
            assert (await client.post(subscribe, json=capped)).status_code == 404

            removed = await client.delete(f"/state/mobile-alerts/web-push/subscriptions/{ours[0]['id']}")
            assert removed.status_code == 200 and removed.json()["endpoint_digest"] == push_store.digest(endpoint)
            assert (await client.delete(f"/state/mobile-alerts/web-push/subscriptions/{ours[0]['id']}")).status_code == 404
    finally:
        for name in (mobile_vapid.PUBLIC_ENV, mobile_vapid.PRIVATE_ENV, mobile_vapid.SUBJECT_ENV):
            os.environ.pop(name, None)
    print(f"PASS web push: refused and nothing stored with no key pair; public key served, private never; one row per "
          f"browser, moved between phones not doubled; HTTP endpoint refused; {mobile_web_push.MAX_PER_DEVICE} per phone; "
          "listed by push service and digest; removed, then 404")


async def main(dsn: str) -> None:
    conn = await throwaway_connection(dsn)
    outer = conn.transaction()
    await outer.start()
    pool, provider = Pool(conn), Provider()
    os.environ["MOBILE_ALERTS_CONTROL_KEY"] = KEY
    mobile.publish = provider.publish
    try:
        await schema(conn)
        dead_letter = await retries(pool, conn, provider)
        await acknowledgements(pool, conn, provider, dead_letter)
        await web_push(pool, conn)
        print(f"{provider.calls} calls to the local fake provider; no request left the process.")
    finally:
        await outer.rollback()
        await conn.close()
        print("Rolled back; nothing kept.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(main(parser.parse_args().dsn))
