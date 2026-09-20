"""A bounded, checkable export of decisions, approvals, orders, outcomes and paper activity.

The paper sections (rehearsals, managed paper positions and their lifecycle
events) are declared in ``audit_export_paper``: paper mode stores no decision
or order, so without them the export of the paper default is empty.

An audit export exists so somebody outside this process can check the record
without being given the database. Three things decide whether it is worth
anything:

**It must be checkable against the rows it came from.** Every section carries
the digests those rows already store -- an approval's digest and the hash of
the candidate it was granted for, an opportunity's evidence digest -- so a row
in the export can be matched to the artefact it describes rather than merely
believed. The export also digests its own content, so the file can be checked
for having been edited after it was produced.

**It must be bounded, and say so.** An unbounded export of a table that grows
forever is a denial of service with a friendly name. Each section is capped at
``MAX_ROWS_PER_SECTION`` and the window at ``MAX_WINDOW_DAYS``; a section that
hit its cap says ``truncated`` with the cap that applied, so a short export is
never mistaken for a short history.

**It must not leak a secret.** Two defences, because one is not enough. The
columns of every section are named here explicitly, so a column added to a
table in future cannot appear in an export by simply existing. Then every
nested payload -- an order's request and response, a decision's risk envelope --
is scrubbed by key, because those are free-form JSON that nothing constrains.
A redacted field is replaced by a marker and counted, so the export states that
something was removed rather than quietly dropping it.

Nothing here reads a database, a clock or a network. It is given rows and
returns a document.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .audit_export_paper import COMPUTED_DIGEST_COLUMNS, PAPER_SECTIONS, PAPER_STORED_DIGESTS, SECTION_NOTES

SCHEMA_VERSION = "audit_export_v1"

# The bounds, stated in the export itself.
MAX_ROWS_PER_SECTION = 5000
MAX_WINDOW_DAYS = 31

REDACTED = "[redacted]"

# Key names whose value never belongs in an export. Deliberately broad: a field
# wrongly redacted costs an auditor one question, a field wrongly exported
# cannot be taken back. "digest" and "hash" are absent on purpose -- they are
# the fingerprints the export exists to carry.
SECRET_KEY = re.compile(
    r"secret|token|password|passphrase|mnemonic|seed|private|credential|cookie|bearer|signature"
    r"|api[_-]?key|authorization|\bkey\b",
    re.IGNORECASE,
)

# Every column that may leave this system, per section. A column not named here
# is not exported, whatever the query returned.
RECORD_SECTIONS: dict[str, tuple[str, ...]] = {
    "decisions": ("id", "created_at", "opportunity_id", "venue", "requested", "risk"),
    "approvals": ("envelope_id", "approval_id", "approval_decision_id", "approval_digest", "approved_at",
                  "candidate_id", "candidate_hash", "created_at", "consumed_at", "consumed_by"),
    "orders": ("id", "created_at", "decision_id", "venue", "status", "dry_run", "txid", "request", "response"),
    "outcomes": ("opportunity_id", "symbol", "direction", "horizon_minutes", "status", "entry_price", "exit_price",
                 "forward_return_pct", "signed_return_pct", "max_favourable_pct", "max_adverse_pct",
                 "candles_used", "reason", "opened_at", "measured_at", "evidence_digest"),
}
SECTIONS: dict[str, tuple[str, ...]] = {**RECORD_SECTIONS, **PAPER_SECTIONS}

# The columns that are themselves a stored fingerprint, listed so the export can
# say which of its fields are checkable against something else.
STORED_DIGEST_COLUMNS = ("approval_digest", "candidate_hash", "evidence_digest", *PAPER_STORED_DIGESTS)


class AuditExportError(ValueError):
    """Raised for a request that cannot be served, never for an empty result."""


def canonical_json(value: Any) -> str:
    """Key-ordered, separator-stable JSON, so a digest does not depend on key order."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def digest_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def scrub(value: Any, counter: list[int] | None = None) -> Any:
    """Replace every value under a secret-looking key, however deeply nested.

    Counting the replacements matters: an export that silently dropped a field
    would be indistinguishable from one where the field was never there.
    """
    counter = counter if counter is not None else []
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY.search(str(key)):
                out[str(key)] = REDACTED
                counter.append(1)
            else:
                out[str(key)] = scrub(item, counter)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(item, counter) for item in value]
    return value


