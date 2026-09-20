"""Web Push message encryption: RFC 8291, in the aes128gcm content coding of RFC 8188, as one record.

A push service carries a notification to a browser but must not be able to read it. When the browser subscribed
it gave two public values, ``p256dh`` (its P-256 public key) and ``auth`` (a 16-octet secret), and every message
is sealed for exactly that browser:

1. A new P-256 key pair (``sender_key``) and a new 16-octet ``salt`` are made for every message.
2. ECDH between that private key and the browser's public key gives ``ecdh_secret``.
3. ``auth`` and both public keys fold it into ``ikm`` (RFC 8291 section 3.3), and ``salt`` turns that into the
   content-encryption key ``cek`` and the ``nonce`` (RFC 8188 section 2.2).
4. The body is AES-128-GCM over the plaintext, the last-record delimiter 0x02 and zero padding, behind an
   86-octet header holding the salt, the record size and the new public key.

Padding every TradeSync push to one size means a push service cannot tell a test from an alert by its length.
``tests/test_web_push_encryption.py`` reproduces the example in RFC 8291 section 5 and every intermediate value
in its Appendix A, byte for byte.

Nothing here reads the environment, touches the network or logs. An error says what is wrong with a value and
never repeats the value.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass

from Crypto.Cipher import AES
from Crypto.Protocol.DH import key_agreement
from Crypto.PublicKey import ECC

CURVE = "P-256"
RECORD_SIZE = 4096
SALT_BYTES = 16
AUTH_SECRET_BYTES = 16
POINT_BYTES = 65
TAG_BYTES = 16
HEADER_BYTES = SALT_BYTES + 4 + 1 + POINT_BYTES
KEY_INFO = b"WebPush: info\x00"
CEK_INFO = b"Content-Encoding: aes128gcm\x00"
NONCE_INFO = b"Content-Encoding: nonce\x00"
LAST_RECORD = b"\x02"


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract with SHA-256 (RFC 5869 section 2.2)."""
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """HKDF-Expand with SHA-256 (RFC 5869 section 2.3)."""
    output, block, counter = b"", b"", 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def public_point(raw: bytes):
    """A P-256 public key from its 65 uncompressed octets. A point that is not on the curve is refused."""
    if len(raw) != POINT_BYTES or raw[0] != 0x04:
        raise ValueError("A P-256 public key is the 65-octet uncompressed point.")
    try:
        return ECC.import_key(raw, curve_name=CURVE)
    except ValueError:
        raise ValueError("That public key is not a point on the P-256 curve.") from None


def raw_public(key) -> bytes:
    """The 65 uncompressed octets of a key's public half."""
    return key.public_key().export_key(format="raw")


@dataclass(frozen=True)
class KeySchedule:
    """Every value derived for one message, named as RFC 8291 Appendix A names them."""

    ecdh_secret: bytes
    prk_key: bytes
    key_info: bytes
    ikm: bytes
    prk: bytes
    cek: bytes
    nonce: bytes


def key_schedule(sender_key, ua_public: bytes, auth_secret: bytes, salt: bytes) -> KeySchedule:
    """RFC 8291 section 3.4, from the sender's private key, the browser's public key, ``auth`` and ``salt``."""
    browser = public_point(ua_public)
    ecdh_secret = key_agreement(static_priv=sender_key, static_pub=browser, kdf=lambda shared: shared)
    prk_key = hkdf_extract(auth_secret, ecdh_secret)
    key_info = KEY_INFO + ua_public + raw_public(sender_key)
    ikm = hkdf_expand(prk_key, key_info, 32)
    prk = hkdf_extract(salt, ikm)
    return KeySchedule(ecdh_secret, prk_key, key_info, ikm, prk,
                       hkdf_expand(prk, CEK_INFO, 16), hkdf_expand(prk, NONCE_INFO, 12))


def encrypt(plaintext: bytes, ua_public: bytes, auth_secret: bytes, *, pad_to: int = 0,
            salt: bytes | None = None, sender_key=None) -> bytes:
    """One push message body for one browser.

    ``pad_to`` is the size the plaintext, its delimiter and the padding fill together. ``salt`` and
    ``sender_key`` are fixed only to reproduce the RFC's example; a real message always gets new ones.
    """
    if len(auth_secret) != AUTH_SECRET_BYTES:
        raise ValueError(f"The browser's auth secret is {AUTH_SECRET_BYTES} octets.")
    salt = os.urandom(SALT_BYTES) if salt is None else salt
    if len(salt) != SALT_BYTES:
        raise ValueError(f"The salt is {SALT_BYTES} octets.")
    record = plaintext + LAST_RECORD
    if pad_to:
        if len(record) > pad_to:
            raise ValueError("The message is longer than the size every push is padded to.")
        record += bytes(pad_to - len(record))
    if len(record) + TAG_BYTES > RECORD_SIZE:
        raise ValueError(f"A push message is one record of at most {RECORD_SIZE} octets.")
    sender_key = ECC.generate(curve=CURVE) if sender_key is None else sender_key
    schedule = key_schedule(sender_key, ua_public, auth_secret, salt)
    cipher = AES.new(schedule.cek, AES.MODE_GCM, nonce=schedule.nonce, mac_len=TAG_BYTES)
    ciphertext, tag = cipher.encrypt_and_digest(record)
    header = salt + struct.pack("!IB", RECORD_SIZE, POINT_BYTES) + raw_public(sender_key)
    return header + ciphertext + tag
