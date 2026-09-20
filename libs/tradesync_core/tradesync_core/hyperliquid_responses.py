"""What the Hyperliquid exchange endpoint said about an order, cancel or replacement, read strictly.

Three outcomes, and the difference between them decides what happens next:

- **answered**: the venue processed the action and said, for every order in it,
  exactly one of ``resting`` (on the book, with its order id), ``filled`` (with
  total size, average price and order id) or ``error`` (refused, with the reason).
- **refused**: the whole action was rejected before it was processed
  (``{"status": "err", "response": "..."}``). Nothing was placed.
- **ambiguous**: anything else. A missing status, an unexpected shape, the wrong
  number of statuses, a status this reader does not know. The action may or may
  not have reached the book, so the delivery is unknown and must be reconciled
  before anything else is sent on that market. Guessing here is how a second,
  duplicate order gets placed.

Nothing here talks to the venue. It reads a body another module received.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ANSWERED = "answered"
REFUSED = "refused"
AMBIGUOUS = "ambiguous"

# A venue message is quoted, never trusted to be short.
MAX_MESSAGE_CHARS = 300


@dataclass(frozen=True)
class OrderStatus:
    """One order's fate: resting, filled or error."""

    state: str
    oid: int | None = None
    cloid: str | None = None
    total_size: str | None = None
    average_price: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state, "oid": self.oid, "cloid": self.cloid, "total_size": self.total_size,
            "average_price": self.average_price, "message": self.message,
        }


@dataclass(frozen=True)
class VenueReading:
    """The outcome of one exchange request and, when answered, a status per order or cancel."""

    outcome: str
    statuses: tuple[Any, ...] = ()
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "statuses": [s.to_dict() if isinstance(s, OrderStatus) else s for s in self.statuses],
            "detail": self.detail,
        }


def _quote(value: Any) -> str:
    return str(value)[:MAX_MESSAGE_CHARS]


def _statuses(body: Any, expected_type: str, expected_count: int) -> tuple[VenueReading | None, list[Any]]:
    """The raw status list of an ok answer, or the reading that ends parsing early."""
    if not isinstance(body, dict):
        return VenueReading(AMBIGUOUS, detail="the venue's answer is not a JSON object"), []
    status = body.get("status")
    if status == "err":
        return VenueReading(REFUSED, detail=_quote(body.get("response"))), []
    if status != "ok":
        return VenueReading(AMBIGUOUS, detail=f"unexpected status {_quote(status)!r}"), []
    response = body.get("response")
    if not isinstance(response, dict) or response.get("type") != expected_type:
        return VenueReading(AMBIGUOUS, detail=f"expected a {expected_type} response"), []
    raw = (response.get("data") or {}).get("statuses") if isinstance(response.get("data"), dict) else None
    if not isinstance(raw, list) or len(raw) != expected_count:
        return VenueReading(AMBIGUOUS, detail=f"expected {expected_count} status(es)"), []
    return None, raw


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def read_order_answer(body: Any, expected_count: int = 1) -> VenueReading:
    """Read the answer to an order or batchModify action; a replacement answers as an order."""
    early, raw = _statuses(body, "order", expected_count)
    if early is not None:
        return early
    parsed: list[OrderStatus] = []
    for item in raw:
        if not isinstance(item, dict) or len(item) != 1:
            return VenueReading(AMBIGUOUS, detail="an order status is not one of resting, filled or error")
        (kind, value), = item.items()
        if kind == "error" and isinstance(value, str):
            parsed.append(OrderStatus("error", message=_quote(value)))
            continue
        if kind not in ("resting", "filled") or not isinstance(value, dict) or _positive_int(value.get("oid")) is None:
            return VenueReading(AMBIGUOUS, detail=f"unrecognised order status {_quote(kind)!r}")
        cloid = value.get("cloid") if isinstance(value.get("cloid"), str) else None
        if kind == "resting":
            parsed.append(OrderStatus("resting", oid=value["oid"], cloid=cloid))
            continue
        total, average = value.get("totalSz"), value.get("avgPx")
        if not isinstance(total, str) or not isinstance(average, str):
            return VenueReading(AMBIGUOUS, detail="a fill without its size and average price")
        parsed.append(OrderStatus("filled", oid=value["oid"], cloid=cloid, total_size=total, average_price=average))
    return VenueReading(ANSWERED, tuple(parsed))


def read_cancel_answer(body: Any, expected_count: int = 1) -> VenueReading:
    """Read the answer to a cancel: ``"success"`` or ``{"error": ...}`` per order."""
    early, raw = _statuses(body, "cancel", expected_count)
    if early is not None:
        return early
    parsed: list[OrderStatus] = []
    for item in raw:
        if item == "success":
            parsed.append(OrderStatus("cancelled"))
        elif isinstance(item, dict) and set(item) == {"error"} and isinstance(item["error"], str):
            parsed.append(OrderStatus("error", message=_quote(item["error"])))
        else:
            return VenueReading(AMBIGUOUS, detail="a cancel status is neither success nor error")
    return VenueReading(ANSWERED, tuple(parsed))
