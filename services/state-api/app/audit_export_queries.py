"""The bounded reads behind the audit export.

One query per section, each naming its columns explicitly rather than selecting
everything: a column added to one of these tables later cannot then appear in an
export by merely existing. ``audit_export`` narrows the result to its declared
columns again and scrubs the free-form payloads, so the guarantee does not rest
on this file alone.

Times come back as ISO strings rather than datetimes, so the export's digest is
over exactly the text an auditor reads, and a CSV cell says the same thing as
its JSON counterpart.
"""

from __future__ import annotations

from typing import Any

from app import audit_export_paper_queries as paper_queries
from app import heavy_query
from app.json_util import as_json

DECISIONS_SQL = """
SELECT id::text AS id, created_at, opportunity_id::text AS opportunity_id, venue, requested, risk
FROM decisions
WHERE created_at > now() - make_interval(days => $1)
ORDER BY created_at DESC
LIMIT $2
"""

APPROVALS_SQL = """
SELECT envelope_id, approval_id, approval_decision_id, approval_digest, approved_at,
       candidate_id, candidate_hash, created_at, consumed_at, consumed_by
FROM control_envelopes
WHERE created_at > now() - make_interval(days => $1)
ORDER BY created_at DESC
LIMIT $2
"""

ORDERS_SQL = """
SELECT id::text AS id, created_at, decision_id::text AS decision_id, venue, status, dry_run, txid,
       request, response
FROM exec_orders
WHERE created_at > now() - make_interval(days => $1)
ORDER BY created_at DESC
LIMIT $2
"""

# The opportunity's stored evidence digest travels with its outcome, so a row in
# the export can be checked against the call it measures.
OUTCOMES_SQL = """
SELECT x.opportunity_id::text AS opportunity_id, x.symbol, x.direction, x.horizon_minutes, x.status,
       x.entry_price, x.exit_price, x.forward_return_pct, x.signed_return_pct,
       x.max_favourable_pct, x.max_adverse_pct, x.candles_used, x.reason,
       x.opened_at, x.measured_at,
       o.links->>'evidence_digest' AS evidence_digest
FROM opportunity_outcomes x
JOIN opportunities o ON o.id = x.opportunity_id
WHERE x.opened_at > now() - make_interval(days => $1)
ORDER BY x.opened_at DESC
LIMIT $2
"""

SECTION_SQL = {
    "decisions": ("audit:decisions", DECISIONS_SQL, ("requested", "risk")),
    "approvals": ("audit:approvals", APPROVALS_SQL, ()),
    "orders": ("audit:orders", ORDERS_SQL, ("request", "response")),
    "outcomes": ("audit:outcomes", OUTCOMES_SQL, ()),
}

# Read one row past the cap, so the export can tell "exactly the cap" from
# "more than the cap" and report truncation honestly.
PROBE = 1


def _jsonable(value: Any) -> Any:
    from datetime import datetime

    return value.isoformat() if isinstance(value, datetime) else value


async def fetch_section(conn, name: str, days: int, cap: int) -> list[dict[str, Any]]:
    """One section's rows over the window, bounded and recorded."""
    if name in paper_queries.PAPER_SECTION_SQL:
        return await paper_queries.fetch_section(conn, name, days, cap, PROBE)
    if name not in SECTION_SQL:
        raise KeyError(name)
    read_name, sql, json_columns = SECTION_SQL[name]
    records = await heavy_query.fetch(conn, read_name, sql, days, cap + PROBE)
    rows = []
    for record in records:
        row = {key: _jsonable(value) for key, value in dict(record).items()}
        for column in json_columns:
            row[column] = as_json(row.get(column))
        rows.append(row)
    return rows


async def collect(conn, days: int, cap: int) -> dict[str, list[dict[str, Any]]]:
    """Every section of the export over one window: the stored records, then the paper activity."""
    return {name: await fetch_section(conn, name, days, cap) for name in (*SECTION_SQL, *paper_queries.PAPER_SECTION_SQL)}
