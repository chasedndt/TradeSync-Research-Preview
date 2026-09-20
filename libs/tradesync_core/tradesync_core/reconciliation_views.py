"""Five read-only comparisons of this system's records against each other.

``reconciliation`` compares recorded decisions against recorded orders. These
are the other five the roadmap names, built the same way and with the same
discipline: each one reads two records, reports where they disagree, guesses
nothing about which side is right, and can change nothing.

Every view answers two questions that a bare count cannot:

- **what was compared**, so a finding is traceable to the two records behind it;
- **over what window**, so a reader can tell a real absence from the edge of
  the query. The existing module already learned this the hard way: an order
  whose decision predates the window is not an orphan, it is a query bound, and
  reporting it as a finding manufactures a divergence out of how far back
  somebody looked. Every view here keeps that distinction.

A clean view is a result and is reported as one. So is an empty one, but they
are *different* results: ``considered`` says how many records the view actually
examined, so "nothing to reconcile" cannot be misread as "everything agrees".
That matters most for orders, because no order has ever been placed.

The views
---------

``orphaned_events``
    Market events no signal referenced. An event nothing consumed is either an
    ingestion that produced nothing or a scorer that missed it.
``duplicate_candidates``
    Two opportunities from one evidence digest, which the digest exists to
    prevent, and repeated calls on one market within a short window.
``stale_approvals``
    Approvals recorded and never consumed past their validity. An approval
    nobody acted on is not an approval that was refused.
``partial_orders``
    Orders that never reached a terminal state, and orders whose fill is
    smaller than the request.
``missing_outcomes``
    Opportunities whose horizon has fully elapsed with no verdict recorded, and
    verdicts still pending after their window closed.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .reconciliation_view_model import Finding, View, _seconds, _text

SCHEMA_VERSION = "reconciliation_views_v1"

# An approval's default validity, matching the Gate approval model's four hours.
DEFAULT_APPROVAL_VALIDITY_S = 4 * 3600
# How long an order may sit in a non-terminal state before it is worth reporting.
DEFAULT_ORDER_SETTLE_S = 300
# Two calls on one market this close together are worth a look, even when their
# evidence differs. Below the opportunity TTL, so it is not merely "both live".
DEFAULT_REPEAT_WINDOW_S = 60
# The states an order can stop in. Anything else is still in flight.
TERMINAL_ORDER_STATES = frozenset({"filled", "cancelled", "failed", "reconciled", "rejected"})
# Money agrees to the cent; below that is rounding, not a partial fill.
SIZE_TOLERANCE_USD = 0.01


def orphaned_events(events: Iterable[Mapping[str, Any]], signals: Iterable[Mapping[str, Any]],
                    *, window: str) -> View:
    """Events in the window that no signal referenced.

    ``signals`` carry ``event_ids``. A referenced event that is not in the
    window is reported as outside it, not as a missing event.
    """
    rows = [dict(event) for event in events]
    known = {_text(event.get("id")) for event in rows}
    referenced: set[str] = set()
    for signal in signals:
        for event_id in signal.get("event_ids") or []:
            text = _text(event_id)
            if text:
                referenced.add(text)

    findings = [
        Finding("orphaned_event", _text(event.get("id")),
                "no signal in this window referenced this event; either nothing consumed it or the signal that "
                "did was not recorded",
                {"source": event.get("source"), "kind": event.get("kind"), "symbol": event.get("symbol"),
                 "ts": event.get("ts")})
        for event in rows
        if _text(event.get("id")) not in referenced
    ]
    return View("orphaned_events", "events against the event_ids every signal recorded", window,
                len(rows), tuple(findings), tuple(sorted(referenced - known)))


def duplicate_candidates(opportunities: Iterable[Mapping[str, Any]], *, window: str,
                         repeat_window_s: float = DEFAULT_REPEAT_WINDOW_S) -> View:
    """Opportunities that look like the same call recorded twice.

    Two kinds, deliberately not merged. A shared evidence digest is a certainty:
    the digest binds a verdict to the exact evidence that produced it precisely
    so a replay is idempotent, and two opportunities carrying one digest mean
    that guarantee did not hold. A repeat within a few seconds on one market and
    side is a candidate worth a look, not proof of anything.
    """
    rows = [dict(row) for row in opportunities]
    findings: list[Finding] = []

    by_digest: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        digest = _text(row.get("evidence_digest"))
        if digest:
            by_digest.setdefault(digest, []).append(row)
    for digest, group in sorted(by_digest.items()):
        if len(group) > 1:
            ids = sorted(str(row.get("id")) for row in group)
            findings.append(Finding(
                "duplicate_evidence_digest", ids[0],
                f"{len(group)} opportunities share one evidence digest; the digest exists to make a replay "
                "idempotent rather than create a second opportunity",
                {"evidence_digest": digest, "opportunity_ids": ids}))

    by_call: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("symbol")), str(row.get("timeframe")), str(row.get("dir")))
        by_call.setdefault(key, []).append(row)
    for key, group in sorted(by_call.items()):
        ordered = sorted(group, key=lambda row: _seconds(row.get("snapshot_ts_s")) or 0.0)
        for earlier, later in zip(ordered, ordered[1:]):
            first, second = _seconds(earlier.get("snapshot_ts_s")), _seconds(later.get("snapshot_ts_s"))
            if first is None or second is None or second - first > repeat_window_s:
                continue
            if _text(earlier.get("evidence_digest")) and _text(earlier.get("evidence_digest")) == _text(later.get("evidence_digest")):
                continue  # already reported above, as the stronger finding
            findings.append(Finding(
                "repeated_call", str(later.get("id")),
                f"a second {key[2]} call on {key[0]} {key[1]} {second - first:.0f}s after the previous one, "
                f"inside the {repeat_window_s:.0f}s repeat window",
                {"previous_opportunity_id": str(earlier.get("id")), "seconds_apart": round(second - first, 3)}))

    return View("duplicate_candidates",
                "opportunities against each other by evidence digest, and by market, timeframe and side",
                window, len(rows), tuple(findings))


def stale_approvals(envelopes: Iterable[Mapping[str, Any]], now_s: float, *, window: str,
                    validity_s: float = DEFAULT_APPROVAL_VALIDITY_S) -> View:
    """Approvals recorded and never consumed, past their validity.

    An unconsumed approval is a recorded permission nobody acted on, which is a
    different thing from one that was refused, and a different thing again from
    one that was used. This does not guess between them and it consumes nothing.
    """
    rows = [dict(row) for row in envelopes]
    findings = []
    for row in rows:
        if row.get("consumed_at_s") is not None:
            continue
        created = _seconds(row.get("created_at_s"))
        if created is None:
            findings.append(Finding("approval_without_a_time", _text(row.get("envelope_id")),
                                    "this approval records no creation time, so its age cannot be established"))
            continue
        age = now_s - created
        if age > validity_s:
            findings.append(Finding(
                "stale_approval", _text(row.get("envelope_id")),
                f"recorded {age / 3600:.2f}h ago and never consumed, past the {validity_s / 3600:.2f}h validity",
                {"approval_id": _text(row.get("approval_id")), "age_s": round(age, 3),
                 "candidate_id": _text(row.get("candidate_id"))}))
    return View("stale_approvals", "control envelopes against their own consumption record", window,
                len(rows), tuple(findings))


def partial_orders(orders: Iterable[Mapping[str, Any]], now_s: float, *, window: str,
                   settle_s: float = DEFAULT_ORDER_SETTLE_S) -> View:
    """Orders that never settled, and orders filled for less than they asked.

    No order has ever been placed by this system, so this view is expected to
    consider nothing. ``considered`` says so rather than letting an empty table
    read as a clean reconciliation.
    """
    rows = [dict(row) for row in orders]
    findings = []
    for row in rows:
        order_id = _text(row.get("id"))
        status = str(row.get("status") or "").strip().lower()
        created = _seconds(row.get("created_at_s"))
        if status not in TERMINAL_ORDER_STATES and created is not None and now_s - created > settle_s:
            findings.append(Finding(
                "order_not_terminal", order_id,
                f"still {status!r} {now_s - created:.0f}s after it was recorded, past the {settle_s:.0f}s "
                "settle window",
                {"decision_id": _text(row.get("decision_id")), "status": status,
                 "age_s": round(now_s - created, 3), "dry_run": row.get("dry_run")}))
        requested = _seconds((row.get("request") or {}).get("size_usd"))
        filled = _seconds((row.get("response") or {}).get("filled_usd"))
        if requested is not None and filled is not None and requested - filled > SIZE_TOLERANCE_USD:
            findings.append(Finding(
                "partial_fill", order_id,
                f"filled {filled:.2f} USD of a {requested:.2f} USD request; the rest is unaccounted for",
                {"decision_id": _text(row.get("decision_id")), "requested_usd": requested, "filled_usd": filled}))
    return View("partial_orders", "recorded orders against their own status and fill", window,
                len(rows), tuple(findings))


def missing_outcomes(opportunities: Iterable[Mapping[str, Any]], now_s: float, horizons: Sequence[int],
                     *, window: str) -> View:
    """Opportunities whose horizon has closed with no verdict, or a verdict still pending.

    Each row carries its ``outcomes``: the horizons already recorded and their
    status. A horizon that has not yet elapsed is not missing, it is simply not
    due, and it is never reported.
    """
    rows = [dict(row) for row in opportunities]
    findings = []
    for row in rows:
        opened = _seconds(row.get("opened_at_s"))
        if opened is None:
            findings.append(Finding("opportunity_without_a_time", _text(row.get("id")),
                                    "this opportunity records no time, so no horizon can be said to have closed"))
            continue
        recorded = {int(outcome["horizon_minutes"]): str(outcome.get("status") or "")
                    for outcome in row.get("outcomes") or []
                    if isinstance(outcome, Mapping) and outcome.get("horizon_minutes") is not None}
        for horizon in horizons:
            closed_at = opened + horizon * 60
            if now_s < closed_at:
                continue  # not due; reporting it would be a finding about the clock
            status = recorded.get(int(horizon))
            if status is None:
                findings.append(Finding(
                    "missing_outcome", _text(row.get("id")),
                    f"the {horizon}-minute horizon closed {(now_s - closed_at) / 60:.0f} minutes ago with no "
                    "verdict recorded",
                    {"symbol": row.get("symbol"), "horizon_minutes": horizon,
                     "closed_at_s": closed_at}))
            elif status == "pending":
                findings.append(Finding(
                    "outcome_still_pending", _text(row.get("id")),
                    f"the {horizon}-minute verdict is still pending {(now_s - closed_at) / 60:.0f} minutes after "
                    "its window closed",
                    {"symbol": row.get("symbol"), "horizon_minutes": horizon, "status": status}))
    return View("missing_outcomes", "opportunities against the outcome rows recorded for each horizon", window,
                len(rows), tuple(findings))


def combine(views: Iterable[View]) -> dict[str, Any]:
    """Every view together, with one honest overall verdict."""
    rendered = [view.to_dict() for view in views]
    findings = sum(len(view["findings"]) for view in rendered)
    considered = sum(view["considered"] for view in rendered)
    return {
        "schema_version": SCHEMA_VERSION,
        "views": rendered,
        "findings": findings,
        "records_compared": considered,
        "clean": findings == 0,
        "summary": (f"{len(rendered)} views compared {considered} record(s) with no divergence"
                    if findings == 0 else
                    f"{findings} finding(s) across {len(rendered)} views over {considered} record(s)"),
        "note": (
            "Read-only comparisons of this system's own records. Nothing here can place, amend, cancel or "
            "consume anything, and a view that considered no record says so rather than reporting a clean "
            "reconciliation."
        ),
    }
