"""The isolated signer. The only process in this system that may hold a key.

Everything about this service is shaped by one question: if some other part of
TradeSync is compromised, what can it make this process do?

**It receives a digest, never a payload.** `POST /sign` takes a 32-byte hex hash
and nothing it has to parse to understand. There is no code path here that
decodes an order, talks to a venue, or interprets anything a venue said. The
attack surface of "parse untrusted input" does not exist in this process.

**It cannot be asked what it holds.** No endpoint returns the key, the mnemonic,
or anything derived from them beyond the public address — which is public. There
is no debug route, no config dump, no "verify the key loaded" that answers with
more than a boolean.

**It refuses by default.** No key configured means every request is refused.
There is no permissive fallback, because there is no fallback.

**It is authorised per signature.** A request must name an envelope and an
approval, and the same approval cannot be used twice. That is enforced here, in
this process, rather than trusted from the caller — a caller that has been
compromised is exactly the caller whose word about authorisation is worthless.

**It knows who is asking.** `POST /sign` answers only a caller presenting
`SIGNER_CALLER_TOKEN` in `X-Signer-Caller-Token`: exec-hl-svc holds it, state-api
does not. Unset, every signing request is refused before its body is read. The
compose network limits who can connect; the token decides who may ask.

The key arrives as `SIGNER_PRIVATE_KEY` in this container's own environment. The
operator sets it; nothing else in this repository reads it, writes it, defaults
it, or logs it.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tradesync_core.hyperliquid_signing import EIP712_DOMAIN, AGENT_TYPES
from tradesync_core.durable_journal import DurableJournal, JournalError
from tradesync_core.service_tokens import SIGNER_TOKEN_ENV, SIGNER_TOKEN_HEADER, CallerTokenGuard
from tradesync_core.signer_boundary import SCHEMA_VERSION, SignerRefused, validate_signing_request
from tradesync_core.state_api_access import token_state

app = FastAPI(title="TradeSync Isolated Signer", version="0.1.0")

# Read once, at import, and never re-read. A key that can be swapped at runtime
# is a key that can be swapped by whatever caused the swap.
_PRIVATE_KEY = os.getenv("SIGNER_PRIVATE_KEY", "").strip()

# Signing is refused unless this is explicitly true, independently of the key
# being present. Two switches, so having a key configured is not by itself
# permission to use it.
SIGNING_ENABLED = os.getenv("SIGNING_ENABLED", "false").strip().lower() == "true"

MAINNET = os.getenv("SIGNER_MAINNET", "true").strip().lower() == "true"

# Who may ask for a signature: the caller presenting this token, exec-hl-svc.
# Read once, like the key, and never logged or returned; unset refuses /sign.
_CALLER_TOKEN = os.getenv(SIGNER_TOKEN_ENV, "").strip()
CALLER_TOKEN_STATE = token_state(_CALLER_TOKEN)

# A signer must remember spent approvals across the exact restart that could
# otherwise replay one. The journal contains identifiers and digests only,
# never a key, signature or order payload. Missing/unreadable storage disables
# signing; an in-memory fallback would make restart replay possible.
_JOURNAL_PATH = os.getenv("SIGNER_JOURNAL_PATH", "").strip()
_journal = DurableJournal(_JOURNAL_PATH) if _JOURNAL_PATH else None
_journal_error: str | None = None
_spent: set[str] = set()
if _journal is None:
    _journal_error = "SIGNER_JOURNAL_PATH is not configured"
else:
    try:
        _spent = {
            str(row["approval_id"])
            for row in _journal.records()
            if row.get("kind") == "approval_spent" and row.get("approval_id")
        }
    except JournalError:
        _journal_error = "the signer journal cannot be trusted"
_spent_lock = threading.Lock()

_account = None
if _PRIVATE_KEY:
    try:
        _account = Account.from_key(_PRIVATE_KEY)
    except Exception:
        # Never echo the value or its length in the failure.
        _account = None


class SignRequest(BaseModel):
    """Exactly these fields, and nothing else.

    `extra="forbid"` rather than the default. Pydantic silently discards unknown
    fields, which meant a request carrying `force` or `bypass` had them dropped
    before the boundary check could refuse it — the check was dead code at the
    HTTP layer while looking like enforcement.

    For the one process that may hold a key, an unrecognised field is fatal
    whether or not it appears on a forbidden list. Something sent a request this
    service does not understand, and guessing which parts to honour is how a
    boundary erodes.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION)
    payload_digest: str
    envelope_id: str
    approval_id: str


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    """Liveness. Says whether a key is loaded, never anything about its value."""
    return {
        "ok": True,
        "service": "signer",
        "key_loaded": _account is not None,
        "signing_enabled": SIGNING_ENABLED,
        "caller_token": CALLER_TOKEN_STATE,
    }


