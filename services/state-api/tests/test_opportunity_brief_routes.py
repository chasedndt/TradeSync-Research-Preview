"""The opportunity-brief routes read stored rows, refuse bad identifiers, and change nothing."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app, state

client = TestClient(app)

OPPORTUNITY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def decision() -> dict:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "schema_version": "paper_signal_v1", "admitted": True, "direction": "LONG", "data_coverage": 0.55,
        "directional_score": 0.42, "directional_coverage": 1.0, "paper_risk_multiplier": 0.5,
        "evidence_digest": "digest-1", "rejection_reasons": [],
        "contributing_features": [{"feature_id": "hl_return_1h_pct", "score": 0.4, "observed_at_ms": now_ms - 1_000}],
        "evidence": {"evaluated_at_ms": now_ms, "rulebook_version": "1.0.0", "catalog_version": "1.2.0",
                     "policy": {"minimum_coverage_to_emit": 0.3, "minimum_directional_coverage": 0.5,
                                "direction_deadband": 0.05, "direction_enter_threshold": 0.15,
                                "maximum_evidence_age_ms": 120_000}},
    }


def row(**over):
    opened = datetime.now(timezone.utc) - timedelta(seconds=30)
    base = {
        "id": OPPORTUNITY_ID, "symbol": "BTC-PERP", "timeframe": "1m", "dir": "LONG", "bias": 0.42, "quality": 55.0,
        "snapshot_ts": opened, "links": json.dumps({"signal_id": "s1", "evidence_digest": "digest-1"}),
        "confluence": json.dumps(decision()), "signal_id": None, "status": "new",
        "expires_at": opened + timedelta(seconds=900),
        "regime": "rising", "trailing_return_pct": 0.4, "lookback_minutes": 60, "regime_reason": "",
        "regime_computed_at": opened,
        "position_id": None, "position_opened_at": None, "evidence_sha256": None, "initial_plan": None,
        "position_state": None, "entry_reference_price": 100.5,
    }
    base.update(over)
    return base


class Pool:
    """Stands in for the asyncpg pool and records every statement, so the tests can see nothing is written."""

    def __init__(self, one=None, many=(), paused=True):
        self.conn = AsyncMock()
        self.conn.fetchrow = AsyncMock(return_value=one)
        self.conn.fetch = AsyncMock(return_value=list(many))
        self.conn.fetchval = AsyncMock(side_effect=paused if isinstance(paused, Exception) else None,
                                       return_value=None if isinstance(paused, Exception) else paused)

    def acquire(self):
        conn = self.conn

        class Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return Ctx()

    def statements(self):
        calls = self.conn.fetchrow.call_args_list + self.conn.fetch.call_args_list + self.conn.fetchval.call_args_list
        return [call.args[0] for call in calls]


def test_one_brief_carries_every_field_from_stored_records() -> None:
    pool = Pool(one=row())
    with patch.object(state, "pool", pool):
        resp = client.get(f"/state/opportunity-briefs/{OPPORTUNITY_ID}")
    body = resp.json()
    assert resp.status_code == 200 and body["schema_version"] == "opportunity_brief_v1"
    assert (body["symbol"], body["timeframe"], body["side"]) == ("BTC-PERP", "1m", "LONG")
    assert body["regime_fit"]["fit"] == "with"
    assert body["entry"]["conditions_met"] == body["entry"]["conditions_checked"] == 4
    assert body["plan"]["status"] == "none" and "no stop" in body["plan"]["detail"]
    assert body["provenance"]["evidence_digest"] == "digest-1" and body["provenance"]["entry_reference_price"] == 100.5
    assert body["state"]["label"] == "Paper entries paused" and body["state"]["execution_authority"] is False
    assert 25 <= body["age_s"] <= 120


def test_a_frozen_paper_plan_supplies_the_stop_target_and_risk() -> None:
    plan = {"side": "long", "style": "intraday", "rules": {"version": "v3", "reward_risk": 2.0}, "entry_price": 100.0,
            "stop": 98.0, "target": 104.0, "planned_risk_usdc": 4.4,
            "planning": {"reward_usdc": 8.0, "cost_budget_usdc": 0.4, "stop_distance": 2.0}}
    opened = datetime.now(timezone.utc)
    pool = Pool(one=row(position_id=uuid.uuid4(), position_opened_at=opened, evidence_sha256="sha",
                        initial_plan=json.dumps(plan), position_state=json.dumps({"status": "open", "current_stop": 98.0})))
    with patch.object(state, "pool", pool):
        body = client.get(f"/state/opportunity-briefs/{OPPORTUNITY_ID}").json()
    assert (body["plan"]["stop"], body["plan"]["targets"][0]["level"]) == (98.0, 104.0)
    assert body["plan"]["net_reward_risk"] == round(7.6 / 4.4, 4)
    assert body["state"]["label"] == "Paper position open"
    assert body["provenance"]["entry_evidence_sha256"] == "sha"


def test_a_bad_identifier_is_refused_and_a_missing_one_is_not_found() -> None:
    with patch.object(state, "pool", Pool(one=None)):
        assert client.get("/state/opportunity-briefs/not-a-uuid").status_code == 422
        assert client.get(f"/state/opportunity-briefs/{uuid.uuid4()}").status_code == 404


def test_the_list_returns_compact_briefs_newest_first_for_a_status() -> None:
    pool = Pool(many=[row(), row(id=uuid.uuid4(), dir="SHORT", regime="rising")])
    with patch.object(state, "pool", pool):
        resp = client.get("/state/opportunity-briefs?status=new&symbol=btc-perp&limit=10")
    body = resp.json()
    assert resp.status_code == 200 and body["schema_version"] == "opportunity_briefs_v1"
    assert [b["side"] for b in body["briefs"]] == ["LONG", "SHORT"]
    assert [b["regime_fit"]["fit"] for b in body["briefs"]] == ["with", "against"]
    assert "evidence" not in body["briefs"][0]
    sql, *params = pool.conn.fetch.call_args.args
    assert "ORDER BY o.snapshot_ts DESC" in sql and params[0] == "BTC-PERP" and params[-1] == 10


def test_an_unreadable_pause_is_reported_as_unknown_rather_than_guessed() -> None:
    with patch.object(state, "pool", Pool(one=row(), paused=RuntimeError("no control table"))):
        body = client.get(f"/state/opportunity-briefs/{OPPORTUNITY_ID}").json()
    assert body["state"]["entries_paused"] is None
    assert body["state"]["label"] == "Paper entry state unknown"


def test_the_routes_only_ever_read() -> None:
    pool = Pool(one=row(), many=[row()])
    with patch.object(state, "pool", pool):
        client.get(f"/state/opportunity-briefs/{OPPORTUNITY_ID}")
        client.get("/state/opportunity-briefs?status=all")
    assert pool.statements() and all(sql.lstrip().upper().startswith("SELECT") for sql in pool.statements())
    pool.conn.execute.assert_not_called()


def test_no_database_is_a_503_that_says_nothing_was_read() -> None:
    with patch.object(state, "pool", None):
        resp = client.get("/state/opportunity-briefs")
    assert resp.status_code == 503 and "no brief was read" in resp.json()["detail"]
