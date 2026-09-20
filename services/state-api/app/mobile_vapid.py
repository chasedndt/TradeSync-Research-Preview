"""The VAPID application server keys, read from the environment and never written down anywhere else.

Web Push identifies the sender with a VAPID key pair on the P-256 curve:

- the **public** key is what a browser is given when it subscribes. It is public by design — it travels to the
  push service with every subscription — so it is served to the Cockpit and may appear on screen.
- the **private** key signs the request a sender makes to the push service. It stays in the environment. This
  module reads it only to say whether it is present and the right shape; it is never returned by a route,
  never logged, never put in an error message and never stored in the database.

Both are base64url with no padding: the public key is the 65-byte uncompressed point ``0x04 || X || Y`` (87
characters), the private key the 32-byte scalar (43 characters).

Generating the pair is the operator's step and happens on the operator's PC. Nothing in this repository creates
a key, and no key is committed. The command is in ``docs/runbooks/MOBILE_ALERTS.md`` and on the Settings page.

Two levels of ready. With a usable pair a browser may subscribe (``configured``). Sending needs one more thing,
``MOBILE_WEB_PUSH_SUBJECT``, the contact push services are given for the sender, because Apple's refuses a push
without one (``sender_ready``). Until both hold, alerts keep going through ntfy and the status says why. The
contact is an operator's address, so the status reports only whether it is set and well formed, never the value.
"""

from __future__ import annotations

import base64
import binascii
import os
import re
from urllib.parse import urlsplit

from Crypto.PublicKey import ECC

PUBLIC_ENV = "MOBILE_WEB_PUSH_VAPID_PUBLIC_KEY"
PRIVATE_ENV = "MOBILE_WEB_PUSH_VAPID_PRIVATE_KEY"
SUBJECT_ENV = "MOBILE_WEB_PUSH_SUBJECT"

PUBLIC_KEY_BYTES = 65
PRIVATE_KEY_BYTES = 32
UNCOMPRESSED_POINT = 0x04

MISSING, MALFORMED, OK = "missing", "malformed", "ok"
MAILTO = re.compile(r"mailto:[^@\s/]+@[^@\s/]+\.[^@\s/]+")


class VapidKeyError(ValueError):
    """The configured pair cannot sign. The message names a variable, never a value."""

NOTE = ("The public key is public by design: a browser sends it to its push service with every subscription. "
        "The private key stays in the environment; it is never returned, shown or written to the database.")
DELIVERY = ("While Web Push can send, alerts for a phone with a subscribed browser that has not expired go to its "
            "browsers instead of ntfy, and a phone without one keeps ntfy. A push service accepting a push is not "
            "proof the phone showed it; tapping the notification records that it was seen.")


def decode(value: str | None, expected: int) -> bytes | None:
    """The bytes behind a base64url value of exactly ``expected`` length, or None when it is not that."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        return None
    return raw if len(raw) == expected else None


def _state(value: str | None, expected: int, point: bool = False) -> str:
    if not (value or "").strip():
        return MISSING
    raw = decode(value, expected)
    if raw is None or (point and raw[0] != UNCOMPRESSED_POINT):
        return MALFORMED
    return OK


def public_key() -> str | None:
    """The public key to hand the browser, or None when it is absent or the wrong shape."""
    value = os.getenv(PUBLIC_ENV, "").strip()
    return value if _state(value, PUBLIC_KEY_BYTES, point=True) == OK else None


def private_key_state() -> str:
    """Whether the private key is present and the right shape. Its value never leaves this function."""
    return _state(os.getenv(PRIVATE_ENV), PRIVATE_KEY_BYTES)


def signing_key():
    """The private key as a P-256 key object, once it is known to be the other half of the public key.

    Raises VapidKeyError when either half is missing or malformed, when the scalar is not a P-256 private key, or
    when the private key does not produce the configured public key. A push signed with a mismatched pair would be
    refused by every push service, so the mismatch is reported here instead.
    """
    public = decode(os.getenv(PUBLIC_ENV), PUBLIC_KEY_BYTES)
    private = decode(os.getenv(PRIVATE_ENV), PRIVATE_KEY_BYTES)
    if public is None or private is None or public[0] != UNCOMPRESSED_POINT:
        raise VapidKeyError(f"{PUBLIC_ENV} and {PRIVATE_ENV} must both be set, in the shapes described above.")
    try:
        key = ECC.construct(curve="P-256", d=int.from_bytes(private, "big"))
    except ValueError:
        raise VapidKeyError(f"{PRIVATE_ENV} is not a usable P-256 private key. The value is not shown.") from None
    if key.public_key().export_key(format="raw") != public:
        raise VapidKeyError(f"{PRIVATE_ENV} and {PUBLIC_ENV} are not the two halves of one key pair.")
    return key


def pair_matches() -> bool:
    try:
        signing_key()
    except VapidKeyError:
        return False
    return True


def subject_state() -> str:
    """Whether the sender's contact is set, and is a ``mailto:`` address or an ``https:`` URL with a real host."""
    value = os.getenv(SUBJECT_ENV, "").strip()
    if not value:
        return MISSING
    if MAILTO.fullmatch(value):
        return OK
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
    except ValueError:
        return MALFORMED
    return OK if parts.scheme == "https" and "." in host and not parts.username else MALFORMED


