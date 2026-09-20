"""What the execution boundary reports: venue circuits, the signer's own status, and the preflight inventory.

Moved out of ``app/main.py`` unchanged, with the legacy ``/execution/status`` alias.
"""

import asyncio
import os
from typing import Any

import httpx
from fastapi import APIRouter, Response

from app.deprecation import apply_deprecation_headers
from app.execution_flags import execution_gate_enabled, paper_mode_enabled

router = APIRouter()

# The paper execution boundary. Outside the bounded profile by default;
# probing it is how the preflight reports what the venue side thinks.
EXEC_HL_URL = os.getenv("EXEC_HL_URL", "http://exec-hl-svc:8004")
SIGNER_URL = os.getenv("SIGNER_URL", "http://signer-svc:8006")


def register(app, state) -> None:
    """Attach the execution status, signer status and preflight reads."""

    @router.get("/state/execution/status")
    async def get_execution_status():
        """Aggregates execution status and circuit breaker states from all venues."""
        venues = ["hyperliquid"]
        urls = {
            "hyperliquid": "http://exec-hl-svc:8004/exec/hl/circuit-status"
        }

        status_report = []
        async with httpx.AsyncClient() as client:
            tasks = []
            for v in venues:
                tasks.append(client.get(urls[v], timeout=2.0))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, res in enumerate(results):
                venue_name = venues[i]
                if isinstance(res, httpx.Response) and res.status_code == 200:
                    status_report.append(res.json())
                else:
                    status_report.append({
                        "venue": venue_name,
                        "circuit_open": "unknown",
                        "error": str(res)
                    })

        return {
            "execution_enabled": os.getenv("EXECUTION_ENABLED", "false"),
            "venues": status_report
        }

    @router.get("/execution/status", tags=["legacy"])
    async def get_execution_status_alias(response: Response):
        apply_deprecation_headers(response, "/state/execution/status")
        return await get_execution_status()

    @router.get("/state/execution/signer-status", tags=["execution"])
    async def get_signer_status():
        """What the isolated signer reports about itself.

        Proxied rather than inlined, because the signer is deliberately a separate
        process and state-api must not grow the ability to answer for it.
        """
        try:
            async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
                response = await client.get(f"{SIGNER_URL}/signer/status")
                response.raise_for_status()
                return {**response.json(), "reachable": True}
        except Exception as exc:
            # Offline is the expected state: the signer is not in the bounded
            # profile and running one is a deliberate act.
            return {
                "reachable": False,
                "available": False,
                "status": "offline",
                "detail": type(exc).__name__ + (f": {exc}" if str(exc) else ""),
            }

    @router.get("/state/execution/preflight", tags=["execution"])
    async def get_execution_preflight():
        """Everything that would have to be true before any order could be placed.

        This makes the closed gate **legible**. It opens nothing: every field is a
        read, and the endpoint has no counterpart that flips any of them.

        The reason it is worth having while execution is disabled is that "why can I
        not trade" currently has its answer spread across an environment variable, a
        service that may not be running, a roadmap gate, and a risk policy. One
        place that lists them, with the current value of each, is the difference
        between a deliberate closed gate and one nobody can account for.
        """
        blockers: list[dict[str, Any]] = []

        if not execution_gate_enabled():
            blockers.append({
                "check": "execution_gate",
                "state": "closed",
                "detail": "EXECUTION_ENABLED is false. This is the global killswitch "
                          "and it is checked before any per-symbol rule.",
            })
        if paper_mode_enabled():
            blockers.append({
                "check": "paper_mode",
                "state": "on",
                "detail": "DRY_RUN is true. Orders are simulated at the execution "
                          "boundary and never reach a venue.",
            })

        # The measurement gate. This is the one that matters most and is the least
        # visible, because it lives in a document rather than in a variable.
        blockers.append({
            "check": "skill_gate_1_2",
            "state": "negative",
            "detail": "Gate 1.2 measured no demonstrated skill in any regime at any "
                      "horizon. Nothing in the current measurements argues for "
                      "moving toward execution.",
        })

        # The venue boundary's own view. Offline is an ordinary answer: exec-hl-svc
        # is outside the bounded profile and not running one is the normal state.
        venue: dict[str, Any] = {"status": "offline"}
        try:
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                resp = await client.get(f"{EXEC_HL_URL}/exec/hl/preflight")
            venue = (
                resp.json()
                if resp.status_code == 200
                else {"status": "error", "http_status": resp.status_code}
            )
        except Exception as exc:
            # The type, and the message only when there is one. httpx timeouts
            # stringify to empty, and "ConnectTimeout: " with nothing after the
            # colon reads like a truncated message rather than a complete answer.
            venue = {
                "status": "offline",
                "detail": type(exc).__name__ + (f": {exc}" if str(exc) else ""),
            }

        return {
            "can_execute": False if blockers else None,
            "blockers": blockers,
            "venue_preflight": venue,
            "authority": "read_only",
            "note": (
                "An inventory of what is closed and why. This endpoint opens "
                "nothing and has no counterpart that does. Opening the gate is an "
                "operator act requiring explicit approval and a passing skill gate."
            ),
        }

    app.include_router(router)
