"""The exact order a decision authorises, fixed before anyone approves it, and its digest.

An approval that covers "buy about $250 of BTC" covers every order a compromised
or buggy executor could build from that sentence. An approval that covers this
document covers one order: one asset index, one side, one size in coins, one
limit price, one time-in-force, one client order id, on one network, under one
risk policy. ``intent_digest`` is the SHA-256 of its canonical JSON, and it is
that digest an approval is bound to, that execute checks before an approval is
consumed, and that exec-hl-svc checks again before it asks for a signature.

Size and price are computed here once, from the reference price observed when
the intent was built and the market's ``szDecimals``, and travel as the venue's
decimal strings. Nothing downstream recomputes them from a newer price: if the
market has moved past the slippage bound, the order is refused as stale and a
new intent needs a new approval.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from typing import Any, Mapping

from .control_envelope import canonical_hash
from .hyperliquid_orders import (
    CLOID,
    TIFS,
    OrderFormatError,
    decimal_to_wire,
    order_wire,
    round_price,
    round_size,
    to_decimal,
)

SCHEMA_VERSION = "order_intent_v1"
ENVIRONMENTS = frozenset({"mainnet", "testnet"})
SIDES = frozenset({"buy", "sell"})
MAX_SLIPPAGE_BPS = 500
_SYMBOL = re.compile(r"[A-Z0-9]{1,20}-PERP")
_DIGEST = re.compile(r"[0-9a-f]{64}")

FIELDS = (
    "schema_version", "decision_id", "venue", "environment", "symbol", "coin", "asset", "sz_decimals",
    "side", "size", "limit_px", "reduce_only", "tif", "cloid", "reference_px", "max_slippage_bps",
    "market_observed_at_ms", "strategy_version", "policy_digest",
)


class IntentError(ValueError):
    """An order intent could not be built or is not one this system builds."""


def cloid_for(decision_id: str, purpose: str = "order") -> str:
    """The client order id for one decision's order, derived so a retry can never mint a second one."""
    raw = hashlib.sha256(f"tradesync:{purpose}:{decision_id}".encode("utf-8")).hexdigest()
    return "0x" + raw[:32]


def build_intent(
    *,
    decision_id: str,
    symbol: str,
    side: str,
    size_usd: str,
    reference_px: str,
    asset: int,
    sz_decimals: int,
    max_slippage_bps: int,
    environment: str,
    market_observed_at_ms: int,
    reduce_only: bool = False,
    tif: str = "Ioc",
    strategy_version: str | None = None,
    policy_digest: str | None = None,
) -> dict[str, Any]:
    """One exact order: size cut to the lot, limit at the slippage bound, both rounded in the safe direction."""
    if side not in SIDES:
        raise IntentError("side must be buy or sell")
    if not isinstance(max_slippage_bps, int) or isinstance(max_slippage_bps, bool) or not 0 < max_slippage_bps <= MAX_SLIPPAGE_BPS:
        raise IntentError(f"max_slippage_bps must be an integer from 1 to {MAX_SLIPPAGE_BPS}")
    try:
        reference = to_decimal(reference_px, "reference_px")
        notional = to_decimal(size_usd, "size_usd")
        if reference <= 0 or notional <= 0:
            raise IntentError("size_usd and reference_px must be positive")
        is_buy = side == "buy"
        size = round_size(notional / reference, sz_decimals)
        if size <= 0:
            raise IntentError(f"${size_usd} is less than one lot at {reference_px}")
        bound = reference * (Decimal(10_000 + max_slippage_bps) if is_buy else Decimal(10_000 - max_slippage_bps)) / Decimal(10_000)
        limit = round_price(bound, sz_decimals, is_buy=is_buy)
        intent = {
            "schema_version": SCHEMA_VERSION,
            "decision_id": str(decision_id),
            "venue": "hyperliquid",
            "environment": environment,
            "symbol": symbol,
            "coin": symbol.removesuffix("-PERP"),
            "asset": asset,
            "sz_decimals": sz_decimals,
            "side": side,
            "size": decimal_to_wire(size, "size"),
            "limit_px": decimal_to_wire(limit, "limit_px"),
            "reduce_only": reduce_only,
            "tif": tif,
            "cloid": cloid_for(str(decision_id)),
            "reference_px": decimal_to_wire(reference, "reference_px"),
            "max_slippage_bps": max_slippage_bps,
            "market_observed_at_ms": market_observed_at_ms,
            "strategy_version": strategy_version,
            "policy_digest": policy_digest,
        }
    except OrderFormatError as exc:
        raise IntentError(str(exc)) from exc
    return validate_intent(intent)


