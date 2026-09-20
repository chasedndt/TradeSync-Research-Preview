"""Tapping a notification records that it was seen: once, with a token that names nothing, behind every guard.

Requests go through the layering app/asgi.py deploys (Host check, access guard, body limit) around the real
routes, with the guards' settings passed in rather than read from this machine.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app import mobile_ack_token as tokens
from app.access_guard import TOKEN_EXEMPT_PATHS, AccessGuard
from app.body_limit import PATH_LIMITS, BodyLimit
from app.host_guard import HostGuard
from app.mobile_tap_ack import MAX_BODY_BYTES, PATH, REFUSED
from tradesync_core.state_api_access import MIN_TOKEN_CHARS, TOKEN_HEADER

OPERATOR_TOKEN = "s" * MIN_TOKEN_CHARS
COCKPIT = {"Host": "127.0.0.1:8000", "Origin": "http://127.0.0.1:3000"}
EVENT = uuid.UUID("3f2504e0-4f89-11d3-9a0c-0305e82c3301")


class Outbox:
    """One row's tap token, answered the way CONSUME_SQL answers: a matching, unexpired digest, once."""

    def __init__(self, token="", expired=False):
        self.digest, self.expired, self.queried = tokens.digest(token) if token else None, expired, []

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def fetchval(self, sql, *args):
        assert sql == tokens.CONSUME_SQL
        self.queried.append(args)
        if self.digest is not None and args[0] == self.digest and not self.expired:
            self.digest = None
            return EVENT
        return None


def client(monkeypatch, outbox, operator_token=""):
    monkeypatch.setattr(main.state, "pool", outbox)
    guarded = BodyLimit(main.app)
    guarded = AccessGuard(guarded, token=operator_token, allowed_origins=[])
    return TestClient(HostGuard(guarded, allowed_hosts=[], tunnel_hosts=[]))


def test_a_token_records_the_tap_once_and_the_answer_names_nothing_about_the_alert(monkeypatch):
    token = tokens.new_token()
    outbox = Outbox(token)
    api = client(monkeypatch, outbox)
    first = api.post(PATH, json={"token": token}, headers=COCKPIT)
    assert first.status_code == 200
    assert first.json() == {"status": "acknowledged", "authority": "none",
                            "note": "Recorded that the notification was opened. Nothing else changed."}
    again = api.post(PATH, json={"token": token}, headers=COCKPIT)
    assert again.status_code == 410 and again.json()["detail"] == REFUSED
    assert str(EVENT) not in first.text + again.text and str(EVENT)[:8] not in first.text + again.text
    # Only the digest is ever looked up; the token itself never reaches the database.
    assert outbox.queried == [(tokens.digest(token),)] * 2 and token not in str(outbox.queried)


def test_an_expired_or_unknown_token_gets_exactly_the_refusal_a_used_one_gets(monkeypatch):
    token = tokens.new_token()
    expired = client(monkeypatch, Outbox(token, expired=True)).post(PATH, json={"token": token}, headers=COCKPIT)
    unknown = client(monkeypatch, Outbox(token)).post(PATH, json={"token": tokens.new_token()}, headers=COCKPIT)
    assert expired.status_code == unknown.status_code == 410
    assert expired.json() == unknown.json() == {"detail": REFUSED}


def test_a_malformed_token_is_refused_before_the_database_is_asked(monkeypatch):
    outbox = Outbox(tokens.new_token())
    api = client(monkeypatch, outbox)
    for body in ({"token": "short"}, {"token": "!" * 43}, {"token": "a" * 44}, {}, {"token": 7}):
        assert api.post(PATH, json=body, headers=COCKPIT).status_code == 422, body
    assert outbox.queried == []
    assert asyncio.run(tokens.consume(outbox, "not a token")) is False and outbox.queried == []


def test_a_foreign_host_a_cross_site_page_and_an_oversized_body_are_each_refused_before_routing(monkeypatch):
    token = tokens.new_token()
    outbox = Outbox(token)
    api = client(monkeypatch, outbox)
    rebound = api.post(PATH, json={"token": token}, headers={**COCKPIT, "Host": "rebind.example"})
    cross_site = api.post(PATH, json={"token": token}, headers={**COCKPIT, "Origin": "https://example.invalid"})
    oversized = api.post(PATH, content=b'{"token":"' + b"a" * 2000 + b'"}',
                         headers={**COCKPIT, "Content-Type": "application/json"})
    assert (rebound.status_code, cross_site.status_code, oversized.status_code) == (400, 403, 413)
    assert PATH_LIMITS[PATH] == MAX_BODY_BYTES == 1024
    assert outbox.queried == [] and outbox.digest == tokens.digest(token)


def test_a_tap_needs_no_operator_token_while_every_other_change_still_does(monkeypatch):
    token = tokens.new_token()
    api = client(monkeypatch, Outbox(token), operator_token=OPERATOR_TOKEN)
    assert TOKEN_EXEMPT_PATHS == frozenset({PATH})
    assert api.post(PATH, json={"token": token}, headers=COCKPIT).status_code == 200
    assert api.post(PATH, json={"token": token}, headers={**COCKPIT, "Origin": "https://example.invalid"}).status_code == 403
    control = f"/state/mobile-alerts/events/{EVENT}/acknowledge"
    assert api.post(control, json={"by": "operator"}, headers=COCKPIT).status_code == 401
    with patch.dict("os.environ", {"MOBILE_ALERTS_CONTROL_KEY": ""}):
        # With the operator token the guard lets it through, and the route then asks for its own key.
        assert api.post(control, json={"by": "operator"}, headers={**COCKPIT, TOKEN_HEADER: OPERATOR_TOKEN}).status_code == 503


def test_the_statement_uses_a_token_once_and_keeps_an_acknowledgement_that_came_first():
    sql = tokens.CONSUME_SQL
    assert sql.startswith("UPDATE mobile_alert_outbox SET") and ";" not in sql
    assert "WHERE ack_token_hash=$1 AND ack_token_expires_at > now()" in sql
    assert "ack_token_hash=NULL, ack_token_expires_at=NULL" in sql
    assert "acknowledged_at=coalesce(acknowledged_at, now())" in sql and "coalesce(acknowledged_by, 'device')" in sql


def test_a_token_is_43_random_characters_and_what_is_kept_is_its_digest():
    first, second = tokens.new_token(), tokens.new_token()
    assert first != second and all(tokens.well_formed(value) for value in (first, second))
    assert len(tokens.digest(first)) == 64 and set(tokens.digest(first)) <= set("0123456789abcdef")
    assert tokens.LIFETIME_SECONDS == 3600 and "interval '3600 seconds'" in tokens.ISSUE_SQL
    for bad in ("", "a" * 42, "a" * 44, "a" * 42 + "=", None, 43):
        assert not tokens.well_formed(bad)
