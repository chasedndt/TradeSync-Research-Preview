"""Hyperliquid's exchange actions for orders, cancels and replacements, exactly as the venue reads them.

The digest a signer signs is keccak over the msgpack encoding of the action, and
msgpack encodes a mapping in the order its keys were inserted. Two actions with
the same fields in a different key order are different bytes, so a different
digest, so a signature the venue rejects. Every builder here therefore writes
keys in the venue's own order, and ``canonical_action`` rebuilds that order for
an action that has been through storage (PostgreSQL ``jsonb`` does not keep key
order), so a stored action can be re-hashed and compared.

The formats follow Hyperliquid's published Python SDK:

- an order wire is ``{"a", "b", "p", "s", "r", "t"}`` plus ``"c"`` for a client
  order id: asset index, is-buy, limit price, size, reduce-only, order type;
- an order action is ``{"type": "order", "orders": [...], "grouping": "na"}``;
- a cancel is ``{"type": "cancel", "cancels": [{"a", "o"}]}``, or by client order
  id ``{"type": "cancelByCloid", "cancels": [{"asset", "cloid"}]}``;
- a replacement is ``{"type": "batchModify", "modifies": [{"oid", "order"}]}``;
- prices and sizes travel as decimal strings with no exponent and no trailing
  zeros ("0.01", never "1e-2" or "0.010").

A perpetual's price has at most five significant figures and at most
``6 - szDecimals`` decimals; its size has at most ``szDecimals``. Rounding here is
always in the safe direction: a size rounds down (never more than asked for), a
buy's limit rounds down and a sell's rounds up (never worse than the bound).

Nothing here holds a key, signs, or talks to the venue.
"""

from __future__ import annotations

import re
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

TIFS = frozenset({"Gtc", "Ioc", "Alo"})
MAX_WIRE_DECIMALS = 8
PERP_PRICE_DECIMALS = 6
PRICE_SIGNIFICANT_FIGURES = 5
CLOID = re.compile(r"0x[0-9a-f]{32}")


class OrderFormatError(ValueError):
    """An order could not be expressed in the venue's format, with the reason stated."""


