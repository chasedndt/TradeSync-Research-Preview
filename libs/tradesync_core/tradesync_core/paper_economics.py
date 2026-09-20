"""What each managed paper position cost and earned, and what the closed ones earned on average.

Every figure comes from the position's own lifecycle state, as the lifecycle recorded it; nothing here reads a
market or re-prices a fill. Per position:

- **excursions**: maximum favourable and adverse excursion (``paper_excursions``);
- **fees**: the taker fee charged on the entry fill and on each exit fill; while open, the exit fee is the
  lifecycle's estimate at its latest mark and is labelled as one;
- **funding**: Hyperliquid's settled hourly funding, with the hours still unpublished listed;
- **modelled slippage**: the cost against the mid of the entry and exit fills, walked through the observed
  book (``paper_depth``). It is already inside the fill prices and is never subtracted again;
- **realised P&L** for a closed position: gross from the fills, less fees, less funding. It stays
  provisional while an hour of funding it held is still unpublished.

Expectancy
----------

For ``n`` closed positions with realised results ``x_1 .. x_n`` (USDC)::

    E = (x_1 + ... + x_n) / n = w * W - l * L

where ``w`` and ``l`` are the shares of winners (``x > 0``) and losers (``x < 0``), ``W`` the mean winner
and ``L`` the mean size of a loser. The same mean is taken in units of planned risk, ``r_i = x_i / R_i``
with ``R_i`` the planned risk frozen at entry, so positions of different sizes weigh alike. The sample size
travels with both. With no closed position there is no expectancy, never a zero.

Worked example: three closed positions, +3.00, -1.00 and -0.50 USDC, with planned risk 2, 2 and 1 USDC.
``E = (3 - 1 - 0.5) / 3 = 0.50`` USDC, which is also ``1/3 * 3.00 - 2/3 * 0.75``. In units of risk the
results are +1.5, -0.5 and -0.5, so ``E_R = 0.5 / 3 = 0.1667``. Three positions describe those three
positions; they are not evidence of an edge.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from . import paper_excursions as excursions

SCHEMA_VERSION = "paper_economics_v1"
IDENTITY_TOLERANCE_USDC = 1e-9

NOTE = ("Figures are the lifecycle's own: fills walked through observed books, the published taker fee and settled "
        "Hyperliquid funding. Slippage is inside the fill prices and is not subtracted again. Expectancy is the mean "
        "realised result of the closed positions shown, with its sample size; it is not evidence of an edge.")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def fees(state: Mapping[str, Any]) -> dict[str, Any]:
    record, closed = _mapping(state.get("fees")), state.get("status") == "closed"
    return {"rate": _number(record.get("rate")), "liquidity": record.get("liquidity"),
            "entry_usdc": _number(record.get("entry_usdc")),
            "exit_usdc": _number(record.get("exit_usdc")) if closed else None,
            "exit_estimate_usdc": None if closed else _number(record.get("exit_estimate_usdc")),
            "total_usdc": _number(state.get("fees_usdc")),
            "basis": "the taker fee on the entry fill and on each exit fill" if closed
            else "the taker fee on the entry fill, and the exit fee estimated at the latest mark"}


def funding(state: Mapping[str, Any]) -> dict[str, Any]:
    record = _mapping(state.get("funding"))
    missing = record.get("missing_hours")
    return {"model": record.get("model"), "accrued_usdc": _number(state.get("funding_usdc")),
            "settled_hours": record.get("settled_hours"), "expected_hours": record.get("expected_hours"),
            "missing_hours": list(missing) if isinstance(missing, list) else [], "status": record.get("status"),
            "basis": "settled hourly funding; positive is paid, negative received"}


def _leg(fill: Any) -> dict[str, Any] | None:
    record = _mapping(fill)
    if not record:
        return None
    return {"cost_usdc": _number(record.get("cost_usdc")), "cost_bps": _number(record.get("cost_bps")),
            "half_spread_bps": _number(record.get("half_spread_bps")), "depth_bps": _number(record.get("depth_bps")),
            "basis": record.get("basis"), "parts": record.get("parts")}


def slippage(state: Mapping[str, Any]) -> dict[str, Any]:
    record = _mapping(state.get("slippage"))
    entry, exit_leg = _leg(record.get("entry")), _leg(record.get("exit"))
    costs = [leg["cost_usdc"] for leg in (entry, exit_leg) if leg is not None]
    known = all(cost is not None for cost in costs) and bool(costs)
    return {"model": record.get("model"), "entry": entry, "exit": exit_leg,
            "total_usdc": math.fsum(costs) if known else None,
            "basis": "cost against the mid inside the fill prices; not subtracted again"}


def pnl(state: Mapping[str, Any]) -> dict[str, Any]:
    gross, fee, paid = (_number(state.get(key)) for key in ("gross_pnl_usdc", "fees_usdc", "funding_usdc"))
    net = _number(state.get("net_estimate_usdc"))
    closed = state.get("status") == "closed"
    identity = None if None in (gross, fee, paid, net) else abs(net - (gross - fee - paid)) <= IDENTITY_TOLERANCE_USDC * max(1.0, abs(gross))
    provisional = closed and _mapping(state.get("funding")).get("status") == "awaiting_rows"
    return {"gross_usdc": gross, "fees_usdc": fee, "funding_usdc": paid,
            "realised_usdc": net if closed else None, "unrealised_estimate_usdc": None if closed else net,
            "net_equals_gross_less_fees_less_funding": identity, "provisional": provisional,
            "basis": ("realised at the exit fills, provisional until every funding hour it held is published" if closed
                      else "an estimate if closed at the latest observed book")}


def _excursions(state: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return excursions.summary(state)
    except ValueError as exc:  # a state without a side or a usable entry says so rather than failing the reading
        return {"model": excursions.MODEL, "status": "unreadable", "reason": str(exc), "basis": excursions.BASIS,
                "observations": None, "favourable": None, "adverse": None}


def position(position_id: Any, symbol: str, state: Mapping[str, Any], *, opportunity_id: Any = None,
             opened_at: str | None = None, updated_at: str | None = None) -> dict[str, Any]:
    """One position's economics, read from its lifecycle state."""
    closed = state.get("status") == "closed"
    figures = pnl(state)
    risk = _number(state.get("planned_risk_usdc"))
    realised = figures["realised_usdc"]
    return {
        "position_id": str(position_id), "opportunity_id": None if opportunity_id is None else str(opportunity_id),
        "symbol": symbol, "status": state.get("status"), "side": state.get("side"), "style": state.get("style"),
        "lifecycle_version": state.get("version"), "opened_at": opened_at, "updated_at": updated_at,
        "entry_time": _number(state.get("entry_time")), "entry_price": _number(state.get("entry_price")),
        "quantity": _number(state.get("quantity")), "notional_usdc": _number(state.get("notional")),
        "exit_time": _number(state.get("exit_time")) if closed else None,
        "exit_price": _number(state.get("exit_price")) if closed else None,
        "exit_reason": state.get("exit_reason") if closed else None,
        "planned_risk_usdc": risk,
        "r_multiple": realised / risk if realised is not None and risk else None,
        "excursions": _excursions(state),
        "fees": fees(state), "funding": funding(state), "slippage": slippage(state), "pnl": figures,
        "observation_gap": bool(state.get("observation_gap")),
    }


