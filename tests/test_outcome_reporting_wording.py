"""The reconciliation, metric and export text the Cockpit prints verbatim avoids retired wording.

The reconciliation panel shows each view's comparison, summary and note, every finding's detail, the
metric notes and the export note exactly as state-api sends them. That puts them under the rule
``test_ui_wording.py`` applies to the rest of the backend text the Cockpit shows, and the rule is
imported from there rather than copied, so it has one source.

Every finding kind and every abstention is produced here, so a new message cannot slip past by being
a branch the test never reached.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ui_wording import RETIRED  # noqa: E402

from tradesync_core import audit_export, regime_fit, thesis_adherence  # noqa: E402
from tradesync_core import reconciliation_views as views  # noqa: E402
from tradesync_core.regime_weights import config_digest  # noqa: E402

NOW = 10_000_000.0
WINDOW = "2026-09-15T12:00:00+00:00 to 2026-09-16T12:00:00+00:00 (24h)"


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)


def offences(value):
    return [text for text in strings(value) if RETIRED.search(text)]


def test_every_reconciliation_finding_and_summary_avoids_retired_wording():
    reading = views.combine([
        views.orphaned_events([{"id": "e1"}], [{"id": "s1", "event_ids": ["older"]}], window=WINDOW),
        views.duplicate_candidates([
            {"id": "o1", "symbol": "BTC-PERP", "timeframe": "1m", "dir": "LONG", "snapshot_ts_s": NOW, "evidence_digest": "d"},
            {"id": "o2", "symbol": "BTC-PERP", "timeframe": "1m", "dir": "LONG", "snapshot_ts_s": NOW + 1, "evidence_digest": "d"},
            {"id": "o3", "symbol": "ETH-PERP", "timeframe": "1m", "dir": "LONG", "snapshot_ts_s": NOW, "evidence_digest": "x"},
            {"id": "o4", "symbol": "ETH-PERP", "timeframe": "1m", "dir": "LONG", "snapshot_ts_s": NOW + 5, "evidence_digest": "y"},
        ], window=WINDOW),
        views.stale_approvals([{"envelope_id": "a", "created_at_s": NOW - 9 * 3600}, {"envelope_id": "b", "created_at_s": None}],
                              NOW, window=WINDOW),
        views.partial_orders([{"id": "o", "status": "placed", "created_at_s": NOW - 900, "dry_run": True,
                               "request": {"size_usd": 100.0}, "response": {"filled_usd": 50.0}}], NOW, window=WINDOW),
        views.missing_outcomes([{"id": "m", "opened_at_s": NOW - 300 * 60, "outcomes": [{"horizon_minutes": 60, "status": "pending"}]},
                                {"id": "n", "opened_at_s": None}], NOW, (15, 60, 240), window=WINDOW),
        views.partial_orders([], NOW, window=WINDOW),
    ])
    kinds = {finding["kind"] for view in reading["views"] for finding in view["findings"]}
    assert kinds == {"orphaned_event", "duplicate_evidence_digest", "repeated_call", "stale_approval", "approval_without_a_time",
                     "order_not_terminal", "partial_fill", "missing_outcome", "outcome_still_pending", "opportunity_without_a_time"}
    assert offences(reading) == []
    assert offences(views.combine([views.orphaned_events([{"id": "e1"}], [{"id": "s", "event_ids": ["e1"]}], window=WINDOW)])) == []


def test_every_adherence_verdict_avoids_retired_wording():
    plan = {"side": "long", "stop": 98.5, "target": 103.0, "expiry": 4600.0, "rules": {"max_depth_bps": 5.0},
            "slippage": {"entry": {"mid": 100.0, "fill_price": 100.02, "half_spread_bps": 1.0}}}
    results = [
        thesis_adherence.score(plan, {"side": "long", "status": "closed", "exit": {"rule": rule, "fill_price": price, "at": at}})
        for rule, price, at in (("operator_close", 98.2, 5000.0), ("stop", 98.1, 2000.0), ("target", 102.0, 2000.0),
                                ("target", 103.1, 2000.0), ("time_expiry", 99.0, 4700.0), ("manual_override", 101.0, 2000.0))
    ]
    results += [thesis_adherence.score(plan, {"side": "long", "status": "open"}), thesis_adherence.score({}, {}),
                thesis_adherence.score({**plan, "rules": {}, "stop": None, "target": None, "expiry": None},
                                       {"side": "long", "status": "closed", "exit": {"rule": "stop", "fill_price": 99.0, "at": 1.0}})]
    assert offences(results) == [] and offences(thesis_adherence.summarise(results)) == []


def test_every_regime_fit_verdict_avoids_retired_wording():
    declared = {"rulebook_id": "r", "version": "1",
                "regime_expectation": {"schema": "regime_expectation_v1", "LONG": ["rising"]}}
    silent = {"rulebook_id": "r", "version": "2"}
    book = {"config": declared, "config_digest": config_digest(declared)}
    quiet = {"config": silent, "config_digest": config_digest(silent)}
    call = {"direction": "LONG", "entry_regime": "rising", "rulebook_digest": book["config_digest"]}
    results = [
        regime_fit.judge(call, book),
        regime_fit.judge({**call, "entry_regime": "falling"}, book),
        regime_fit.judge({**call, "entry_regime": "unknown"}, book),
        regime_fit.judge({**call, "direction": "SHORT"}, book),
        regime_fit.judge({**call, "rulebook_digest": quiet["config_digest"]}, quiet),
        regime_fit.judge({**call, "rulebook_digest": "other"}, book),
        regime_fit.judge(call, {"config": {**declared, "version": "9"}, "config_digest": book["config_digest"]}),
        regime_fit.judge(call, None),
    ]
    assert {result["verdict"] for result in results} == {"fit", "misfit", *regime_fit.ABSTENTIONS}
    assert offences(results) == [] and offences(regime_fit.summarise(results)) == []


def test_the_audit_export_text_avoids_retired_wording():
    built = audit_export.build({}, window_days=7.0, window_from="a", window_to="b", generated_at="c")
    assert offences({key: built[key] for key in ("bounds", "note", "verification")}) == []