def to_decimal(value: Any, field: str) -> Decimal:
    """A finite decimal from a string, int or Decimal; floats are refused because they are not exact."""
    if isinstance(value, bool) or isinstance(value, float):
        raise OrderFormatError(f"{field} must be a decimal string, not {type(value).__name__}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise OrderFormatError(f"{field} is not a number") from exc
    if not number.is_finite():
        raise OrderFormatError(f"{field} must be finite")
    return number


def decimal_to_wire(value: Decimal, field: str) -> str:
    """The venue's decimal string: plain notation, no trailing zeros, at most eight decimals."""
    if not value.is_finite():
        raise OrderFormatError(f"{field} must be finite")
    if value.as_tuple().exponent < -MAX_WIRE_DECIMALS:
        try:
            exact = value.quantize(Decimal(1).scaleb(-MAX_WIRE_DECIMALS)) == value
        except InvalidOperation:
            exact = False
        if not exact:
            raise OrderFormatError(f"{field} has more than {MAX_WIRE_DECIMALS} decimals")
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def round_size(size: Decimal, sz_decimals: int) -> Decimal:
    """A size cut down to the market's lot: never more than was asked for."""
    if sz_decimals < 0:
        raise OrderFormatError("szDecimals cannot be negative")
    return size.quantize(Decimal(1).scaleb(-sz_decimals), rounding=ROUND_DOWN)


def round_price(price: Decimal, sz_decimals: int, *, is_buy: bool) -> Decimal:
    """A perpetual's limit price, rounded so a buy never pays above it and a sell never takes below it."""
    if price <= 0:
        raise OrderFormatError("a limit price must be positive")
    rounding = ROUND_FLOOR if is_buy else ROUND_CEILING
    decimals = PERP_PRICE_DECIMALS - sz_decimals
    if decimals < 0:
        raise OrderFormatError("szDecimals leaves no price precision")
    integer_digits = len(str(int(price))) if price >= 1 else 0
    if integer_digits >= PRICE_SIGNIFICANT_FIGURES:
        # Whole prices are always allowed, however many digits they have.
        return price.quantize(Decimal(1), rounding=rounding)
    exponent = price.adjusted() - (PRICE_SIGNIFICANT_FIGURES - 1)
    significant = price.quantize(Decimal(1).scaleb(exponent), rounding=rounding)
    return significant.quantize(Decimal(1).scaleb(-decimals), rounding=rounding)


def order_wire(
    *,
    asset: int,
    is_buy: bool,
    limit_px: str,
    size: str,
    reduce_only: bool,
    tif: str,
    cloid: str | None = None,
) -> dict[str, Any]:
    """One limit order in the venue's key order."""
    if not isinstance(asset, int) or isinstance(asset, bool) or asset < 0:
        raise OrderFormatError("asset must be a non-negative integer index")
    if tif not in TIFS:
        raise OrderFormatError(f"tif must be one of {sorted(TIFS)}")
    if not isinstance(is_buy, bool) or not isinstance(reduce_only, bool):
        raise OrderFormatError("is_buy and reduce_only must be booleans")
    for field, text in (("limit_px", limit_px), ("size", size)):
        if not isinstance(text, str) or decimal_to_wire(to_decimal(text, field), field) != text:
            raise OrderFormatError(f"{field} must already be a venue decimal string")
        if to_decimal(text, field) <= 0:
            raise OrderFormatError(f"{field} must be positive")
    wire: dict[str, Any] = {
        "a": asset,
        "b": is_buy,
        "p": limit_px,
        "s": size,
        "r": reduce_only,
        "t": {"limit": {"tif": tif}},
    }
    if cloid is not None:
        if not isinstance(cloid, str) or not CLOID.fullmatch(cloid):
            raise OrderFormatError("cloid must be 0x followed by 32 lowercase hex characters")
        wire["c"] = cloid
    return wire


def order_action(orders: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Orders placed together, ungrouped."""
    if not orders:
        raise OrderFormatError("an order action needs at least one order")
    return {"type": "order", "orders": [canonical_order_wire(order) for order in orders], "grouping": "na"}


def cancel_action(asset: int, oid: int) -> dict[str, Any]:
    """Cancel one resting order by the venue's order id."""
    if not isinstance(oid, int) or isinstance(oid, bool) or oid <= 0:
        raise OrderFormatError("oid must be a positive integer")
    return {"type": "cancel", "cancels": [{"a": asset, "o": oid}]}


def cancel_by_cloid_action(asset: int, cloid: str) -> dict[str, Any]:
    """Cancel one resting order by its client order id."""
    if not CLOID.fullmatch(cloid or ""):
        raise OrderFormatError("cloid must be 0x followed by 32 lowercase hex characters")
    return {"type": "cancelByCloid", "cancels": [{"asset": asset, "cloid": cloid}]}


def modify_action(oid: int, order: Mapping[str, Any]) -> dict[str, Any]:
    """Replace one resting order with another in a single action (cancel/replace)."""
    if not isinstance(oid, int) or isinstance(oid, bool) or oid <= 0:
        raise OrderFormatError("oid must be a positive integer")
    return {"type": "batchModify", "modifies": [{"oid": oid, "order": canonical_order_wire(order)}]}


def canonical_order_wire(order: Mapping[str, Any]) -> dict[str, Any]:
    """An order wire rebuilt in the venue's key order, refusing any field the venue does not define."""
    allowed = {"a", "b", "p", "s", "r", "t", "c"}
    extra = sorted(set(order) - allowed)
    if extra:
        raise OrderFormatError(f"order carries fields the venue does not define: {', '.join(extra)}")
    tif = ((order.get("t") or {}).get("limit") or {}).get("tif")
    return order_wire(
        asset=order.get("a"), is_buy=order.get("b"), limit_px=order.get("p"), size=order.get("s"),
        reduce_only=order.get("r"), tif=tif, cloid=order.get("c"),
    )


def canonical_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Any action built here, rebuilt in the venue's key order so it hashes as it did when it was sent."""
    kind = action.get("type")
    if kind == "order":
        return order_action(action.get("orders") or [])
    if kind == "cancel":
        cancel = _single(action.get("cancels"), "cancels", {"a", "o"})
        return cancel_action(cancel["a"], cancel["o"])
    if kind == "cancelByCloid":
        cancel = _single(action.get("cancels"), "cancels", {"asset", "cloid"})
        return cancel_by_cloid_action(cancel["asset"], cancel["cloid"])
    if kind == "batchModify":
        modify = _single(action.get("modifies"), "modifies", {"oid", "order"})
        return modify_action(modify["oid"], modify["order"])
    raise OrderFormatError(f"unsupported action type {kind!r}")


def _single(items: Any, name: str, keys: set[str]) -> Mapping[str, Any]:
    """The one entry of a list this system only ever sends with one entry, with exactly ``keys``."""
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], Mapping):
        raise OrderFormatError(f"{name} must hold exactly one entry")
    if set(items[0]) != keys:
        raise OrderFormatError(f"{name} entry must have exactly {sorted(keys)}")
    return items[0]


def exchange_body(
    action: Mapping[str, Any], *, nonce: int, signature: Mapping[str, Any], vault_address: str | None = None
) -> dict[str, Any]:
    """The request the exchange endpoint receives: the action, its nonce, its signature, and the vault."""
    return {
        "action": dict(action),
        "nonce": nonce,
        "signature": {"r": signature["r"], "s": signature["s"], "v": signature["v"]},
        "vaultAddress": vault_address,
    }
