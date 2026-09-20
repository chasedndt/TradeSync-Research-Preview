"""Whether an order declared reduce-only can only reduce the position it is meant for.

The venue enforces reduce-only itself, and this is not a replacement for that.
It is the check made before a signature is requested, from the position the
venue reported, so an order that would add exposure is refused on this side of
the signer rather than discovered on the other side of it.

A reduce-only order may only trade against the position (sell a long, buy a
short) and may not be larger than it: the excess would open the opposite side,
which is new exposure however the order is labelled.
"""

from __future__ import annotations

from decimal import Decimal


def exposure_refusal(*, position_size: Decimal, is_buy: bool, size: Decimal, reduce_only: bool) -> str | None:
    """Why this order would increase exposure while declared reduce-only; None when it cannot.

    ``position_size`` is signed as the venue reports it (``szi``): positive long,
    negative short, zero flat. Orders not declared reduce-only are judged by the
    risk and canary checks, not here.
    """
    if not reduce_only:
        return None
    if size <= 0:
        return "a reduce-only order needs a positive size"
    if position_size == 0:
        return "there is no position to reduce, so a reduce-only order could only open one"
    if (position_size > 0) == is_buy:
        side = "long" if position_size > 0 else "short"
        return f"the position is {side} and this order trades the same side, which would increase it"
    if size > abs(position_size):
        return f"the order ({size}) is larger than the position ({abs(position_size)}); the excess would open the opposite side"
    return None
