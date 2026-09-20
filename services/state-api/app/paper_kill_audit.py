"""The kill-switch close audit row, written by whichever path fills a kill-switch exit.

An exit the displayed book cannot fill stays owed and closes at a later observation,
which may be the monitor's own retry (``paper_kill_switch``) or the observer's next tick
(``managed_paper.update``). Both store the close through the same lifecycle, so both
record the same row here: the operator and reason of the kill that owed the exit, frozen
on the exit itself, the rule that coincided with it, and whether the exit was held before
it filled. It is written in the transaction that stores the close, so a kill-switch close
is never recorded without its audit row.
"""

from __future__ import annotations

from typing import Any, Mapping

from app import paper_control_store as control
from tradesync_core.paper_kill import EXIT_REASON, close_audit

MISSING_AUTHORITY = "Kill-switch close without an operator and reason to audit"


def killed(state: Any) -> Mapping[str, Any] | None:
    """The exit record of a stored close the kill switch owns, or None for any other close."""
    if not isinstance(state, Mapping) or state.get("status") != "closed":
        return None
    record = state.get("exit")
    return record if isinstance(record, Mapping) and record.get("rule") == EXIT_REASON else None


async def record_close(conn, position_id: Any, symbol: str, state: Any, *, filled_by: str) -> bool:
    """Audit one kill-switch close; False when the stored close is not the kill switch's."""
    record = killed(state)
    if record is None:
        return False
    authority = record.get("kill_switch") if isinstance(record.get("kill_switch"), Mapping) else {}
    operator, reason = authority.get("operator"), authority.get("reason")
    if not operator or not reason:
        # An exit owed before its kill recorded the authority: the kill still standing owns it.
        current = await control.kill_state(conn)
        operator = operator or (current["operator"] if current is not None else None)
        reason = reason or (current["reason"] if current is not None else None)
    if not operator or not reason:
        raise ValueError(MISSING_AUTHORITY)
    await control.kill_event(conn, action="close", operator=operator, reason=reason, position_id=position_id,
                             detail=close_audit(symbol, state, filled_by=filled_by))
    return True
