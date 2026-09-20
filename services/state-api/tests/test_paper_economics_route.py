"""Paper-position economics over fake storage: every figure from the stored lifecycle state, bounded and windowed."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from audit_fakes import FakeConn, pool_of
from fastapi.testclient import TestClient

from app.main import app, state
from tradesync_core.managed_paper import advance, open_position

client = TestClient(app)
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)


def book(at, bid, ask):
    return {"poll_ts": at * 1000, "best_bid": bid, "best_ask": ask,
            "bids": [{"price": bid, "size": 100.0}], "asks": [{"price": ask, "size": 100.0}]}


def closed(exit_bid):
    p = open_position("long", "scalp", 1000, 1, book(1000, 99.99, 100.01), 1000)
    p = advance(p, book(1010, 100.6, 100.61), 1010)
    return advance(p, book(1020, exit_bid, exit_bid + 0.01), 1020, manual_close=True)


def stored(position_id, state_doc, created=NOW):
    return {"id": position_id, "opportunity_id": f"o-{position_id}", "symbol": "BTC-PERP", "created_at": created,
            "updated_at": created + timedelta(minutes=5), "position_state": json.dumps(state_doc)}


def read(rows, **params):
    conn = FakeConn([("FROM managed_paper_positions", lambda days, cap: rows[:cap])])
    with patch.object(state, "pool", pool_of(conn)):
        response = client.get("/state/outcomes/paper-economics", params=params)
    return response, conn


def test_the_reading_is_registered_and_refuses_without_a_database():
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", ())}
    assert ("/state/outcomes/paper-economics", "GET") in paths
    with patch.object(state, "pool", None):
        assert client.get("/state/outcomes/paper-economics").status_code == 503


def test_each_position_carries_its_economics_and_the_closed_ones_their_expectancy():
    win, loss = closed(100.9), closed(99.5)
    opened = advance(open_position("long", "scalp", 1000, 1, book(1000, 99.99, 100.01), 1000), book(1010, 100.2, 100.21), 1010)
    response, conn = read([stored("p1", win), stored("p2", loss), stored("p3", opened)], days=14)
    body = response.json()
    assert response.status_code == 200 and conn.bounded() and conn.asked("updated_at > now() - make_interval(days => $1)")
    assert body["window"]["days"] == 14 and body["window"]["to"] == body["generated_at"]
    assert [p["position_id"] for p in body["positions"]] == ["p1", "p2", "p3"] and body["truncated"] is False

    first = body["positions"][0]
    assert first["pnl"]["realised_usdc"] == pytest.approx(win["net_estimate_usdc"])
    assert first["fees"]["total_usdc"] == pytest.approx(win["fees_usdc"])
    assert first["slippage"]["entry"]["cost_usdc"] == pytest.approx(win["slippage"]["entry"]["cost_usdc"])
    assert first["excursions"]["favourable"]["price"] == 100.9 and first["excursions"]["adverse"]["price"] == 100.6
    assert body["positions"][2]["pnl"]["realised_usdc"] is None

    expectancy = body["expectancy"]
    assert expectancy["sample_size"] == 2
    assert expectancy["expectancy_usdc"] == pytest.approx((win["net_estimate_usdc"] + loss["net_estimate_usdc"]) / 2)
    assert expectancy["win_rate"] == 0.5 and expectancy["loss_rate"] == 0.5


def test_an_empty_window_has_no_expectancy_rather_than_a_zero():
    body = read([])[0].json()
    assert body["positions"] == [] and body["expectancy"]["sample_size"] == 0
    assert body["expectancy"]["expectancy_usdc"] is None


def test_a_capped_reading_says_it_is_truncated():
    rows = [stored(f"p{i}", closed(100.9)) for i in range(3)]
    body = read(rows, limit=2)[0].json()
    assert body["row_count"] == 2 and body["row_cap"] == 2 and body["truncated"] is True
    assert body["expectancy"]["sample_size"] == 2


def test_the_window_and_cap_are_bounded():
    for params in ({"days": 0}, {"days": 32}, {"limit": 0}, {"limit": 501}):
        assert read([], **params)[0].status_code == 422
