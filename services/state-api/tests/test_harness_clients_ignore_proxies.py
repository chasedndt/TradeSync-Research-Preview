"""Harness HTTP clients ignore proxy variables, so no proxy set in a container can receive the gateway's key (security review L8)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app import agent_connector

APP = Path(__file__).resolve().parents[1] / "app"
HARNESS_MODULES = ("agent_connector.py", "hermes_jobs.py", "hermes_link.py", "horizon_reading.py", "editions.py")


@pytest.mark.parametrize("module", HARNESS_MODULES)
def test_every_http_client_in_a_harness_module_ignores_proxy_variables(module: str) -> None:
    tree = ast.parse((APP / module).read_text(encoding="utf-8"))
    clients = [node for node in ast.walk(tree)
               if isinstance(node, ast.Call) and ast.unparse(node.func) in ("httpx.AsyncClient", "httpx.Client")]
    assert clients, f"{module} opens no httpx client; update this test"
    for call in clients:
        assert any(keyword.arg == "trust_env" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                   for keyword in call.keywords), f"{module}:{call.lineno} opens a client that honours proxy variables"


def test_with_proxy_variables_set_the_probe_still_opens_a_client_that_ignores_them(monkeypatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    opened: list[dict] = []

    class Recorder:
        def __init__(self, *args, **kwargs):
            opened.append(kwargs)

        async def __aenter__(self):
            raise httpx.ConnectError("not sent")

        async def __aexit__(self, *exc):
            return False

    with patch.object(agent_connector, "AGENT_HARNESS_URL", "http://hermes:8642"), \
            patch.object(agent_connector.httpx, "AsyncClient", Recorder):
        status = asyncio.run(agent_connector.probe())
    assert status["status"] == "offline" and opened and all(kwargs.get("trust_env") is False for kwargs in opened)
