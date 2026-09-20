"""Request bodies for the agent harness kill switch: the operator's stop or start, and the host control process's claim and report."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.paper_risk_models import Audited


class HarnessChange(Audited):
    """Stop or start the agent harness: an operator, a reason of 5 to 240 characters, and an explicit confirmation."""

    desired_state: Literal["running", "stopped"]
    confirm: Literal[True]


class HostClaim(BaseModel):
    command_id: uuid.UUID


class HostReport(BaseModel):
    """What the host control process ran, its exit status, and ``systemctl --user is-active`` afterwards."""

    command_id: uuid.UUID
    status: Literal["applied", "failed"]
    command: str = Field(min_length=1, max_length=400)
    exit_status: int | None = Field(None, ge=-(2**31), le=2**31 - 1)
    is_active: str = Field(min_length=1, max_length=80)
    detail: str = Field("", max_length=600)
