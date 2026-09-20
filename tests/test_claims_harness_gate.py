"""core-scorer's claim reading asks nothing while the agent harness is stopped, and picks up where it stopped."""

from __future__ import annotations

import ast
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _service_import import load_service_module  # noqa: E402

_h = load_service_module("core_scorer_app", "core-scorer", "claims_harness")
ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 9, 15, 18, 0, tzinfo=timezone.utc)
REASON = ("The agent harness was stopped by chase at 2026-09-15 18:20:00 UTC (maintenance). "
          "TradeSync does not call Hermes until it is started again.")


def _row(qid: str) -> dict:
    return {"id": qid, "source": "discord", "received_at": T0, "observed_at": T0,
            "payload": {"schema_version": "discord_message_v1", "agent": "desk", "content": "BTC bearish below 77.3k", "embeds": []}}


def _response(status: int, body: dict) -> MagicMock:
    response = MagicMock(status_code=status)
    response.json.return_value = body
    response.text = str(body)
    return response


@pytest.fixture(autouse=True)
def fresh_gate():
    _h._gate.update(read_at=None, reason=None)
    yield
    _h._gate.update(read_at=None, reason=None)


@pytest.mark.asyncio
async def test_a_stopped_harness_is_not_asked_and_its_rows_stay_for_a_later_pass() -> None:
    client = MagicMock(get=AsyncMock(return_value=_response(200, {"open": False, "reason": REASON})))
    available, ask, record = AsyncMock(return_value=True), AsyncMock(), AsyncMock()
    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row("a"), _row("b")])), \
         patch.object(_h, "harness_available", available), patch.object(_h, "ask", ask), \
         patch.object(_h, "record_harness_extraction", record), patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), client)
    assert counts["stopped"] == 2 and counts["asked"] == 0 and counts["deferred"] == 0
    available.assert_not_awaited()
    ask.assert_not_awaited()
    record.assert_not_awaited()
    assert client.get.await_args.args[0].endswith("/state/agents/harness/gate")


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, expected", [
    (_response(404, {"detail": "Not Found"}), "HTTP 404"),
    (_response(200, {"unexpected": True}), "HTTP 200"),
    (httpx.ConnectError("state-api down"), "ConnectError"),
])
async def test_a_switch_that_cannot_be_read_counts_as_stopped(answer, expected) -> None:
    get = AsyncMock(side_effect=answer) if isinstance(answer, Exception) else AsyncMock(return_value=answer)
    reason = await _h.harness_stopped(MagicMock(get=get))
    assert reason and "could not be read" in reason and expected in reason


@pytest.mark.asyncio
async def test_the_switch_is_read_once_per_cache_window(monkeypatch) -> None:
    clock = iter([100.0, 105.0, 111.0])
    monkeypatch.setattr(_h, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(_h, "HARNESS_GATE_CACHE_S", 10.0)
    get = AsyncMock(return_value=_response(200, {"open": True, "reason": None}))
    client = MagicMock(get=get)
    assert await _h.harness_stopped(client) is None
    assert await _h.harness_stopped(client) is None and get.await_count == 1
    assert await _h.harness_stopped(client) is None and get.await_count == 2


@pytest.mark.asyncio
async def test_a_stop_during_the_pass_ends_it_without_marking_the_rows_left() -> None:
    post = AsyncMock(return_value=_response(423, {"detail": REASON, "harness": "stopped"}))
    record = AsyncMock()
    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row("a"), _row("b"), _row("c")])), \
         patch.object(_h, "harness_stopped", AsyncMock(return_value=None)), \
         patch.object(_h, "harness_available", AsyncMock(return_value=True)), \
         patch.object(_h, "record_harness_extraction", record), patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), MagicMock(post=post))
    assert counts["stopped"] == 3 and counts["asked"] == 0 and post.await_count == 1
    record.assert_not_awaited()
    assert _h._gate["reason"] == REASON


@pytest.mark.asyncio
async def test_an_open_switch_lets_the_pass_continue_as_before() -> None:
    client = MagicMock(get=AsyncMock(return_value=_response(200, {"open": True, "reason": None})))
    available = AsyncMock(return_value=False)
    with patch.object(_h, "harness_candidates", AsyncMock(return_value=[_row("a")])), \
         patch.object(_h, "harness_available", available), patch.object(_h, "HARNESS_CLAIMS_ENABLED", True):
        counts = await _h.run_harness_pass(MagicMock(), client)
    available.assert_awaited_once()
    assert counts["stopped"] == 0 and counts["asked"] == 0


def test_the_claims_client_ignores_proxy_variables() -> None:
    """It carries the harness asks and the operator token (security review L8)."""
    tree = ast.parse((ROOT / "services" / "core-scorer" / "app" / "main.py").read_text(encoding="utf-8"))
    loop = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "claims_loop")
    calls = [node for node in ast.walk(loop) if isinstance(node, ast.Call) and ast.unparse(node.func) == "httpx.AsyncClient"]
    assert calls and all(any(k.arg == "trust_env" and getattr(k.value, "value", None) is False for k in call.keywords)
                         for call in calls)
