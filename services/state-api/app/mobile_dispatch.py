"""Deliver one queued mobile notification, through Web Push or ntfy, into one ledger row.

``dispatch`` claims one outbox row, checks that it may still be sent, attempts it and records the outcome
through app/mobile_delivery.py. The ntfy call arrives as ``publish``: app/mobile_alerts.dispatch_one passes its
own ``publish`` at call time, so this module keeps no import back into the routes.

Which transport carries an attempt is decided per attempt. When Web Push can send (a usable key pair and a
contact, app/mobile_vapid.py) and the phone has a browser that is not expired, the attempt goes to its browsers
(app/mobile_web_push_sender.py) with a new tap token; otherwise it goes to ntfy. Both land on the same row, so
the retries, the backoff, the dead letter and the budget are one path whichever transport carried it, and the
row records which one did.
"""
import json
from datetime import datetime, timezone

from app import mobile_ack_token, mobile_delivery, mobile_vapid, mobile_web_push_sender
from app import mobile_web_push_store as web_push_store
from app.mobile_policy import Preferences, opt_in_field, quiet


async def dispatch(pool, publish):
    async with pool.acquire() as conn:
        # Expire rows past their window and dead-letter rows that can never be attempted again; see app/mobile_delivery.py.
        await mobile_delivery.sweep(conn)
        row = await conn.fetchrow(mobile_delivery.CLAIM_SQL, mobile_delivery.MAX_ATTEMPTS)
        if row is None:
            return
        topic = await conn.fetchval('SELECT topic FROM mobile_alert_devices WHERE id=$1 AND enabled', row['device_id'])
    if topic is None:
        return
    # An automatic message is sent only while its own opt-in is still on and the phone is not in quiet hours.
    opt_in = opt_in_field(row['dedupe_key'])
    if row['kind'] == 'attention' and opt_in:
        async with pool.acquire() as conn:
            device = await conn.fetchrow('SELECT notification_preferences,enabled FROM mobile_alert_devices WHERE id=$1', row['device_id'])
            raw = device['notification_preferences'] if device else {}
            prefs = Preferences(**(json.loads(raw) if isinstance(raw, str) else raw))
            if not device or not device['enabled'] or not getattr(prefs, opt_in) or quiet(prefs, datetime.now(timezone.utc)):
                await conn.execute("UPDATE mobile_alert_outbox SET status='expired',last_error='PreferenceSuppressed',lease_until=NULL WHERE id=$1", row['id'])
                return
    # The transport and the tap token's digest are written before anything is sent.
    async with pool.acquire() as conn:
        browsers = (await web_push_store.active_for_device(conn, row['device_id'], mobile_web_push_sender.MAX_BROWSERS)
                    if mobile_vapid.sender_ready() else [])
        token = mobile_ack_token.new_token() if browsers else None
        await mobile_ack_token.issue(conn, row['id'], 'web_push' if browsers else 'ntfy', token)
    try:
        if browsers:
            provider_id = await mobile_web_push_sender.deliver(pool, browsers, row['kind'], row['id'], token)
        else:
            provider_id = await publish(topic, row['kind'], row['id'])
        async with pool.acquire() as conn:
            await conn.execute("UPDATE mobile_alert_outbox SET status='provider_accepted', provider_id=$2, accepted_at=now(), lease_until=NULL, last_error=NULL WHERE id=$1", row['id'], provider_id)
    except Exception as exc:
        # Bounded exponential backoff, then a dead letter that keeps why it was given up on.
        result = mobile_delivery.outcome(row['attempts'], *mobile_delivery.failure(exc))
        async with pool.acquire() as conn:
            await mobile_delivery.record_failure(conn, row['id'], result)
