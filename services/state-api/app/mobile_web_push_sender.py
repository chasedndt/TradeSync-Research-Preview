"""Deliver one alert to a phone's subscribed browsers over Web Push.

app/mobile_dispatch.py calls ``deliver`` for an outbox row it has claimed, when Web Push can send and the phone has
at least one browser that is not expired. The row's retries, backoff, dead letter and budget are exactly those
ntfy uses; this module decides only what one attempt means.

**One attempt.** Every browser gets its own sealed copy (app/web_push_encryption.py) of the same payload, signed
for its own push service (app/web_push_jwt.py), all at once:

- 2xx: the push service accepted it. That is not proof the phone showed it.
- 404 or 410: the subscription no longer exists. The browser is marked expired with the reason and never sent to
  again; so is one whose stored key cannot be used or whose push service is not one TradeSync sends to.
- 429, 5xx, a timeout or a lost connection: worth trying again.
- any other answer (400, 401, 403, 413, or a redirect, which is never followed): the push service refused.

The row is accepted when any browser accepted. Otherwise the attempt fails as hopefully as the answers allow:
anything worth trying again makes it a retry; failing that, the refusal's HTTP status goes to the delivery policy
(app/mobile_delivery.py), which makes a 4xx a dead letter at once and tries anything else again until the attempts
run out; and when every browser turned out to be gone, the retry finds none left and goes through ntfy.

**The payload** is the sentence ntfy sends, the short reference, the path to open and the tap token
(app/mobile_ack_token.py), padded to one size so a push service cannot tell a test from an alert by its length.
A lock screen shows no trade, symbol, price, amount or wallet.

**Headers.** ``TTL`` lets a push service hold the message only for the outbox's own ten-minute window, and
``Urgency: high`` asks it to wake the phone. Redirects are not followed and no proxy settings are read.

The private key is only ever a key object here. Nothing is logged, and what is kept about a failure is an HTTP
status and a short name, never a response body, an endpoint or a key.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app import mobile_vapid, web_push_encryption, web_push_jwt
from app import mobile_web_push_store as store
from app.mobile_delivery import EXPIRY_SECONDS
from app.mobile_message import message

MAX_BROWSERS = 5
PADDED_BYTES = 512
TIMEOUT_SECONDS = 8
ACCEPTED, GONE, RETRY, REFUSED = "accepted", "gone", "retry", "refused"
P256DH_BYTES, AUTH_BYTES = 65, 16


class WebPushUndelivered(Exception):
    """No browser accepted this attempt. ``error_name`` and ``status_code`` are all the ledger keeps."""

    def __init__(self, error_name: str, status_code: int | None = None):
        super().__init__(error_name)
        self.error_name, self.status_code = error_name, status_code


@dataclass(frozen=True)
class Result:
    """What one browser's push service did with one push; ``reason`` is why a gone browser is marked expired."""

    outcome: str
    status: int | None = None
    error: str | None = None
    reason: str | None = None


NOT_ALLOWED = Result(GONE, None, "PushServiceNotAllowed",
                     "This push service is not one TradeSync sends to. Subscribe from a current Chrome, Edge, "
                     "Firefox or Safari.")
UNUSABLE_KEY = Result(GONE, None, "SubscriptionKeyUnusable",
                      "The browser key stored for this subscription cannot be used. Subscribe the browser again.")


def classify(status: int) -> Result:
    if 200 <= status < 300:
        return Result(ACCEPTED, status)
    if status in (404, 410):
        return Result(GONE, status, "SubscriptionGone",
                      f"The push service answered HTTP {status}: this subscription no longer exists. "
                      "Subscribe the browser again.")
    if status == 429:
        return Result(RETRY, status, "PushServiceRateLimited")
    if status >= 500:
        return Result(RETRY, status, "PushServiceUnavailable")
    return Result(REFUSED, status, "PushServiceRefused")


def payload(kind: str, event_id, token: str) -> bytes:
    """The words ntfy would send, with nothing added but a reference, where a tap goes, and the tap token."""
    reference = str(event_id)[:8]
    return json.dumps({"title": "TradeSync", "body": message(kind, event_id), "tag": f"tradesync-{reference}",
                       "path": "/", "reference": reference, "ack": token}, separators=(",", ":")).encode("utf-8")


async def post(endpoint: str, body: bytes, headers: dict[str, str]) -> int:
    """POST one sealed message and return the HTTP status. The only function here that reaches the network."""
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, trust_env=False, follow_redirects=False) as client:
        response = await client.post(endpoint, content=body, headers=headers)
    return response.status_code


async def attempt(browser: dict, plaintext: bytes, subject: str, public_key: str, key) -> Result:
    """One push to one browser, reduced to a Result. Never raises for anything the push service or network does."""
    endpoint = browser["endpoint"]
    if urlsplit(endpoint).scheme != "https" or not store.known_push_service(store.host(endpoint)):
        return NOT_ALLOWED
    p256dh = mobile_vapid.decode(browser["p256dh"], P256DH_BYTES)
    auth = mobile_vapid.decode(browser["auth"], AUTH_BYTES)
    try:
        if p256dh is None or auth is None:
            raise ValueError("unusable subscription key")
        sealed = web_push_encryption.encrypt(plaintext, p256dh, auth, pad_to=PADDED_BYTES)
    except ValueError:
        return UNUSABLE_KEY
    headers = {
        "Authorization": web_push_jwt.authorization(endpoint, subject, public_key, key),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(EXPIRY_SECONDS),
        "Urgency": "high",
    }
    try:
        return classify(await post(endpoint, sealed, headers))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return Result(RETRY, None, type(exc).__name__[:80])


def summary(results: list[Result]) -> str:
    """What the row keeps as its provider id when any browser accepted; otherwise the failure to record."""
    accepted = sum(result.outcome == ACCEPTED for result in results)
    if accepted:
        return f"web_push {accepted}/{len(results)}"
    for outcome in (RETRY, REFUSED):
        found = next((result for result in results if result.outcome == outcome), None)
        if found is not None:
            raise WebPushUndelivered(found.error or "PushServiceRefused", found.status)
    raise WebPushUndelivered("SubscriptionsGone")


async def deliver(pool, browsers: list[dict], kind: str, event_id, token: str) -> str:
    """Send one attempt to every browser, record each browser's result, and return or raise for the row."""
    key = mobile_vapid.signing_key()
    subject, public_key = mobile_vapid.subject(), mobile_vapid.public_key()
    plaintext = payload(kind, event_id, token)
    results = list(await asyncio.gather(*(attempt(browser, plaintext, subject, public_key, key)
                                          for browser in browsers)))
    async with pool.acquire() as conn:
        for browser, result in zip(browsers, results):
            await store.record_result(conn, browser["id"], result.status, result.error,
                                      result.outcome == ACCEPTED, result.reason if result.outcome == GONE else None)
    return summary(results)
