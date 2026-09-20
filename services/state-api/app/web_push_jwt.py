"""VAPID (RFC 8292): the signed token that names the application server to a push service.

Every push request carries ``Authorization: vapid t=<JWT>, k=<public key>``. The push service checks the
signature against ``k``, the same public key the browser subscribed with, so only the holder of the private key
can push to TradeSync's subscriptions. The token's claims are:

- ``aud``: the push service's origin, taken from the endpoint;
- ``exp``: twelve hours ahead, inside RFC 8292's 24-hour ceiling;
- ``sub``: a contact for the sender, a ``mailto:`` or ``https:`` URL. Apple's push service refuses a token without
  one, so app/mobile_vapid.py lets no push go out while it is unset.

The signature is ES256: ECDSA over P-256 with SHA-256, encoded as the 64-octet r||s that JOSE uses. Its nonce is
derived deterministically (RFC 6979) rather than drawn at random, so a weak random source can never leak the
private key through a repeated nonce.

The private key arrives as a key object from app/mobile_vapid.signing_key(). This module never reads the
environment, never logs, and never puts key material in an error.
"""

from __future__ import annotations

import base64
import json
import time
from urllib.parse import urlsplit

from Crypto.Hash import SHA256
from Crypto.Signature import DSS

LIFETIME_SECONDS = 12 * 60 * 60
MAX_LIFETIME_SECONDS = 24 * 60 * 60
HEADER = {"typ": "JWT", "alg": "ES256"}


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _segment(value: dict) -> str:
    return b64url(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def audience(endpoint: str) -> str:
    """The origin of a push endpoint: ``https://host``, with a port only when it is not 443."""
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("A push endpoint is an https URL with a host.")
    port = parts.port
    return f"https://{parts.hostname}" + (f":{port}" if port and port != 443 else "")


def token(aud: str, subject: str, key, *, now: float | None = None, lifetime: int = LIFETIME_SECONDS) -> str:
    """A signed VAPID token for one push service."""
    if not 0 < lifetime <= MAX_LIFETIME_SECONDS:
        raise ValueError("A VAPID token lasts at most 24 hours.")
    claims = {"aud": aud, "exp": int(time.time() if now is None else now) + lifetime, "sub": subject}
    signing_input = f"{_segment(HEADER)}.{_segment(claims)}"
    signature = DSS.new(key, "deterministic-rfc6979").sign(SHA256.new(signing_input.encode("ascii")))
    return f"{signing_input}.{b64url(signature)}"


def authorization(endpoint: str, subject: str, public_key: str, key, *, now: float | None = None) -> str:
    """The Authorization header for one push request (RFC 8292 section 3)."""
    return f"vapid t={token(audience(endpoint), subject, key, now=now)}, k={public_key}"
