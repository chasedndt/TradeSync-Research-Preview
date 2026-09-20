"""The comparisons over frozen entry evidence, declared before any of them was measured.

Every comparison asks the same question in the same shape: *had the signal only
been acted on when this context reading passed its threshold, would the result
per original opportunity have been better?* Each is a retrospective ablation of
the signal's own calls, never a strategy and never a promotion.

Declaring the whole family in one frozen place is the point. A threshold chosen
after seeing the answer is not evidence, and a family quietly extended until one
cell clears is not evidence either. These are fixed here, with a digest, so a
reading can prove it measured exactly what was declared:

- both polarities of every variable, because a context can be usefully
  contrarian and testing for that costs an adjustment, not a decision;
- one threshold per variable, carried over from the frozen v1 ablation (0.2) for
  the balance readings, and a plain sign rule where the variable has no natural
  scale;
- every cell, at every horizon, corrected together (``multiple_testing``).

Changing a threshold, a polarity or the list is a new ``FAMILY_VERSION``: results
gathered under one declaration are not evidence for another.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .source_comparison import THRESHOLD as BALANCE_THRESHOLD

FAMILY_VERSION = "entry-evidence-ablation-v1"

POLARITIES = (("as_read", 1), ("inverted", -1))


@dataclass(frozen=True)
class Declaration:
    """One context variable, its fixed threshold, and what passing it is supposed to mean."""

    variable: str
    label: str
    item: str
    unit: str
    aligned: bool
    threshold: float
    hypothesis: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DECLARATIONS: tuple[Declaration, ...] = (
    Declaration(
        variable="book_imbalance",
        label="Resting liquidity balance near price",
        item="resting_liquidity",
        unit="share of displayed notional, -1 to +1",
        aligned=True,
        threshold=BALANCE_THRESHOLD,
        hypothesis="Displayed depth leaning the call's way marks the side with less resting supply to absorb it.",
    ),
    Declaration(
        variable="wall_asymmetry",
        label="Largest resting wall behind against in front",
        item="resting_liquidity",
        unit="share of the two walls' notional, -1 to +1",
        aligned=True,
        threshold=BALANCE_THRESHOLD,
        hypothesis="A large wall behind the entry supports it; a larger one in front is what the move has to clear.",
    ),
    Declaration(
        variable="liquidation_skew",
        label="Liquidations received in the hour before entry",
        item="liquidations",
        unit="share of liquidated notional, -1 to +1",
        aligned=True,
        threshold=BALANCE_THRESHOLD,
        hypothesis="Forced exits push price the way the call pointed; inverted, they mark the exhaustion that reverses it.",
    ),
    Declaration(
        variable="open_interest_change_1h_pct",
        label="Open-interest change in the hour before entry",
        item="open_interest",
        unit="percent",
        aligned=False,
        threshold=0.0,
        hypothesis="Positions being opened mark conviction behind the move; inverted, positions being closed mark it ending.",
    ),
    Declaration(
        variable="funding_received_bps_hour",
        label="Funding the position would receive",
        item="open_interest",
        unit="basis points an hour",
        aligned=True,
        threshold=0.0,
        hypothesis="Being paid to hold marks the crowded side as the other one; inverted, paying marks the side with momentum.",
    ),
    Declaration(
        variable="horizon_lean",
        label="Measured timeframe lean",
        item="horizon_measurement",
        unit="-1, 0 or +1",
        aligned=True,
        threshold=1.0,
        hypothesis="A measured lean agreeing with the call marks a trade with the timeframe rather than against it.",
    ),
)

RULE = (
    "A trade is retained when the variable, multiplied by the polarity, is at least the declared "
    "threshold. Missing context abstains and is counted separately; it is never read as a zero. "
    "A reading of exactly zero passes both polarities of a sign rule."
)


def cells() -> list[dict[str, Any]]:
    """Every declared cell, before any horizon is attached: one per variable per polarity."""
    return [
        {**declaration.to_dict(), "polarity": name, "sign": sign,
         "keeps": f"{declaration.variable} x {sign} >= {declaration.threshold}"}
        for declaration in DECLARATIONS
        for name, sign in POLARITIES
    ]


def digest() -> str:
    """SHA-256 over the frozen declaration, so a reading can prove what it measured."""
    frozen = {"version": FAMILY_VERSION, "rule": RULE, "cells": cells()}
    return hashlib.sha256(
        json.dumps(frozen, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def to_dict() -> dict[str, Any]:
    """The declaration as a reading reports it."""
    return {"version": FAMILY_VERSION, "rule": RULE, "cells": cells(), "sha256": digest(),
            "authority": "research_only", "promotion_allowed": False}