def _row(section: str, row: Mapping[str, Any], counter: list[int]) -> dict[str, Any]:
    """One row cut down to the section's declared columns, and scrubbed."""
    return {column: scrub(row.get(column), counter) for column in SECTIONS[section]}


def section(name: str, rows: Iterable[Mapping[str, Any]], *, cap: int = MAX_ROWS_PER_SECTION) -> dict[str, Any]:
    """One section of the export: its rows, its bound, and a digest of its content."""
    if name not in SECTIONS:
        raise AuditExportError(f"{name!r} is not an exportable section; expected one of {sorted(SECTIONS)}")
    if cap < 1:
        raise AuditExportError("a section cap must be at least one row")
    counter: list[int] = []
    collected = list(rows)
    kept = [_row(name, row, counter) for row in collected[:cap]]
    return {
        "name": name,
        "columns": list(SECTIONS[name]),
        "rows": kept,
        "row_count": len(kept),
        "rows_available_in_window": len(collected),
        "truncated": len(collected) > cap,
        "row_cap": cap,
        "redacted_fields": len(counter),
        "stored_digests": [c for c in STORED_DIGEST_COLUMNS if c in SECTIONS[name]],
        "computed_digests": [c for c in COMPUTED_DIGEST_COLUMNS if c in SECTIONS[name]],
        "content_digest": digest_of(kept),
        "note": SECTION_NOTES.get(name),
    }


def to_csv(name: str, rows: Sequence[Mapping[str, Any]]) -> str:
    """One section as CSV, with the section's declared columns as a stable header.

    A nested value is written as canonical JSON in its cell, so a row survives
    the round trip into a spreadsheet without losing its payload. The header is
    written even when there are no rows: an empty section is a result.
    """
    if name not in SECTIONS:
        raise AuditExportError(f"{name!r} is not an exportable section; expected one of {sorted(SECTIONS)}")
    columns = SECTIONS[name]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([
            "" if row.get(column) is None
            else canonical_json(row[column]) if isinstance(row.get(column), (Mapping, list, tuple))
            else row[column]
            for column in columns
        ])
    return buffer.getvalue()


def check_window(days: float) -> float:
    """The requested window, or a refusal naming the bound."""
    if not isinstance(days, (int, float)) or isinstance(days, bool) or days <= 0:
        raise AuditExportError("an export window must be a positive number of days")
    if days > MAX_WINDOW_DAYS:
        raise AuditExportError(
            f"an export window is bounded at {MAX_WINDOW_DAYS} days; {days:g} was requested")
    return float(days)


def build(sections: Mapping[str, Sequence[Mapping[str, Any]]], *, window_days: float, window_from: str,
          window_to: str, generated_at: str, cap: int = MAX_ROWS_PER_SECTION) -> dict[str, Any]:
    """The whole export: every section, the window it covers, and its own digest.

    ``content_digest`` is over the sections only, so it is the same for the same
    rows whenever it was produced: a digest that included ``generated_at`` would
    differ on every call and could check nothing.
    """
    check_window(window_days)
    built = {name: section(name, sections.get(name) or [], cap=cap) for name in SECTIONS}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "window": {"days": window_days, "from": window_from, "to": window_to},
        "bounds": {
            "max_rows_per_section": cap,
            "max_window_days": MAX_WINDOW_DAYS,
            "note": (
                f"Each section returns at most {cap} rows and the window is bounded at {MAX_WINDOW_DAYS} days. "
                "A section that reached its cap says truncated, so a short export is not mistaken for a short history."
            ),
        },
        "sections": built,
        "row_count": sum(part["row_count"] for part in built.values()),
        "truncated": any(part["truncated"] for part in built.values()),
        "redacted_fields": sum(part["redacted_fields"] for part in built.values()),
        "content_digest": digest_of({name: part["content_digest"] for name, part in built.items()}),
        "verification": (
            "Each row carries the digests already stored beside it, so it can be checked against the artefact it "
            "describes. content_digest is over the sections only and not over generated_at, so the same rows "
            "produce the same digest whenever the export was taken."
        ),
        "note": (
            "Read-only. Fields under a secret-looking key are replaced by a marker and counted; no token, key or "
            "credential is exported. No order has ever been placed by this system, so the orders section is "
            "expected to be empty. Paper activity is in the paper sections: rehearsals, managed paper positions "
            "and their lifecycle transitions."
        ),
    }
