"""Browser (Web Push) subscription management.

- ``GET /state/mobile-alerts/web-push`` — whether a VAPID key pair is configured, the **public** key when it
  is, and in plain words what is missing when it is not. The private key is never part of this answer.
- ``POST /state/mobile-alerts/devices/{device_id}/web-push/subscriptions`` — record what a browser handed back
  after the operator allowed notifications on an enrolled phone.
- ``GET /state/mobile-alerts/web-push/subscriptions`` — the recorded browsers, by push service and digest.
- ``DELETE /state/mobile-alerts/web-push/subscriptions/{id}`` — remove one.

Every route except the status read needs the mobile control key, exactly like the rest of the mobile controls.

Sending is app/mobile_web_push_sender.py's job; these routes only record and remove. They do not accept any
endpoint: it is a URL the sender will post to, so it must be HTTPS, carry no credentials, and belong to one of the
push services browsers use (``PUSH_SERVICES`` in app/mobile_web_push_store.py). The browser's key must be a real
P-256 point, so nothing is stored that could never be sealed for.
"""

from __future__ import annotations

import ipaddress
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from app import mobile_vapid, web_push_encryption, mobile_web_push_store as store
from app.mobile_alerts import authorize

MAX_PER_DEVICE = 5
MAX_LISTED = 50
MIN_ENDPOINT, MAX_ENDPOINT = 20, 2000
P256DH_BYTES, AUTH_BYTES = 65, 16
PRIVATE_SUFFIXES = (".local", ".internal", ".localdomain", ".home.arpa")

SUBSCRIBE_NOTE = ("Recorded for this browser. While Web Push can send, alerts for this phone go to its subscribed "
                  "browsers instead of the ntfy app. A browser whose push service reports it gone is marked expired; "
                  "once none of the phone's browsers is left, the phone goes back to ntfy.")


class Subscription(BaseModel):
    endpoint: str
    p256dh: str = ""
    auth: str = ""
    label: str = Field("", max_length=60)
    keys: dict[str, str] | None = None

    def material(self) -> tuple[str, str]:
        """The two public values, whether they arrived flat or inside ``keys`` as the browser gives them."""
        keys = self.keys or {}
        return (self.p256dh or keys.get("p256dh", ""), self.auth or keys.get("auth", ""))


def checked_endpoint(value: str) -> str:
    """The endpoint to store, or a ValueError saying why it cannot be. The value is not repeated back."""
    endpoint = (value or "").strip()
    if not MIN_ENDPOINT <= len(endpoint) <= MAX_ENDPOINT:
        raise ValueError(f"A push endpoint is between {MIN_ENDPOINT} and {MAX_ENDPOINT} characters.")
    parts = urlsplit(endpoint)
    if parts.scheme != "https":
        raise ValueError("A push endpoint must be an HTTPS URL, as every browser's push service gives it.")
    if parts.username or parts.password:
        raise ValueError("A push endpoint must not carry a user name or password.")
    hostname = parts.hostname or ""
    if not hostname or "." not in hostname or hostname.endswith(PRIVATE_SUFFIXES):
        raise ValueError("A push endpoint must name a public push service host.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("A push endpoint must name a push service, not a private or loopback address.")
    if not store.known_push_service(hostname):
        raise ValueError("That is not a push service TradeSync sends to. Subscribe from a current Chrome, Edge, "
                         "Firefox or Safari.")
    return endpoint


def checked_material(p256dh: str, auth: str) -> tuple[str, str]:
    """The browser's two public values, checked so a key nothing could be sealed for is refused at the door."""
    key, secret = (p256dh or "").strip(), (auth or "").strip()
    raw = mobile_vapid.decode(key, P256DH_BYTES)
    if raw is None:
        raise ValueError(f"p256dh must be the browser's {P256DH_BYTES}-byte public key as base64url.")
    try:
        web_push_encryption.public_point(raw)
    except ValueError:
        raise ValueError("p256dh is not a P-256 public key, so no message could be sealed for this browser.") from None
    if mobile_vapid.decode(secret, AUTH_BYTES) is None:
        raise ValueError(f"auth must be the browser's {AUTH_BYTES}-byte secret as base64url.")
    return key, secret


def register(app, state) -> None:
    def pool():
        if getattr(state, "pool", None) is None:
            raise HTTPException(503, "Notification database unavailable")
        return state.pool

    @app.get("/state/mobile-alerts/web-push")
    async def web_push_status():
        return mobile_vapid.status()

    @app.post("/state/mobile-alerts/devices/{device_id}/web-push/subscriptions")
    async def subscribe(device_id: uuid.UUID, body: Subscription, request: Request):
        authorize(request)
        if not mobile_vapid.configured():
            raise HTTPException(503, mobile_vapid.problem() or "No Web Push key pair is configured.")
        try:
            endpoint = checked_endpoint(body.endpoint)
            p256dh, auth = checked_material(*body.material())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        async with pool().acquire() as conn:
            async with conn.transaction():
                if not await conn.fetchval("SELECT enabled FROM mobile_alert_devices WHERE id=$1", device_id):
                    raise HTTPException(404, "Enabled device not found")
                if await store.count_for_device(conn, device_id, endpoint) >= MAX_PER_DEVICE:
                    raise HTTPException(409, f"That phone already has {MAX_PER_DEVICE} browsers subscribed; "
                                             "remove one first.")
                saved = await store.save(conn, device_id, endpoint, p256dh, auth, body.label.strip())
        return {"id": str(saved["id"]), "endpoint_digest": saved["endpoint_digest"],
                "push_service": store.host(endpoint), "created": bool(saved["inserted"]),
                "status": "subscription_recorded", "note": SUBSCRIBE_NOTE}

    @app.get("/state/mobile-alerts/web-push/subscriptions")
    async def list_subscriptions(request: Request, limit: int = Query(MAX_LISTED, ge=1, le=MAX_LISTED)):
        authorize(request)
        async with pool().acquire() as conn:
            rows = await store.subscriptions(conn, limit)
        return {"schema_version": "mobile_web_push_subscriptions_v2",
                "subscriptions": [store.display(row) for row in rows],
                "configured": mobile_vapid.configured(), "sender_implemented": True,
                "sender_ready": mobile_vapid.sender_ready(),
                "note": ("A browser is shown by its push service and a digest, with the result of the last push sent "
                         "to it; the endpoint itself is never returned.")}

    @app.delete("/state/mobile-alerts/web-push/subscriptions/{subscription_id}")
    async def unsubscribe(subscription_id: uuid.UUID, request: Request):
        authorize(request)
        async with pool().acquire() as conn:
            removed = await store.remove(conn, subscription_id)
        if removed is None:
            raise HTTPException(404, "No such subscription")
        return {"status": "subscription_removed", "endpoint_digest": removed,
                "note": "Removed here. The browser keeps its own subscription until it is turned off there too."}