def _unavailable_reason() -> str | None:
    """Why this signer will not sign, the first missing switch first; None when it would."""
    if not _account:
        return "SIGNER_PRIVATE_KEY is not configured"
    if not SIGNING_ENABLED:
        return "SIGNING_ENABLED is false"
    if _journal_error:
        return _journal_error
    if CALLER_TOKEN_STATE == "disabled":
        return f"{SIGNER_TOKEN_ENV} is not configured"
    if CALLER_TOKEN_STATE == "misconfigured":
        return f"{SIGNER_TOKEN_ENV} is too short to trust"
    return None


@app.get("/signer/status")
async def status() -> dict[str, Any]:
    """What a caller may know.

    The address is public by construction — it is derivable from any signature
    this service produces — so withholding it would be theatre. Everything else
    about the key stays here.
    """
    reason = _unavailable_reason()
    return {
        "available": reason is None,
        "key_loaded": _account is not None,
        "signing_enabled": SIGNING_ENABLED,
        "caller_token": CALLER_TOKEN_STATE,
        "address": _account.address if _account else None,
        "network": "mainnet" if MAINNET else "testnet",
        "approvals_spent": len(_spent),
        "accepts": "a 32-byte digest and a single-use approval from the caller holding "
        f"{SIGNER_TOKEN_ENV}; never a payload",
        "reason": reason,
    }


@app.post("/sign")
async def sign(request: SignRequest) -> dict[str, Any]:
    """Sign one digest, once, against one approval.

    Refuses before touching the key if anything about the request is wrong, so a
    malformed or unauthorised request never reaches the signing primitive.
    """
    # Both switches, checked before anything else.
    if not SIGNING_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="SIGNING_ENABLED is false; this signer will not sign",
        )
    if _account is None:
        raise HTTPException(
            status_code=503,
            detail="no signing key is configured",
        )

    try:
        checked = validate_signing_request(request.model_dump())
    except SignerRefused as exc:
        raise HTTPException(status_code=422, detail=f"{exc.code}: {exc}")

    # Single use, enforced and fsynced here rather than trusted from the caller.
    # The approval is burned before the signature is made. A crash between the
    # two may require operator reconciliation, but can never create a replay.
    approval = checked["approval_id"]
    with _spent_lock:
        if approval in _spent:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"approval {approval} has already been signed against; its "
                    "scope is 'once'"
                ),
            )
        if _journal is None or _journal_error:
            raise HTTPException(status_code=503, detail="durable signer journal unavailable")
        try:
            _journal.append({
                "kind": "approval_spent",
                "approval_id": approval,
                "envelope_id": checked["envelope_id"],
                "payload_digest": checked["payload_digest"],
                "recorded_at_ms": int(time.time() * 1000),
            })
        except JournalError:
            raise HTTPException(status_code=503, detail="durable signer journal unavailable") from None
        _spent.add(approval)

    connection_id = bytes.fromhex(checked["payload_digest"])
    typed = {
        "domain": EIP712_DOMAIN,
        "types": AGENT_TYPES,
        "primaryType": "Agent",
        "message": {"source": "a" if MAINNET else "b", "connectionId": connection_id},
    }
    signable = encode_typed_data(full_message=typed)
    signed = _account.sign_message(signable)

    return {
        "schema_version": "signature_v1",
        "envelope_id": checked["envelope_id"],
        "approval_id": approval,
        "payload_digest": checked["payload_digest"],
        "signature": {
            "r": hex(signed.r),
            "s": hex(signed.s),
            "v": signed.v,
        },
        "address": _account.address,
        "signed_at_ms": int(time.time() * 1000),
        "network": "mainnet" if MAINNET else "testnet",
    }


# Every /sign request must present the caller token before anything else is
# read. The routes above stay registered on the FastAPI app; uvicorn serves
# app.main:app, which from here on is the guard in front of it.
app = CallerTokenGuard(app, paths={"/sign"}, env=SIGNER_TOKEN_ENV, header=SIGNER_TOKEN_HEADER, token=_CALLER_TOKEN)
