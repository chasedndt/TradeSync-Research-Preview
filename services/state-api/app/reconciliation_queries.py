"""The bounded reads behind the reconciliation views.

Every one of these covers a whole table over a window, which is exactly the
shape of read that preceded the crash resets of 13 and 15 September, so they all
go through ``heavy_query``: parallel workers off, a server-side statement
timeout, and the duration recorded under a name. Read-only by construction --
each is a single ``SELECT`` inside the transaction ``heavy_query`` opens.

Every row comes back JSON-safe: identifiers as text, times as epoch seconds for
the arithmetic the views do, and stored JSON decoded. The views then compare
records without knowing anything about asyncpg.
"""

from __future__ import annotations

from typing import Any

from app import heavy_query
from app.json_util import as_json

DEFAULT_WINDOW_HOURS = 24
MAX_WINDOW_HOURS = 720
# Per read. A window wide enough to exceed this is reported as reaching the cap
# rather than silently compared in part.
ROW_CAP = 5000

EVENTS_SQL = """
SELECT id::text AS id, source, kind, symbol, ts
FROM events
WHERE ts > now() - make_interval(hours => $1)
ORDER BY ts DESC
LIMIT $2
"""

SIGNALS_SQL = """
SELECT id::text AS id, event_ids
FROM signals
WHERE created_at > now() - make_interval(hours => $1)
ORDER BY created_at DESC
LIMIT $2
"""

OPPORTUNITIES_SQL = """
SELECT id::text AS id, symbol, timeframe, dir,
       extract(epoch FROM snapshot_ts)::float8 AS snapshot_ts_s,
       links->>'evidence_digest' AS evidence_digest
FROM opportunities
WHERE snapshot_ts > now() - make_interval(hours => $1)
ORDER BY snapshot_ts DESC
LIMIT $2
"""

ENVELOPES_SQL = """
SELECT envelope_id, approval_id, candidate_id,
       extract(epoch FROM created_at)::float8 AS created_at_s,
       extract(epoch FROM consumed_at)::float8 AS consumed_at_s
FROM control_envelopes
WHERE created_at > now() - make_interval(hours => $1)
ORDER BY created_at DESC
LIMIT $2
"""

ORDERS_SQL = """
SELECT id::text AS id, decision_id::text AS decision_id, status, dry_run,
       extract(epoch FROM created_at)::float8 AS created_at_s,
       request, response
FROM exec_orders
WHERE created_at > now() - make_interval(hours => $1)
ORDER BY created_at DESC
LIMIT $2
"""

# One row per opportunity with the horizons already recorded for it, so a
# missing verdict is visible without a second query per call.
OUTCOMES_SQL = """
SELECT o.id::text AS id, o.symbol,
       extract(epoch FROM o.snapshot_ts)::float8 AS opened_at_s,
       coalesce(
         json_agg(json_build_object('horizon_minutes', x.horizon_minutes, 'status', x.status))
           FILTER (WHERE x.id IS NOT NULL),
         '[]'
       ) AS outcomes
FROM opportunities o
LEFT JOIN opportunity_outcomes x ON x.opportunity_id = o.id
WHERE o.snapshot_ts > now() - make_interval(hours => $1)
  AND o.dir IN ('LONG', 'SHORT')
GROUP BY o.id
ORDER BY o.snapshot_ts DESC
LIMIT $2
"""


def _rows(records) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


async def collect(conn, hours: int, cap: int = ROW_CAP) -> dict[str, list[dict[str, Any]]]:
    """Every record the five views compare, each read bounded and recorded."""
    events = _rows(await heavy_query.fetch(conn, "reconciliation:events", EVENTS_SQL, hours, cap))
    for row in events:
        row["ts"] = row["ts"].isoformat() if row.get("ts") is not None else None

    signals = _rows(await heavy_query.fetch(conn, "reconciliation:signals", SIGNALS_SQL, hours, cap))
    for row in signals:
        row["event_ids"] = [str(value) for value in (row.get("event_ids") or [])]

    opportunities = _rows(await heavy_query.fetch(
        conn, "reconciliation:opportunities", OPPORTUNITIES_SQL, hours, cap))

    envelopes = _rows(await heavy_query.fetch(conn, "reconciliation:approvals", ENVELOPES_SQL, hours, cap))

    orders = _rows(await heavy_query.fetch(conn, "reconciliation:orders", ORDERS_SQL, hours, cap))
    for row in orders:
        row["request"] = as_json(row.get("request")) or {}
        row["response"] = as_json(row.get("response")) or {}

    outcomes = _rows(await heavy_query.fetch(conn, "reconciliation:outcomes", OUTCOMES_SQL, hours, cap))
    for row in outcomes:
        row["outcomes"] = as_json(row.get("outcomes")) or []

    return {"events": events, "signals": signals, "opportunities": opportunities,
            "envelopes": envelopes, "orders": orders, "outcome_rows": outcomes}
