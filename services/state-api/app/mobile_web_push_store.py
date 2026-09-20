"""Where browser push subscriptions live: ``ops/migrations/038``, one row per browser.

A subscription is what a browser hands back after the operator allows notifications: the push service's
``endpoint`` URL and two public values, ``p256dh`` and ``auth``. None of them is a TradeSync secret, but the
endpoint is a capability URL — whoever holds it can push to that browser — so it is stored once, uniquely, and
never returned. A route sees only the endpoint's host and a twelve-character digest, which is enough to tell
two phones apart and useless to anyone who intercepts it.

Re-subscribing in the same browser produces the same endpoint, so saving is an upsert keyed on it: one row per
device per browser, and a browser that is moved to another enrolled phone moves rather than doubling. Saving
also brings an expired row back, because the browser has just proved the subscription exists.

Each row keeps the result of the last push sent to it. One whose push service answered 404 or 410 is marked
expired with the reason, is never sent to again, and no longer counts against the phone's limit.

Pushes go only to the push services browsers actually use, named in ``PUSH_SERVICES``. The endpoint came from a
browser through an authorized route, but it is still a URL this server will post to, so an unknown host is
refused when it is recorded and again when it is sent to.
"""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlsplit

# Exact hosts, and suffixes (starting with a dot) for services that shard across hosts.
PUSH_SERVICES = (
    "fcm.googleapis.com",                 # Chrome, and Chromium browsers on Android
    "android.googleapis.com",             # older Chrome subscriptions
    "updates.push.services.mozilla.com",  # Firefox
    "web.push.apple.com",                 # Safari on iPhone, iPad and Mac
    ".notify.windows.com",                # Edge on Windows
)

SUBSCRIPTION_COLUMNS = (
    "s.id, s.device_id, d.label AS device_label, d.platform, d.enabled AS device_enabled, s.endpoint, "
    "s.endpoint_digest, s.label, s.created_at, s.last_seen_at, s.last_attempt_at, s.last_status, s.last_error, "
    "s.accepted_at, s.expired_at, s.expired_reason"
)

SAVE_SQL = (
    "INSERT INTO mobile_web_push_subscriptions (device_id, endpoint, endpoint_digest, p256dh, auth, label) "
    "VALUES ($1, $2, $3, $4, $5, $6) "
    "ON CONFLICT (endpoint) DO UPDATE SET device_id=EXCLUDED.device_id, p256dh=EXCLUDED.p256dh, "
    "auth=EXCLUDED.auth, label=EXCLUDED.label, last_seen_at=now(), expired_at=NULL, expired_reason=NULL "
    "RETURNING id, device_id, endpoint_digest, label, created_at, last_seen_at, (xmax = 0) AS inserted"
)

LIST_SQL = (
    f"SELECT {SUBSCRIPTION_COLUMNS} FROM mobile_web_push_subscriptions s "
    "JOIN mobile_alert_devices d ON d.id = s.device_id ORDER BY s.created_at DESC LIMIT $1"
)

DELETE_SQL = "DELETE FROM mobile_web_push_subscriptions WHERE id = $1 RETURNING endpoint_digest"

# The browsers a phone already has, not counting expired ones or the browser now re-subscribing.
COUNT_SQL = (
    "SELECT count(*) FROM mobile_web_push_subscriptions "
    "WHERE device_id = $1 AND expired_at IS NULL AND endpoint <> $2"
)

ACTIVE_SQL = (
    "SELECT id, endpoint, endpoint_digest, p256dh, auth FROM mobile_web_push_subscriptions "
    "WHERE device_id = $1 AND expired_at IS NULL ORDER BY created_at LIMIT $2"
)

RESULT_SQL = (
    "UPDATE mobile_web_push_subscriptions SET last_attempt_at=now(), last_status=$2, last_error=$3, "
    "accepted_at=CASE WHEN $4 THEN now() ELSE accepted_at END, "
    "expired_at=CASE WHEN $5::text IS NULL THEN expired_at ELSE coalesce(expired_at, now()) END, "
    "expired_reason=CASE WHEN $5::text IS NULL THEN expired_reason ELSE coalesce(expired_reason, $5) END "
    "WHERE id=$1"
)


def digest(endpoint: str) -> str:
    """A short, stable name for one browser's endpoint that reveals nothing about it."""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:12]


def host(endpoint: str) -> str:
    """The push service the endpoint belongs to, for example ``fcm.googleapis.com``."""
    return urlsplit(endpoint).hostname or ""


def known_push_service(hostname: str) -> bool:
    """Whether a host is one of the push services browsers use, so a push may be posted to it."""
    name = (hostname or "").lower().rstrip(".")
    return any(name.endswith(entry) if entry.startswith(".") else name == entry for entry in PUSH_SERVICES)


def display(row: dict[str, Any]) -> dict[str, Any]:
    """One subscription as a route may return it: never the endpoint URL, only its host and digest."""
    endpoint = row.get("endpoint")

    def when(name: str) -> str | None:
        return row[name].isoformat() if row.get(name) else None

    return {
        "id": str(row["id"]),
        "device_id": str(row["device_id"]),
        "device_label": row.get("device_label"),
        "platform": row.get("platform"),
        "device_enabled": row.get("device_enabled"),
        "push_service": host(endpoint) if endpoint else None,
        "endpoint_digest": row["endpoint_digest"],
        "label": row.get("label") or "",
        "created_at": when("created_at"),
        "last_seen_at": when("last_seen_at"),
        "active": row.get("expired_at") is None,
        "last_attempt_at": when("last_attempt_at"),
        "last_status": row.get("last_status"),
        "last_error": row.get("last_error"),
        "accepted_at": when("accepted_at"),
        "expired_at": when("expired_at"),
        "expired_reason": row.get("expired_reason"),
    }


async def save(conn, device_id, endpoint: str, p256dh: str, auth: str, label: str) -> dict[str, Any]:
    """Record one browser's subscription, or update (and revive) the row that browser already has."""
    row = await conn.fetchrow(SAVE_SQL, device_id, endpoint, digest(endpoint), p256dh, auth, label)
    return dict(row)


async def subscriptions(conn, limit: int = 50) -> list[dict[str, Any]]:
    return [dict(row) for row in await conn.fetch(LIST_SQL, limit)]


async def remove(conn, subscription_id) -> str | None:
    """Delete one subscription; returns its digest, or None when there was no such row."""
    return await conn.fetchval(DELETE_SQL, subscription_id)


async def count_for_device(conn, device_id, endpoint: str = "") -> int:
    """Active browsers on a phone, leaving out ``endpoint`` so a browser re-subscribing is never refused."""
    return await conn.fetchval(COUNT_SQL, device_id, endpoint)


async def active_for_device(conn, device_id, limit: int) -> list[dict[str, Any]]:
    """The browsers a push for this phone goes to: every subscription not marked expired."""
    return [dict(row) for row in await conn.fetch(ACTIVE_SQL, device_id, limit)]


async def record_result(conn, subscription_id, status: int | None, error: str | None, accepted: bool,
                        expired_reason: str | None) -> None:
    """The outcome of one push to one browser; a reason marks it expired, keeping the first time and reason."""
    await conn.execute(RESULT_SQL, subscription_id, status, error, accepted, expired_reason)
