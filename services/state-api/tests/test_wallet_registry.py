"""Wallet management remembers public addresses and refuses every secret-shaped input."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app, state
from app.wallet_registry import public_address

client = TestClient(app)
ADDRESS = "0x" + "a" * 40


class WalletDb:
    def __init__(self):
        self.rows = {}
        self.events = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    def transaction(self):
        @asynccontextmanager
        async def tx():
            yield
        return tx()

    async def fetch(self, sql, *args):
        assert "FROM wallet_connections ORDER BY" in sql
        return list(self.rows.values())

    async def fetchrow(self, sql, *args):
        if sql.startswith("SELECT id,label,connector,status"):
            return self.rows.get(args[0])
        if sql.startswith("INSERT INTO wallet_connections"):
            address, label, connector, operator = args
            now = datetime.now(timezone.utc)
            row = {"id": uuid.uuid4(), "address": address, "label": label, "connector": connector,
                   "status": "active", "added_by": operator, "added_at": now, "last_seen_at": now}
            self.rows[address] = row
            return row
        if sql.startswith("UPDATE wallet_connections SET label"):
            address, label, connector = args
            row = self.rows[address]
            row.update(label=label, connector=connector, status="active", last_seen_at=datetime.now(timezone.utc))
            return row
        if sql.startswith("UPDATE wallet_connections SET status"):
            identity = args[0]
            for row in self.rows.values():
                if row["id"] == identity and row["status"] == "active":
                    row.update(status="disconnected", last_seen_at=datetime.now(timezone.utc))
                    return row
            return None
        raise AssertionError(sql)

    async def execute(self, sql, *args):
        if "pg_advisory_xact_lock" in sql:
            return
        if sql.startswith("INSERT INTO wallet_connection_events"):
            self.events.append(args)
            return
        raise AssertionError(sql)


@pytest.fixture()
def db(monkeypatch):
    fake = WalletDb()
    monkeypatch.setattr(state, "pool", fake)
    return fake


def add(address=ADDRESS, connector="phantom"):
    return client.post("/state/wallets", json={"address": address, "label": "Main Hyperliquid",
        "connector": connector, "operator": "chase", "reason": "Local wallet connection"})


def test_address_validation_never_accepts_or_repeats_wallet_secrets():
    assert public_address(ADDRESS.upper().replace("0X", "0x")) == ADDRESS
    for secret in ("ab" * 32, "0x" + "ab" * 32, " ".join(["abandon"] * 11 + ["about"])):
        with pytest.raises(ValueError) as refused:
            public_address(secret)
        assert secret not in str(refused.value)


def test_add_list_reconnect_and_disconnect_are_public_address_only(db):
    created = add()
    assert created.status_code == 200
    body = created.json()
    assert body["action"] == "added" and body["execution_authority"] is False
    assert set(body["wallet"]) == {"id", "address", "label", "connector", "status", "added_by", "added_at", "last_seen_at"}
    assert add(connector="walletconnect").json()["action"] == "reconnected"
    listing = client.get("/state/wallets").json()
    assert listing["authority"] == "address_only" and listing["execution_authority"] is False
    assert len(listing["wallets"]) == 1 and len(db.events) == 2
    identity = listing["wallets"][0]["id"]
    stopped = client.post(f"/state/wallets/{identity}/disconnect", json={"operator": "chase", "reason": "Done"})
    assert stopped.status_code == 200 and stopped.json()["wallet"]["status"] == "disconnected"


def test_invalid_address_is_refused_without_echo_and_database_unavailable_fails_closed(db, monkeypatch):
    secret = " ".join(["abandon"] * 11 + ["about"])
    refused = add(secret)
    assert refused.status_code == 400 and secret not in refused.text and db.rows == {}
    monkeypatch.setattr(state, "pool", None)
    assert client.get("/state/wallets").status_code == 503