def _mean(values: list[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def expectancy(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Mean realised result of the closed positions among ``rows``, in USDC and in units of planned risk."""
    closed = [row for row in rows if row.get("status") == "closed" and _mapping(row.get("pnl")).get("realised_usdc") is not None]
    results = [float(row["pnl"]["realised_usdc"]) for row in closed]
    risked = [float(row["r_multiple"]) for row in closed if row.get("r_multiple") is not None]
    wins, losses = [x for x in results if x > 0], [x for x in results if x < 0]
    n = len(results)
    base = {"sample_size": n, "sample_size_r": len(risked),
            "provisional": sum(1 for row in closed if row["pnl"].get("provisional")),
            "with_observation_gap": sum(1 for row in closed if row.get("observation_gap"))}
    if n == 0:
        return {**base, "expectancy_usdc": None, "expectancy_r": None, "win_rate": None, "loss_rate": None,
                "mean_win_usdc": None, "mean_loss_usdc": None, "total_realised_usdc": None,
                "reason": "no closed paper position in this reading"}
    return {**base, "expectancy_usdc": math.fsum(results) / n, "expectancy_r": _mean(risked),
            "win_rate": len(wins) / n, "loss_rate": len(losses) / n, "flat": n - len(wins) - len(losses),
            "mean_win_usdc": _mean(wins), "mean_loss_usdc": _mean([-x for x in losses]),
            "total_realised_usdc": math.fsum(results), "reason": None,
            "basis": "mean realised result per closed position; in units of risk, realised over the planned risk frozen at entry"}