def subject() -> str | None:
    """The contact a push service is given for the sender, when it is set and well formed."""
    return os.getenv(SUBJECT_ENV, "").strip() if subject_state() == OK else None


def configured() -> bool:
    """Both keys present, well formed, and one pair. Only then can a subscription ever be used."""
    return public_key() is not None and private_key_state() == OK and pair_matches()


def problem() -> str | None:
    """One sentence saying what is missing, or None when the pair is usable. Never repeats a key."""
    public_state, private = _state(os.getenv(PUBLIC_ENV), PUBLIC_KEY_BYTES, point=True), private_key_state()
    if public_state == MISSING and private == MISSING:
        return (f"No Web Push key pair is configured. Generate one on this PC and set {PUBLIC_ENV} and "
                f"{PRIVATE_ENV} in runtime.env; until then a browser cannot subscribe.")
    if public_state == MISSING:
        return f"{PUBLIC_ENV} is not set, so a browser has no key to subscribe with."
    if public_state == MALFORMED:
        return (f"{PUBLIC_ENV} is not a VAPID public key: it must be the {PUBLIC_KEY_BYTES}-byte uncompressed "
                "P-256 point as base64url, 87 characters. The value is not shown.")
    if private == MISSING:
        return f"{PRIVATE_ENV} is not set, so nothing could ever sign a push for these subscriptions."
    if private == MALFORMED:
        return (f"{PRIVATE_ENV} is not a VAPID private key: it must be the {PRIVATE_KEY_BYTES}-byte scalar as "
                "base64url, 43 characters. The value is not shown.")
    try:
        signing_key()
    except VapidKeyError as exc:
        return f"{exc} Generate the pair again with the command below and set both halves."
    return None


def sender_ready() -> bool:
    """Web Push can send: a usable key pair and a well-formed contact."""
    return configured() and subject_state() == OK


def sender_problem() -> str | None:
    """Why alerts are not going out over Web Push, in one sentence, or None when they can."""
    if not configured():
        return problem()
    state = subject_state()
    if state == MISSING:
        return (f"{SUBJECT_ENV} is not set. Push services are given it as the sender's contact and Apple's refuses a "
                "push without one, so alerts keep going through ntfy until it is a mailto: address or an https: URL.")
    if state == MALFORMED:
        return (f"{SUBJECT_ENV} must be a mailto: address or an https: URL with a real host; alerts keep going "
                "through ntfy until it is. The value is not shown.")
    return None


def status() -> dict[str, object]:
    """What the Cockpit is told: the public key when usable, and plainly what is missing when it is not."""
    usable = configured()
    return {
        "schema_version": "mobile_web_push_status_v2",
        "configured": usable,
        "public_key": public_key() if usable else None,
        "public_key_state": _state(os.getenv(PUBLIC_ENV), PUBLIC_KEY_BYTES, point=True),
        "private_key_state": private_key_state(),
        "subject_state": subject_state(),
        "sender_implemented": True,
        "sender_ready": usable and subject_state() == OK,
        "public_key_env": PUBLIC_ENV,
        "private_key_env": PRIVATE_ENV,
        "subject_env": SUBJECT_ENV,
        "problem": problem(),
        "sender_problem": sender_problem(),
        "note": NOTE,
        "delivery": DELIVERY,
    }