def validate_intent(intent: Mapping[str, Any]) -> dict[str, Any]:
    """The intent, if it is exactly one this module builds; raises naming the first thing wrong."""
    if not isinstance(intent, Mapping) or set(intent) != set(FIELDS):
        raise IntentError(f"an order intent has exactly the fields {', '.join(FIELDS)}")
    checks = (
        (intent["schema_version"] == SCHEMA_VERSION, "schema_version"),
        (isinstance(intent["decision_id"], str) and 0 < len(intent["decision_id"]) <= 64, "decision_id"),
        (intent["venue"] == "hyperliquid", "venue"),
        (intent["environment"] in ENVIRONMENTS, "environment"),
        (isinstance(intent["symbol"], str) and bool(_SYMBOL.fullmatch(intent["symbol"])), "symbol"),
        (intent["coin"] == str(intent["symbol"]).removesuffix("-PERP"), "coin"),
        (_non_negative_int(intent["asset"]), "asset"),
        (_non_negative_int(intent["sz_decimals"]) and intent["sz_decimals"] <= 6, "sz_decimals"),
        (intent["side"] in SIDES, "side"),
        (isinstance(intent["reduce_only"], bool), "reduce_only"),
        (intent["tif"] in TIFS, "tif"),
        (isinstance(intent["cloid"], str) and bool(CLOID.fullmatch(intent["cloid"])), "cloid"),
        (_non_negative_int(intent["max_slippage_bps"]) and 0 < intent["max_slippage_bps"] <= MAX_SLIPPAGE_BPS, "max_slippage_bps"),
        (_non_negative_int(intent["market_observed_at_ms"]) and intent["market_observed_at_ms"] > 0, "market_observed_at_ms"),
        (intent["strategy_version"] is None or isinstance(intent["strategy_version"], str), "strategy_version"),
        (intent["policy_digest"] is None or (isinstance(intent["policy_digest"], str) and bool(_DIGEST.fullmatch(intent["policy_digest"]))), "policy_digest"),
    )
    for ok, field in checks:
        if not ok:
            raise IntentError(f"order intent field {field} is not valid")
    try:
        intent_order_wire(intent)
        to_decimal(intent["reference_px"], "reference_px")
    except OrderFormatError as exc:
        raise IntentError(str(exc)) from exc
    return {field: intent[field] for field in FIELDS}


def intent_digest(intent: Mapping[str, Any]) -> str:
    """SHA-256 of the intent's canonical JSON: the one value an approval binds."""
    return canonical_hash(validate_intent(intent))


def intent_order_wire(intent: Mapping[str, Any]) -> dict[str, Any]:
    """The venue order this intent describes, in the venue's key order."""
    return order_wire(
        asset=intent["asset"], is_buy=intent["side"] == "buy", limit_px=intent["limit_px"], size=intent["size"],
        reduce_only=intent["reduce_only"], tif=intent["tif"], cloid=intent["cloid"],
    )


def notional_bound_usd(intent: Mapping[str, Any]) -> Decimal:
    """The most this order can cost or raise: size times the limit price."""
    return to_decimal(intent["size"], "size") * to_decimal(intent["limit_px"], "limit_px")


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
