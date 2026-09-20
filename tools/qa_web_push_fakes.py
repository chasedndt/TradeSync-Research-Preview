"""A local push service and browsers for the Web Push acceptance. Nothing here reaches a network.

The push service checks each request the way a real one does: the VAPID signature against the public key named in
the Authorization header, the audience against its own origin, the expiry and the contact, and the aes128gcm
headers. Then it answers with the status it was told to give. A browser opens every message with its own private
key, and shows only the ones its push service accepted. The checking and the opening are
services/state-api/tests/web_push_receiver.py, written from the RFCs without the sender's code.

Every key is made in memory for one run and discarded with it.
"""

import json
import secrets
import time
from collections import Counter
from urllib.parse import urlsplit

from web_push_receiver import b64, browser, decrypt, verify_vapid

HEADERS = ("aes128gcm", "application/octet-stream", "600", "high")


class FakeBrowser:
    def __init__(self, host: str, label: str):
        self.key, self.p256dh, self.auth_secret = browser()
        self.endpoint = f"https://{host}/qa-push/{secrets.token_hex(24)}"
        self.label, self.shown = label, []

    def subscription(self) -> dict:
        """What the browser hands the Cockpit after it subscribes."""
        return {"endpoint": self.endpoint, "label": self.label,
                "keys": {"p256dh": self.p256dh, "auth": b64(self.auth_secret)}}

    def open(self, body: bytes) -> dict:
        return json.loads(decrypt(body, self.key, self.auth_secret))


class FakePushService:
    def __init__(self, public_key: str, subject: str):
        self.public_key, self.subject = public_key, subject
        self.browsers, self.plans, self.sizes, self.posted = {}, {}, set(), Counter()

    @property
    def requests(self) -> int:
        return sum(self.posted.values())

    def add(self, *browsers: FakeBrowser) -> None:
        for item in browsers:
            self.browsers[item.endpoint] = item

    def plan(self, target: FakeBrowser, *answers) -> None:
        self.plans.setdefault(target.endpoint, []).extend(answers)

    async def post(self, endpoint: str, body: bytes, headers: dict) -> int:
        target = self.browsers[endpoint]
        self.posted[endpoint] += 1
        claims = verify_vapid(headers["Authorization"], f"https://{urlsplit(endpoint).hostname}", time.time())
        assert claims["k"] == self.public_key and claims["sub"] == self.subject, "signed by the configured pair"
        assert (headers["Content-Encoding"], headers["Content-Type"], headers["TTL"], headers["Urgency"]) == HEADERS
        message = target.open(body)  # every push must open, whatever the push service then answers
        self.sizes.add(len(body))
        answers = self.plans.get(endpoint) or []
        answer = answers.pop(0) if answers else 201
        if isinstance(answer, BaseException):
            raise answer
        if 200 <= answer < 300:
            target.shown.append(message)
        return answer
