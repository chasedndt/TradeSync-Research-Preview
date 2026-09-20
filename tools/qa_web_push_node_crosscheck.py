"""A second opinion on Web Push from an independent implementation: Node's crypto, which is OpenSSL.

state-api seals and signs with pycryptodome (app/web_push_encryption.py, app/web_push_jwt.py), and its tests open and
verify with pycryptodome too. This check hands the output to Node instead, sharing no code with either:

1. RFC 8291's example message, opened with the RFC's own browser key and auth secret.
2. A message app/web_push_encryption.py sealed, with TradeSync's padding, for a browser key made in memory.
3. A VAPID Authorization header from app/web_push_jwt.py, verified with Node's ES256; and one signed by another key,
   which must fail.

Nothing touches a network. The keys are made in memory for this run and passed to Node on stdin; nothing is written.

    python tools/qa_web_push_node_crosscheck.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "libs" / "tradesync_core"))
sys.path.insert(0, str(ROOT / "services" / "state-api"))
sys.path.insert(0, str(ROOT / "services" / "state-api" / "tests"))

from Crypto.PublicKey import ECC  # noqa: E402

from app import web_push_encryption, web_push_jwt  # noqa: E402
from test_web_push_encryption import AUTH_SECRET, MESSAGE, PLAINTEXT, UA_PRIVATE  # noqa: E402
from web_push_receiver import b64  # noqa: E402

NODE = r"""
const crypto = require('crypto')
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'))
const bytes = (text) => Buffer.from(text, 'base64url')

function open({ body, browser, auth }) {
  const sealed = bytes(body)
  const salt = sealed.subarray(0, 16), recordSize = sealed.readUInt32BE(16), idLength = sealed[20]
  const senderPublic = sealed.subarray(21, 21 + idLength), record = sealed.subarray(21 + idLength)
  const ecdh = crypto.createECDH('prime256v1')
  ecdh.setPrivateKey(bytes(browser))
  const shared = ecdh.computeSecret(senderPublic)
  const keyInfo = Buffer.concat([Buffer.from('WebPush: info\0'), ecdh.getPublicKey(), senderPublic])
  const ikm = Buffer.from(crypto.hkdfSync('sha256', shared, bytes(auth), keyInfo, 32))
  const cek = Buffer.from(crypto.hkdfSync('sha256', ikm, salt, Buffer.from('Content-Encoding: aes128gcm\0'), 16))
  const nonce = Buffer.from(crypto.hkdfSync('sha256', ikm, salt, Buffer.from('Content-Encoding: nonce\0'), 12))
  const decipher = crypto.createDecipheriv('aes-128-gcm', cek, nonce)
  decipher.setAuthTag(record.subarray(record.length - 16))
  const plain = Buffer.concat([decipher.update(record.subarray(0, record.length - 16)), decipher.final()])
  let end = plain.length
  while (end > 0 && plain[end - 1] === 0) end--
  if (idLength !== 65 || recordSize < record.length || plain[end - 1] !== 2) throw new Error('not one aes128gcm record')
  return plain.subarray(0, end - 1).toString('base64url')
}

function verify({ header, audience, now }) {
  const [, token, k] = /^vapid t=([^,]+), k=(.+)$/.exec(header)
  const [head, claims, signature] = token.split('.')
  const point = bytes(k)
  const key = crypto.createPublicKey({ format: 'jwk', key: { kty: 'EC', crv: 'P-256',
    x: point.subarray(1, 33).toString('base64url'), y: point.subarray(33, 65).toString('base64url') } })
  const signed = crypto.verify('sha256', Buffer.from(`${head}.${claims}`), { key, dsaEncoding: 'ieee-p1363' }, bytes(signature))
  const body = JSON.parse(bytes(claims).toString('utf8'))
  return signed && JSON.parse(bytes(head).toString('utf8')).alg === 'ES256' && body.aud === audience
    && body.exp > now && body.exp <= now + 86400 && /^(mailto:|https:\/\/)/.test(body.sub)
}

process.stdout.write(JSON.stringify({
  node: process.version,
  rfc: open(input.rfc) === input.rfc.plaintext,
  sealed: open(input.sealed) === input.sealed.plaintext,
  vapid: verify(input.vapid),
  forged: verify(input.forged),
}))
"""


def main() -> int:
    browser, auth, server, stranger = ECC.generate(curve="P-256"), os.urandom(16), ECC.generate(curve="P-256"), ECC.generate(curve="P-256")
    plaintext = json.dumps({"title": "TradeSync", "body": "TradeSync notification test. Reference qa000000",
                            "ack": "q" * 43}, separators=(",", ":")).encode("utf-8")
    sealed = web_push_encryption.encrypt(plaintext, web_push_encryption.raw_public(browser), auth, pad_to=512)
    public, now = b64(web_push_encryption.raw_public(server)), int(time.time())
    endpoint, audience, subject = "https://web.push.apple.com/qa-crosscheck", "https://web.push.apple.com", "mailto:qa@example.invalid"
    given = {
        "rfc": {"body": MESSAGE, "browser": UA_PRIVATE, "auth": AUTH_SECRET, "plaintext": PLAINTEXT},
        "sealed": {"body": b64(sealed), "browser": b64(int(browser.d).to_bytes(32, "big")), "auth": b64(auth),
                   "plaintext": b64(plaintext)},
        "vapid": {"header": web_push_jwt.authorization(endpoint, subject, public, server, now=now), "audience": audience, "now": now},
        "forged": {"header": web_push_jwt.authorization(endpoint, subject, public, stranger, now=now), "audience": audience, "now": now},
    }
    run = subprocess.run(["node", "-e", NODE], input=json.dumps(given), capture_output=True, text=True, timeout=60)
    if run.returncode != 0:
        print("FAIL: Node could not run the check:", run.stderr.strip()[-500:])
        return 1
    answer = json.loads(run.stdout)
    expected = {"rfc": True, "sealed": True, "vapid": True, "forged": False}
    lines = {
        "rfc": "Node opens RFC 8291's example message with the RFC's browser key and gets the RFC's plaintext",
        "sealed": f"Node opens a {len(sealed)}-octet message state-api sealed, padding and delimiter removed",
        "vapid": "Node verifies state-api's ES256 VAPID token: signature, audience, expiry within a day, contact",
        "forged": "Node refuses a token signed by a different key under the same public key",
    }
    failed = [name for name, value in expected.items() if answer.get(name) is not value]
    for name in expected:
        print(("FAIL " if name in failed else "PASS ") + lines[name])
    print(f"Independent implementation: Node {answer['node']} (OpenSSL). No network was used.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
