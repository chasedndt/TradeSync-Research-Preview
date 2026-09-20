"""The receiving side of Web Push, for tests and the acceptance tools only: what a push service and a browser do.

Written from RFC 8291 section 3.4 and RFC 8292 sections 2 and 3 with the cipher primitives alone. It shares no
code with app/web_push_encryption.py or app/web_push_jwt.py, so a mistake in the sender is not mirrored here.
"""

import base64
import hashlib
import hmac
import json
import struct

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.DH import key_agreement
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _mac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def decrypt(body: bytes, browser_key, auth_secret: bytes) -> bytes:
    """What the browser reads: the plaintext, with the padding and the 0x02 delimiter removed."""
    salt, record_size, id_length = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
    sender_public, sealed = body[21:21 + id_length], body[21 + id_length:]
    assert id_length == 65 and record_size >= len(sealed), "one record, keyed by a 65-octet public key"
    browser_public = browser_key.public_key().export_key(format="raw")
    shared = key_agreement(static_priv=browser_key, kdf=lambda z: z,
                           static_pub=ECC.import_key(sender_public, curve_name="P-256"))
    ikm = _mac(_mac(auth_secret, shared), b"WebPush: info\x00" + browser_public + sender_public + b"\x01")
    prk = _mac(salt, ikm)
    cek = _mac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _mac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    record = AES.new(cek, AES.MODE_GCM, nonce=nonce, mac_len=16).decrypt_and_verify(sealed[:-16], sealed[-16:])
    unpadded = record.rstrip(b"\x00")
    assert unpadded.endswith(b"\x02"), "the last record ends with the 0x02 delimiter"
    return unpadded[:-1]


def verify_vapid(authorization: str, origin: str, now: float) -> dict:
    """What a push service checks before accepting a push. Returns the claims and ``k``; raises when any fails."""
    scheme, _, parameters = authorization.partition(" ")
    assert scheme == "vapid", "the vapid authentication scheme"
    fields = dict(part.strip().split("=", 1) for part in parameters.split(","))
    header, claims, signature = fields["t"].split(".")
    assert json.loads(unb64(header)) == {"typ": "JWT", "alg": "ES256"}
    public = ECC.import_key(unb64(fields["k"]), curve_name="P-256")
    DSS.new(public, "fips-186-3").verify(SHA256.new(f"{header}.{claims}".encode("ascii")), unb64(signature))
    body = json.loads(unb64(claims))
    assert body["aud"] == origin, "the audience is the push service's own origin"
    assert now < body["exp"] <= now + 24 * 60 * 60, "unexpired, and at most 24 hours ahead"
    assert body["sub"].startswith(("mailto:", "https://")), "a contact for the sender"
    return {**body, "k": fields["k"]}


def browser():
    """A browser's subscription keys, made in memory: its P-256 key pair and a 16-octet auth secret."""
    import os

    key = ECC.generate(curve="P-256")
    return key, b64(key.public_key().export_key(format="raw")), os.urandom(16)
