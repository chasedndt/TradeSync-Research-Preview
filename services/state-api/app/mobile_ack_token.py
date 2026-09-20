"""The single-use token a Web Push notification carries so that tapping it can say it was seen.

The service worker must hold no key: the mobile control key and the operator token authorize far more than
"this alert was opened". So every Web Push attempt gets its own token instead:

- 32 random octets (43 base64url characters), made with ``secrets`` for that one notification;
- only its SHA-256 digest is stored, on the outbox row, beside the moment it stops working, one hour after it
  was issued. A copy of the database cannot be replayed, and the token itself exists only inside the encrypted
  push payload and the browser that received it;
- it says nothing about the alert. It is random, and the reference the notification already shows is the only
  other thing sent.

A later attempt issues a new token and replaces the digest, so only the notification that was delivered can be
acknowledged. The sweep clears digests that have run out, and using a token clears its digest in the same
statement that records the acknowledgement. The route that takes the token is app/mobile_tap_ack.py.
"""

from __future__ import annotations

import hashlib
import re
import secrets

TOKEN_BYTES = 32
TOKEN_CHARACTERS = 43
LIFETIME_SECONDS = 60 * 60
SHAPE = re.compile(r"[A-Za-z0-9_-]{43}")
TRANSPORTS = ("ntfy", "web_push")

# Which transport carries this attempt, and the digest of its token when it has one. A new attempt always
# replaces the previous digest, and an ntfy attempt clears it: nothing it sends can carry a token.
ISSUE_SQL = (
    "UPDATE mobile_alert_outbox SET transport=$2, ack_token_hash=$3, "
    f"ack_token_expires_at=CASE WHEN $3::text IS NULL THEN NULL ELSE now()+interval '{LIFETIME_SECONDS} seconds' END "
    "WHERE id=$1"
)

CLEAR_EXPIRED_SQL = (
    "UPDATE mobile_alert_outbox SET ack_token_hash=NULL, ack_token_expires_at=NULL "
    "WHERE ack_token_expires_at IS NOT NULL AND ack_token_expires_at <= now()"
)

# One statement, so a token is used exactly once however many taps race: the first update clears the digest,
# and a concurrent one re-reads the row, no longer matches, and changes nothing. An acknowledgement already on the
# row (the operator's, say) is the one kept.
CONSUME_SQL = (
    "UPDATE mobile_alert_outbox SET acknowledged_at=coalesce(acknowledged_at, now()), "
    "acknowledged_by=coalesce(acknowledged_by, 'device'), ack_token_hash=NULL, ack_token_expires_at=NULL "
    "WHERE ack_token_hash=$1 AND ack_token_expires_at > now() RETURNING id"
)


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def digest(token: str) -> str:
    """What is stored for a token: its SHA-256, as 64 hex characters."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def well_formed(token: object) -> bool:
    return isinstance(token, str) and SHAPE.fullmatch(token) is not None


async def issue(conn, event_id, transport: str, token: str | None) -> None:
    """Record the transport for this attempt and the digest of its token, before anything is sent."""
    if transport not in TRANSPORTS or (token is not None and not well_formed(token)):
        raise ValueError("An attempt goes through ntfy or Web Push, with a well-formed token or none.")
    await conn.execute(ISSUE_SQL, event_id, transport, digest(token) if token else None)


async def consume(conn, token: str) -> bool:
    """Use a token once: True when it matched an unexpired digest and the acknowledgement is now recorded."""
    if not well_formed(token):
        return False
    return await conn.fetchval(CONSUME_SQL, digest(token)) is not None
