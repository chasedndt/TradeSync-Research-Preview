"""The bounded reads behind the audit export's paper sections: rehearsals, managed paper positions, lifecycle events.

Each query names its columns and is bounded by the same window and cap as the other sections, reading one row
past the cap so truncation can be told. Rows are shaped by ``tradesync_core.audit_export_paper``, which the
export then narrows to its declared columns and scrubs, so this file is not the only guarantee.

Managed paper positions are windowed by ``updated_at``: an observation, a close or a late funding settlement
writes the row, so a position active in the window is in it wherever it was opened. Lifecycle events are read
per position through the ``(position_id, created_at)`` index, and the fifteen-second observation ticks are
counted there rather than read, so no stored book is loaded for a tick.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app import heavy_query
from app.json_util import as_json
from tradesync_core import audit_export_paper as paper

REHEARSALS_SQL = """
SELECT r.id::text AS id, r.created_at, r.opportunity_id::text AS opportunity_id, r.symbol, r.direction, r.size_usd,
       r.status, r.plan, r.risk_verdict, r.fill, r.market, o.links->>'evidence_digest' AS evidence_digest
FROM paper_rehearsals r
LEFT JOIN opportunities o ON o.id = r.opportunity_id
WHERE r.created_at > now() - make_interval(days => $1)
ORDER BY r.created_at DESC
LIMIT $2
"""

POSITIONS_SQL = """
SELECT p.id::text AS id, p.opportunity_id::text AS opportunity_id, p.symbol, p.created_at, p.updated_at,
       p.evidence_sha256, p.position_state, o.links->>'evidence_digest' AS evidence_digest,
       ev.events, ev.observation_events, ev.first_event_at, ev.last_event_at
FROM managed_paper_positions p
LEFT JOIN opportunities o ON o.id = p.opportunity_id
LEFT JOIN LATERAL (
  SELECT count(*) AS events, count(*) FILTER (WHERE kind = 'observed') AS observation_events,
         min(created_at) AS first_event_at, max(created_at) AS last_event_at
  FROM managed_paper_events WHERE position_id = p.id
) ev ON true
WHERE p.updated_at > now() - make_interval(days => $1)
ORDER BY p.created_at DESC
LIMIT $2
"""

EVENTS_SQL = """
SELECT e.id::text AS id, e.position_id::text AS position_id, p.symbol, e.created_at, e.kind, e.payload
FROM managed_paper_positions p
JOIN managed_paper_events e ON e.position_id = p.id
WHERE p.updated_at > now() - make_interval(days => $1)
  AND e.created_at > now() - make_interval(days => $1)
  AND e.kind <> 'observed'
ORDER BY e.created_at DESC, e.id
LIMIT $2
"""

JSON_COLUMNS = ("plan", "risk_verdict", "fill", "market")


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _plain(record: Any) -> dict[str, Any]:
    return {key: _iso(value) for key, value in dict(record).items()}


def rehearsal_row(record: Any) -> dict[str, Any]:
    row = _plain(record)
    for column in JSON_COLUMNS:
        row[column] = as_json(row.get(column))
    return row


def position_row(record: Any) -> dict[str, Any]:
    return paper.position_row({**_plain(record), "position_state": as_json(dict(record).get("position_state"))})


def event_row(record: Any) -> dict[str, Any]:
    return paper.event_row({**_plain(record), "payload": as_json(dict(record).get("payload"))})


PAPER_SECTION_SQL = {
    "paper_rehearsals": ("audit:paper-rehearsals", REHEARSALS_SQL, rehearsal_row),
    "paper_positions": ("audit:paper-positions", POSITIONS_SQL, position_row),
    "paper_position_events": ("audit:paper-position-events", EVENTS_SQL, event_row),
}


async def fetch_section(conn, name: str, days: int, cap: int, probe: int) -> list[dict[str, Any]]:
    """One paper section's rows over the window, bounded, recorded and shaped."""
    read_name, sql, shape = PAPER_SECTION_SQL[name]
    return [shape(record) for record in await heavy_query.fetch(conn, read_name, sql, days, cap + probe)]
