"""The WalletConnect project ID: public, saved with who and when, refused without repeating a mistaken paste."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.access_guard import AccessGuard
from app.main import app, state

client = TestClient(app)
URL = "/state/settings/walletconnect"
PROJECT = "0123456789abcdef0123456789abcdef"
OTHER = "FEDCBA9876543210fedcba9876543210"


class SettingsDb:
    """Migration 037's two tables in memory, answering exactly the statements the store sends."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.audit: list[dict] = []
        self.locks = 0

    @asynccontextmanager
    async def acquire(self):
        yield self

    def transaction(self):
        @asynccontextmanager
        async def transaction():
            yield

        return transaction()

    async def execute(self, sql, *args):
        if "pg_advisory_xact_lock" in sql:
            self.locks += 1
        elif sql.startswith("DELETE FROM operator_public_settings WHERE"):
            self.rows.pop(args[0], None)
        elif sql.startswith("INSERT INTO operator_public_settings_audit"):
            name, changed_by, changed_at, previous, next_value = args
            self.audit.append({"name": name, "changed_by": changed_by, "changed_at": changed_at, "previous": previous, "next": next_value})
        elif sql.startswith("INSERT INTO operator_public_settings ("):
            name, value, updated_by, updated_at = args
            self.rows[name] = {"name": name, "value": value, "updated_by": updated_by, "updated_at": updated_at}
        else:
            raise AssertionError(f"unexpected statement: {sql}")

    async def fetchval(self, sql, *args):
        assert sql.startswith("SELECT value FROM operator_public_settings WHERE name = $1")
        row = self.rows.get(args[0])
        return row["value"] if row else None

    async def fetchrow(self, sql, *args):
        assert sql.startswith("SELECT name, value, updated_by, updated_at FROM operator_public_settings WHERE name = $1")
        return self.rows.get(args[0])

    async def fetch(self, sql, *args):
        assert "FROM operator_public_settings_audit WHERE name = $1 ORDER BY changed_at DESC LIMIT $2" in sql
        name, limit = args
        return [row for row in reversed(self.audit) if row["name"] == name][:limit]


@pytest.fixture()
def db(monkeypatch):
    fake = SettingsDb()
    monkeypatch.setattr(state, "pool", fake)
    return fake


def put(**body):
    return client.put(URL, json={"changed_by": "chase", **body})


def test_the_routes_are_registered():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert {(URL, "GET"), (URL, "PUT")} <= paths


def test_nothing_is_saved_until_an_operator_saves_it(db):
    body = client.get(URL).json()
    assert body["project_id"] is None and body["updated_by"] is None and body["updated_at"] is None
    assert body["changes"] == [] and body["public"] is True and body["project_site"] == "https://dashboard.reown.com"


def test_a_save_is_audited_with_who_and_when_and_read_back(db):
    saved = put(project_id=f"  {PROJECT} ")
    body = saved.json()
    assert saved.status_code == 200 and body["changed"] is True and body["previous"] is None
    assert body["project_id"] == PROJECT and body["changed_by"] == "chase" and datetime.fromisoformat(body["changed_at"])
    page = client.get(URL).json()
    assert page["project_id"] == PROJECT and page["updated_by"] == "chase" and page["updated_at"] == body["changed_at"]
    assert [(c["changed_by"], c["previous"], c["next"]) for c in page["changes"]] == [("chase", None, PROJECT)]
    assert page["changes"][0]["changed_at"] == body["changed_at"] and db.locks == 1


def test_saving_the_same_value_changes_nothing_and_a_new_value_records_the_one_it_replaced(db):
    put(project_id=PROJECT)
    again = put(project_id=PROJECT, changed_by="someone else").json()
    assert again["changed"] is False and again["changed_at"] is None and len(db.audit) == 1
    assert again["updated_by"] == "chase"
    replaced = client.put(URL, json={"project_id": OTHER, "changed_by": "  ops  "}).json()
    assert replaced["previous"] == PROJECT and replaced["project_id"] == OTHER and replaced["changed_by"] == "ops"
    assert [(c["changed_by"], c["previous"], c["next"]) for c in client.get(URL).json()["changes"]] == [
        ("ops", PROJECT, OTHER), ("chase", None, PROJECT)]


def test_an_empty_project_id_clears_it_with_an_audit_row(db):
    put(project_id=PROJECT)
    cleared = put(project_id="   ").json()
    assert cleared["changed"] is True and cleared["project_id"] is None and cleared["previous"] == PROJECT
    assert db.rows == {} and db.audit[-1]["next"] is None and db.audit[-1]["previous"] == PROJECT
    assert put(project_id=None).json()["changed"] is False and len(db.audit) == 2


@pytest.mark.parametrize("value", [
    PROJECT[:-1],
    PROJECT + "0",
    PROJECT[:-1] + "g",
    "0x" + "ab" * 32,
    "ab" * 32,
    " ".join(["abandon"] * 11 + ["about"]),
])
def test_anything_but_32_hexadecimal_characters_is_refused_without_repeating_it(db, value):
    response = put(project_id=value)
    assert response.status_code == 400 and "Nothing was saved" in response.json()["detail"]
    assert value not in response.text
    assert db.rows == {} and db.audit == [] and db.locks == 0


def test_a_change_needs_a_name(db):
    for name in ("", "   ", "x" * 81):
        response = client.put(URL, json={"project_id": PROJECT, "changed_by": name})
        assert response.status_code == 400 and "your name" in response.json()["detail"]
    assert db.rows == {} and db.audit == []


def test_without_the_database_nothing_is_read_or_saved(monkeypatch):
    monkeypatch.setattr(state, "pool", None)
    assert client.get(URL).status_code == 503
    assert put(project_id=PROJECT).status_code == 503


def test_a_change_from_another_web_page_is_refused_before_the_route_runs(db):
    guarded = TestClient(AccessGuard(app, token="", allowed_origins=[]))
    refused = guarded.put(URL, json={"project_id": PROJECT, "changed_by": "x"}, headers={"Origin": "https://example.invalid"})
    assert refused.status_code == 403 and db.audit == []
    accepted = guarded.put(URL, json={"project_id": PROJECT, "changed_by": "chase"}, headers={"Origin": "http://127.0.0.1:3000"})
    assert accepted.status_code == 200 and len(db.audit) == 1
