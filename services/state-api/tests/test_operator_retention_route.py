"""The retention route reports the windows the deleting code applies, and needs no database to do it."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import paper_correlation_store, paper_reconciliation_store
from app.main import app, state
from app.market_recorder import RETENTION_EVERY_S
from tradesync_core import market_history

client = TestClient(app)


def test_the_windows_are_the_ones_the_stores_and_recorder_apply() -> None:
    with patch.object(state, "pool", None):
        resp = client.get("/state/operator/retention")
    assert resp.status_code == 200
    body = resp.json()
    windows = {w["table"]: w for w in body["windows"]}
    correlation = inspect.signature(paper_correlation_store.prune).parameters["keep_days"].default
    reconciliation = inspect.signature(paper_reconciliation_store.prune_runs).parameters["keep_days"].default
    assert windows["paper_correlation_measurements"]["kept_days"] == correlation == 30
    assert windows["paper_reconciliation_runs"]["kept_days"] == reconciliation == 14
    assert windows["market_depth_snapshots"]["kept_days"] == market_history.DEPTH_KEEP_DAYS
    assert f"every {RETENTION_EVERY_S // 60} minutes" in windows["market_open_interest"]["run_by"]
    assert body["schema_version"] == "retention_policy_v1" and "Every other table is kept" in body["kept"]
