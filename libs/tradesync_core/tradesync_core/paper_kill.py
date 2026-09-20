"""The kill switch's close of one open paper position, through the managed-paper close.

The close is the lifecycle's own operator close on a fresh observed book: the exit
walks the displayed depth for the position's quantity, the taker fee is charged at that
fill, and funding is netted from the settled rows passed in (``funding_rows``). Only the
recorded rule differs: ``kill_switch``. A stop, target or expiry the same observation
fires is kept beside it as ``coincided_rule``.

When the displayed book cannot take the whole quantity the lifecycle does not assume a
fill: the exit stays owed (``pending_exit``) and fills at the first later observation
that can. The owed exit carries the ``kill_switch`` rule, the rule that coincided with
it, and the operator and reason of the kill that owed it, so whichever observation fills
it — the monitor's own retry or the observer's next tick — records the same close and
audits it the same way (``close_audit``). A missing, stale, out-of-order or one-sided
book raises and nothing changes.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from tradesync_core.managed_paper import advance
from tradesync_core.paper_observations import observed_time

EXIT_REASON = "kill_switch"


def _labelled(record: Mapping[str, Any], authority: Mapping[str, Any] | None) -> dict[str, Any]:
    natural = record.get("rule")
    labelled = {**record, "rule": EXIT_REASON}
    if natural not in (None, "operator_close", EXIT_REASON):
        labelled["coincided_rule"] = natural
    if authority is not None and "kill_switch" not in labelled:
        # The kill that owed this exit, frozen on the exit: a later fill audits that kill, not a newer one.
        labelled["kill_switch"] = dict(authority)
    return labelled


def kill_close(position: Mapping[str, Any], book: Mapping[str, Any], now_s: float, *,
               funding_rows: Sequence[Mapping[str, Any]] | None = None,
               operator: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """The position closed for the kill switch, or still open with the kill-switch exit owed."""
    if position.get("status") != "open":
        raise ValueError("Only an open paper position can be closed by the kill switch")
    authority = {"operator": operator, "reason": reason} if operator and reason else None
    result = advance(dict(position), book, now_s, manual_close=True, funding_rows=funding_rows)
    if result.get("status") == "closed":
        result["exit"] = _labelled(result["exit"], authority)
        result["exit_reason"] = EXIT_REASON
    elif result.get("pending_exit"):
        result["pending_exit"] = _labelled(result["pending_exit"], authority)
    else:
        raise ValueError("The lifecycle neither closed the position nor recorded an owed exit")
    return result


def close_audit(symbol: str, state: Mapping[str, Any], *, filled_by: str) -> dict[str, Any]:
    """What a kill-switch close records: the fill, any rule that coincided, and whether the exit was held first."""
    record = state.get("exit") or {}
    fired_at = observed_time(record.get("trigger_observation") or {})
    filled_at = observed_time(record.get("fill_observation") or {})
    return {"symbol": symbol, "exit_price": state.get("exit_price"), "exit_time": state.get("exit_time"),
            "coincided_rule": record.get("coincided_rule"), "filled_by": filled_by,
            "held": fired_at is not None and filled_at is not None and filled_at != fired_at,
            "fired_at": fired_at, "filled_at": filled_at}
