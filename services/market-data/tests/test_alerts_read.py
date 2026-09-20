"""The market alert read: an unreadable stream is an error, never an empty list.

The Cockpit's Alerts tab has to tell "no alert was raised" apart from "the
alerts could not be read". Both used to arrive as ``{"alerts": [], "count": 0}``
because a failed Redis read was swallowed here.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import market_routes
from app.redis_client import STREAM_ALERTS, MarketRedisClient


class UnreadableRedis:
    async def xrevrange(self, *args, **kwargs):
        raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")


class AlertStream:
    def __init__(self, messages):
        self.messages = messages
        self.calls = []

    async def xrevrange(self, stream, count=None):
        self.calls.append((stream, count))
        return self.messages[:count]


@contextmanager
def routes_reading(fake):
    """The market routes, reading alerts from ``fake`` through the real client."""
    reader = MarketRedisClient()
    reader.client = fake
    app = FastAPI()
    app.include_router(market_routes.router)
    with patch.object(market_routes, "redis_client", reader):
        yield TestClient(app)


def alert(symbol: str) -> dict:
    return {"id": f"a-{symbol}", "venue": "hyperliquid", "symbol": symbol, "ts": 1_757_980_800_000,
            "alert_type": "regime_change", "metric": "funding", "previous_value": "neutral",
            "new_value": "crowded_long", "context": {}}


def test_an_unreadable_stream_answers_503_rather_than_an_empty_list():
    with routes_reading(UnreadableRedis()) as client:
        response = client.get("/alerts", params={"limit": 100})
    assert response.status_code == 503
    assert response.json()["error"] == "alert_stream_unreadable"
    assert "alerts" not in response.json()


def test_an_unconnected_client_is_unreadable_too():
    with routes_reading(None) as client:
        response = client.get("/alerts")
    assert response.status_code == 503


def test_an_empty_stream_is_still_an_empty_answer():
    with routes_reading(AlertStream([])) as client:
        response = client.get("/alerts")
    assert response.status_code == 200
    assert response.json() == {"alerts": [], "count": 0}


def test_alerts_are_read_newest_first_up_to_the_limit():
    stream = AlertStream([
        ("1757980800000-1", {"data": json.dumps(alert("ETH-PERP"))}),
        ("1757980800000-0", {"data": json.dumps(alert("BTC-PERP"))}),
    ])
    with routes_reading(stream) as client:
        body = client.get("/alerts", params={"limit": 1}).json()
    assert stream.calls == [(STREAM_ALERTS, 1)]
    assert body["count"] == 1
    assert body["alerts"][0]["symbol"] == "ETH-PERP"
    assert body["alerts"][0]["_msg_id"] == "1757980800000-1"
