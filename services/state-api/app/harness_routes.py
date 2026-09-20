"""The advisory harness: whether a runtime is reachable, and asking it a question.

Moved out of ``app/main.py`` unchanged. The boundary is the point of this module:
an answer is never evidence. It is checked against the advisory-only contract,
filed in quarantine as untrusted material, and the row's digest is returned as a
receipt. A model that claims scoring or approval authority is refused by name and
the attempt is stored, because "what did that connector try to send" is exactly
the question an operator needs answered later.

While the agent harness is stopped, ``AskGate`` (app/harness_gate.py) refuses the
ask route with 423 before it reaches here.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import agent_connector, error_responses
from tradesync_core.agent_harness import HarnessError
from tradesync_core.quarantine import content_digest, evaluate_submission

logger = logging.getLogger("state-api")
router = APIRouter()


class HarnessAsk(BaseModel):
    intent: str
    prompt: str
    context: Optional[Dict[str, Any]] = None


def register(app, state) -> None:
    """Attach the harness status and ask routes."""

    async def _record_harness_refusal(request: "HarnessAsk", exc: HarnessError) -> None:
        """File a refused harness answer as a quarantine refusal row.

        The offending content is stored as an opaque string in the payload, which is
        what quarantine is for: untrusted material kept for review. Nothing reads it
        back as structure, and the row is marked not accepted.

        Best effort. A failure to record must not mask the refusal itself — the
        operator still needs the 422.
        """
        if not state.pool:
            return
        try:
            payload = {
                "refused": True,
                "reason_code": exc.code,
                "reason": str(exc),
                "intent": request.intent,
                "prompt": request.prompt,
            }
            async with state.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO quarantine_intake
                        (source, accepted, content_digest, payload, reasons, observed_at)
                    VALUES ('agent_harness', false, $1, $2::jsonb, $3::jsonb, now())
                    ON CONFLICT (source, content_digest) DO NOTHING
                    """,
                    content_digest(payload),
                    json.dumps(payload),
                    json.dumps([{"code": exc.code, "detail": str(exc)}]),
                )
        except Exception as record_exc:
            logger.error(
                f"Could not record harness refusal: {record_exc}",
                extra={"trace_id": "agents"},
            )

    @router.get("/state/agents/harness/status", tags=["agents"])
    async def get_harness_status():
        """Whether an advisory harness runtime is reachable.

        "not_configured" and "offline" are ordinary states, not errors. Harnesses
        are optional and TradeSync is required to work without them — and reporting
        a stopped runtime as broken would repeat the healthcheck mistake this
        project already made once.
        """
        result = await agent_connector.probe()
        return {
            **result,
            "boundary": {
                "may_explain": True,
                "may_compare": True,
                "may_draft_proposals": True,
                "may_score": False,
                "may_approve": False,
                "may_execute": False,
            },
            "note": (
                "Enforced in code, not documented: a response carrying a score, "
                "direction, approval or order field is refused by name, and every "
                "accepted answer is routed to quarantine rather than to evidence."
            ),
        }

    @router.post("/state/agents/harness/ask", tags=["agents"])
    async def ask_harness(request: HarnessAsk):
        """Ask an advisory question and file the answer in quarantine.

        The answer is **never** returned as evidence. It is checked against the
        advisory-only contract, stored as an untrusted quarantine row, and the row's
        digest is returned as a receipt. Promotion to anything the system scores on
        remains an operator act through the normal quarantine review path.

        A model that claims scoring or approval authority produces HTTP 422 naming
        the field. That is a finding, not a transport failure: it usually means the
        prompt, or something the model read, tried to escalate.
        """
        if not agent_connector.configured():
            raise HTTPException(
                status_code=503,
                detail="AGENT_HARNESS_URL is unset; the harness connector is offline",
            )
        if not state.pool:
            raise HTTPException(status_code=503, detail="DB Pool not ready")

        try:
            result = await agent_connector.ask(
                request.intent, request.prompt, request.context
            )
        except HarnessError as exc:
            # A model reaching for authority is a finding, and this system already
            # holds that refusals are stored: "what did that connector try to send"
            # is exactly the question an operator needs answered later. Discarding
            # it would leave no trace of an escalation attempt.
            if exc.code == "authority_claimed":
                await _record_harness_refusal(request, exc)
            # 422 for a contract breach, 502 for a runtime that did not answer.
            status = 502 if exc.code in {"not_configured"} else 422
            raise HTTPException(status_code=status, detail=f"{exc.code}: {exc}")
        except httpx.HTTPError as exc:
            # The type matters. httpx.ReadTimeout stringifies to an empty string,
            # so "unreachable: " with nothing after it is what an operator would
            # have seen — the same trap that made an earlier read-path regression
            # in this system report a blank reason. The text itself can carry the
            # harness address, so only the log reference goes with the type.
            raise HTTPException(
                status_code=504 if isinstance(exc, httpx.TimeoutException) else 502,
                detail=(
                    f"harness runtime {type(exc).__name__} after {agent_connector.AGENT_HARNESS_TIMEOUT_S:.0f}s; "
                    f"log reference {error_responses.reference(exc, 'harness ask')}"
                ),
            )

        submission = agent_connector.quarantine_submission(result)
        received_ms = int(time.time() * 1000)

        async with state.pool.acquire() as conn:
            seen = await conn.fetch(
                "SELECT content_digest FROM quarantine_intake WHERE source = $1",
                submission["source"],
            )
            verdict = evaluate_submission(
                submission["source"],
                submission["payload"],
                received_ms,
                seen_digests=[r["content_digest"] for r in seen],
            )
            await conn.execute(
                """
                INSERT INTO quarantine_intake
                    (source, accepted, content_digest, payload, reasons, observed_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, now())
                ON CONFLICT (source, content_digest) DO NOTHING
                """,
                submission["source"],
                verdict.accepted,
                verdict.content_digest,
                json.dumps(submission["payload"]),
                json.dumps(verdict.reasons),
            )

        return {
            "intent": result["task"]["intent"],
            "task_digest": result["task"]["task_digest"],
            "content": result["accepted"]["content"],
            "model": result["accepted"]["model"],
            "elapsed_ms": result["accepted"]["elapsed_ms"],
            # The evidence writeback receipt: what was filed, and where.
            "receipt": {
                "quarantined": verdict.accepted,
                "content_digest": verdict.content_digest,
                "source": submission["source"],
                "reasons": verdict.reasons,
            },
            "authority": "advisory_only",
            "note": (
                "Filed in quarantine as untrusted material. It is not evidence and "
                "cannot reach the scoring path without an operator promotion."
            ),
        }

    app.include_router(router)
