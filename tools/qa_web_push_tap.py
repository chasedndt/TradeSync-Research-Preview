"""Tapping a notification on a real database, through the guards app/asgi.py deploys, and a real race for one token.

Part of tools/qa_mobile_web_push_sql.py. ``taps`` runs inside that script's rolled-back transaction, using tokens
the fake browsers actually received. ``race`` needs two connections that see the same row, so it commits one
device and one outbox row of its own and deletes both afterwards; that is one more reason the script refuses
anything but a throwaway database.
"""

import asyncio
import secrets
import uuid

import asyncpg
import httpx

from app import main
from app import mobile_ack_token as tokens
from app import mobile_delivery as delivery
from app.access_guard import AccessGuard
from app.body_limit import BodyLimit
from app.host_guard import HostGuard
from app.mobile_tap_ack import PATH
from qa_mobile_support import KEY, outbox
from tradesync_core.state_api_access import MIN_TOKEN_CHARS, TOKEN_HEADER

OPERATOR_TOKEN = "q" * MIN_TOKEN_CHARS
COCKPIT = {"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:3000"}


def deployed(operator_token: str = "") -> httpx.AsyncClient:
    """The real routes behind the layering app/asgi.py builds, with the guards' settings given here."""
    guarded = HostGuard(AccessGuard(BodyLimit(main.app), token=operator_token, allowed_origins=[]),
                        allowed_hosts=[], tunnel_hosts=[])
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded), base_url="http://127.0.0.1:8000")


async def taps(pool, conn, delivered) -> None:
    main.state.pool = pool
    first, token = delivered["first"], delivered["first_token"]
    async with deployed() as api:
        rebound = await api.post(PATH, json={"token": token}, headers={**COCKPIT, "Host": "rebind.example"})
        cross_site = await api.post(PATH, json={"token": token}, headers={**COCKPIT, "Origin": "https://example.invalid"})
        oversized = await api.post(PATH, content=b'{"token":"' + b"a" * 2000 + b'"}',
                                   headers={**COCKPIT, "Content-Type": "application/json"})
        assert (rebound.status_code, cross_site.status_code, oversized.status_code) == (400, 403, 413)
        untouched = await outbox(conn, first)
        assert untouched["ack_token_hash"] == tokens.digest(token) and untouched["acknowledged_at"] is None

        tapped = await api.post(PATH, json={"token": token}, headers=COCKPIT)
        assert tapped.status_code == 200, tapped.text
        assert str(first) not in tapped.text and str(first)[:8] not in tapped.text
        row = await outbox(conn, first)
        assert (row["acknowledged_by"], row["ack_token_hash"], row["ack_token_expires_at"]) == ("device", None, None)
        again = await api.post(PATH, json={"token": token}, headers=COCKPIT)
        assert again.status_code == 410 and (await outbox(conn, first))["acknowledged_at"] == row["acknowledged_at"]

        second, second_token = delivered["second"], delivered["second_token"]
        await conn.execute("UPDATE mobile_alert_outbox SET ack_token_expires_at = now() - interval '1 second' "
                           "WHERE id = $1", second)
        expired = await api.post(PATH, json={"token": second_token}, headers=COCKPIT)
        unknown = await api.post(PATH, json={"token": tokens.new_token()}, headers=COCKPIT)
        malformed = await api.post(PATH, json={"token": "not-a-token"}, headers=COCKPIT)
        assert (expired.status_code, unknown.status_code, malformed.status_code) == (410, 410, 422)
        assert expired.json() == unknown.json() == again.json()
        assert (await outbox(conn, second))["acknowledged_at"] is None
        await delivery.sweep(conn)
        assert (await outbox(conn, second))["ack_token_hash"] is None, "the sweep drops a token that has run out"

    third, third_token = delivered["third"], delivered["third_token"]
    async with deployed(OPERATOR_TOKEN) as api:
        control = f"/state/mobile-alerts/events/{third}/acknowledge"
        assert (await api.post(control, json={"by": "operator"}, headers={**COCKPIT, "X-API-Key": KEY})).status_code == 401
        marked = await api.post(control, json={"by": "operator"},
                                headers={**COCKPIT, "X-API-Key": KEY, TOKEN_HEADER: OPERATOR_TOKEN})
        assert marked.status_code == 200, marked.text
        tapped = await api.post(PATH, json={"token": third_token}, headers=COCKPIT)
        assert tapped.status_code == 200, tapped.text
        row = await outbox(conn, third)
        assert (row["acknowledged_by"], row["ack_token_hash"]) == ("operator", None), dict(row)
    print("PASS taps through the deployed guards: a foreign Host 400, a cross-site page 403 and an oversized body 413 "
          "leave the row untouched; a received token records device once and a reuse gets 410; an expired token and "
          "an unknown one get the identical 410 and a malformed one 422; the sweep drops the expired digest; with an "
          "operator token set, the tap needs none while the control route answers 401, and an earlier operator "
          "acknowledgement is the one kept")


async def race(dsn: str) -> None:
    """Two taps with one token on two connections, the second arriving while the first still holds the row."""
    holder, rival = await asyncpg.connect(dsn), await asyncpg.connect(dsn)
    device, event, token = uuid.uuid4(), uuid.uuid4(), tokens.new_token()
    holding = second = None
    try:
        await holder.execute("INSERT INTO mobile_alert_devices (id, label, platform, topic) VALUES ($1, 'QA race', "
                             "'android', $2)", device, "tradesync-" + secrets.token_hex(24))
        await holder.execute(
            "INSERT INTO mobile_alert_outbox (id, device_id, dedupe_key, kind, status, attempts, expires_at, transport, "
            "ack_token_hash, ack_token_expires_at) VALUES ($1, $2, 'qa:race', 'test', 'provider_accepted', 1, "
            "now() + interval '10 minutes', 'web_push', $3, now() + interval '1 hour')", event, device, tokens.digest(token))
        holding = holder.transaction()
        await holding.start()
        assert await tokens.consume(holder, token) is True
        second = asyncio.create_task(tokens.consume(rival, token))
        await asyncio.sleep(0.5)
        assert not second.done(), "the second tap must wait for the first to finish"
        await holding.commit()
        assert await second is False
        row = await holder.fetchrow("SELECT acknowledged_by, ack_token_hash FROM mobile_alert_outbox WHERE id = $1", event)
        assert (row["acknowledged_by"], row["ack_token_hash"]) == ("device", None)
    finally:
        if second is not None and not second.done():
            second.cancel()
        if holding is not None:
            try:
                await holding.rollback()
            except asyncpg.InterfaceError:
                pass  # already committed
        await holder.execute("DELETE FROM mobile_alert_outbox WHERE id = $1", event)
        await holder.execute("DELETE FROM mobile_alert_devices WHERE id = $1", device)
        left = await holder.fetchval("SELECT count(*) FROM mobile_alert_outbox")
        await holder.close()
        await rival.close()
    assert left == 0
    print("PASS race: the second tap with the same token blocked on the row until the first committed, then matched "
          "nothing; one acknowledgement recorded; the two committed rows deleted, no outbox rows left")
