"""TradingView setup: a boolean for the secret and never its value, the template, and receipts without payloads."""

from __future__ import annotations

import inspect
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import main
from app import tradingview_setup as setup
from app.main import app, state
from tradesync_core.tradingview_webhook import PUBLIC_WEBHOOK_URL, SECRET_PLACEHOLDER, message_template

client = TestClient(app)
URL = "/state/tradingview/setup"
SECRET = "k" * 64
RECEIVED = datetime(2026, 9, 13, 21, 24, 15, tzinfo=timezone.utc)


def row(payload=None, **values):
    body = {"schema_version": "tradingview_alert_v1", "indicator": "StrikeZone FVG Engine", "ticker": "BTCUSD",
            "interval": "15", "action": "", "alert": {"note": "fvg filled", "close": "79000"}}
    return {"id": uuid.uuid4(), "accepted": True, "received_at": RECEIVED, "reviewed_at": None, "promoted_to": None,
            "reasons": "[]", "payload": json.dumps(body if payload is None else payload), **values}


class ReceiptsDb:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.calls = rows or [], error, []

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if self.error:
            raise self.error
        return self.rows[: args[0]]


@pytest.fixture()
def db(monkeypatch):
    fake = ReceiptsDb()
    monkeypatch.setattr(state, "pool", fake)
    return fake


def test_the_route_is_registered():
    assert (URL, "GET") in {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}


@pytest.mark.parametrize("value, configured", [(SECRET, True), ("", False), ("   ", False)])
def test_the_secret_is_reported_as_configured_or_not_and_never_shown(db, value, configured):
    with patch.dict("os.environ", {setup.SECRET_ENV: value}):
        response = client.get(URL)
    assert response.status_code == 200 and response.json()["secret_configured"] is configured
    assert SECRET not in response.text


def test_the_setup_names_the_public_url_the_contract_and_a_template_with_a_placeholder(db):
    body = client.get(URL).json()
    assert body["webhook_url"] == PUBLIC_WEBHOOK_URL == "https://tradesync-pine.chaseintech.com/webhook/tradingview"
    assert body["contract"] == "tradingview_alert_v1" and body["required_fields"] == ["secret", "indicator", "ticker"]
    assert body["message_template"] == message_template() and body["message_template"]["secret"] == SECRET_PLACEHOLDER
    assert list(body["message_template"]) == list(message_template())
    assert body["secret_placeholder"] == SECRET_PLACEHOLDER and body["authority"] == "none"
    assert body["refusal_log_marker"] == "tradingview alert refused"


def test_receipts_list_only_what_identifies_each_alert_and_its_verdict(db):
    refused = [{"code": "payload_claims_authority", "detail": "a submission may not set its own trust or authority: tier"}]
    db.rows = [
        row(payload={"indicator": "EMA cross", "ticker": "ETHUSD", "interval": "1D", "secret": "must-not-appear",
                     "alert": {"secret": "must-not-appear-either"}}),
        row(accepted=False, reasons=json.dumps(refused)),
        row(reviewed_at=RECEIVED),
        row(promoted_to="context_only", reviewed_at=RECEIVED, payload={"indicator": "x" * 500, "ticker": ["odd"]}),
    ]
    response = client.get(URL, params={"limit": 4})
    receipts = response.json()["receipts"]
    assert "must-not-appear" not in response.text and "fvg filled" not in response.text
    assert [set(r) for r in receipts] == [{"id", "received_at", "accepted", "indicator", "ticker", "interval", "reasons", "review"}] * 4
    first, second, third, fourth = receipts
    assert (first["indicator"], first["ticker"], first["interval"], first["accepted"]) == ("EMA cross", "ETHUSD", "1D", True)
    assert first["received_at"] == "2026-09-13T21:24:15+00:00" and first["review"] == "awaiting review"
    assert second["accepted"] is False and second["reasons"] == refused
    assert third["review"] == "reviewed" and fourth["review"] == "promoted"
    assert len(fourth["indicator"]) == setup.FIELD_LIMIT and fourth["ticker"] == "['odd']" and fourth["interval"] == ""
    sql, args = db.calls[0]
    assert "source = 'tradingview'" in sql and "ORDER BY received_at DESC" in sql and args == (4,)


def test_an_unreadable_payload_or_reason_list_becomes_empty_text_not_an_error(db):
    db.rows = [row(payload=None, reasons="not json"), {**row(), "payload": "[1, 2]", "reasons": json.dumps(["plain"])}]
    db.rows[0]["payload"] = "{not json"
    receipts = client.get(URL).json()["receipts"]
    assert [(r["indicator"], r["ticker"], r["reasons"]) for r in receipts] == [("", "", []), ("", "", [])]


def test_the_limit_is_bounded(db):
    assert client.get(URL, params={"limit": 0}).status_code == 422
    assert client.get(URL, params={"limit": 51}).status_code == 422
    client.get(URL)
    assert db.calls[-1][1] == (8,)


def test_without_the_database_the_setup_still_answers_and_says_why_receipts_are_missing(monkeypatch):
    monkeypatch.setattr(state, "pool", None)
    body = client.get(URL).json()
    assert body["receipts"] == [] and "database is not connected" in body["receipts_error"]
    assert body["webhook_url"] == PUBLIC_WEBHOOK_URL


def test_a_failed_read_names_only_the_error_type(monkeypatch):
    monkeypatch.setattr(state, "pool", ReceiptsDb(error=RuntimeError("private connection detail")))
    body = client.get(URL).json()
    assert body["receipts"] == [] and "RuntimeError" in body["receipts_error"]
    assert "private connection detail" not in json.dumps(body)


def test_the_refusal_marker_is_what_the_receiver_logs():
    """The Cockpit's log command searches for this text; if the receiver's log line changes, this fails."""
    assert setup.REFUSAL_LOG_MARKER in inspect.getsource(main.tradingview_webhook)
