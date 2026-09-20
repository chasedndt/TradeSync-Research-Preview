"""The audit export's paper sections: rehearsals, managed paper positions and their lifecycle transitions."""

import json
import os
import sys

import pytest

from tradesync_core import audit_export
from tradesync_core import audit_export_paper as paper
from tradesync_core.managed_paper import advance, open_position
from tradesync_core.paper_kill import kill_close

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ui_wording import RETIRED  # noqa: E402

WINDOW = dict(window_days=7.0, window_from="2026-09-09T12:00:00+00:00", window_to="2026-09-16T12:00:00+00:00",
              generated_at="2026-09-16T12:00:00+00:00")


def book(at, bid, ask):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': 100.0}], 'asks': [{'price': ask, 'size': 100.0}]}


def lifecycle():
    opened = open_position('long', 'scalp', 1000, 1, book(1000, 99.99, 100.01), 1000)
    observed = advance(opened, book(1010, 100.5, 100.51), 1010)
    closed = advance(observed, book(1020, 100.8, 100.81), 1020, manual_close=True)
    return opened, observed, closed


def stored_position(state, **over):
    row = {"id": "p1", "opportunity_id": "o1", "symbol": "BTC-PERP", "created_at": "2026-09-16T10:00:00+00:00",
           "updated_at": "2026-09-16T10:05:00+00:00", "evidence_sha256": "a" * 64, "evidence_digest": "b" * 64,
           "position_state": json.dumps(state), "events": 3, "observation_events": 1,
           "first_event_at": "2026-09-16T10:00:00+00:00", "last_event_at": "2026-09-16T10:00:20+00:00"}
    row.update(over)
    return row


def stored_event(kind, payload, **over):
    row = {"id": f"e-{kind}", "position_id": "p1", "symbol": "BTC-PERP", "created_at": "2026-09-16T10:00:20+00:00",
           "kind": kind, "payload": json.dumps(payload)}
    row.update(over)
    return row


def test_every_paper_section_is_part_of_the_export_with_declared_columns():
    assert set(paper.PAPER_SECTIONS) == {"paper_rehearsals", "paper_positions", "paper_position_events"}
    assert set(paper.PAPER_SECTIONS) <= set(audit_export.SECTIONS)
    assert set(audit_export.RECORD_SECTIONS) == {"decisions", "approvals", "orders", "outcomes"}
    assert "evidence_sha256" in audit_export.STORED_DIGEST_COLUMNS


def test_a_position_row_states_its_lifecycle_figures_as_stored():
    _, _, closed = lifecycle()
    row = paper.position_row(stored_position(closed))
    assert row["status"] == "closed" and row["side"] == "long" and row["style"] == "scalp"
    assert row["lifecycle_version"] == closed["version"]
    assert (row["entry_price"], row["quantity"], row["stop"], row["target"]) == (
        closed["entry_price"], closed["quantity"], closed["stop"], closed["target"])
    assert (row["exit_time"], row["exit_reason"], row["exit_price"]) == (1020, "operator_close", closed["exit_price"])
    assert row["net_usdc"] == closed["net_estimate_usdc"] and row["fees_usdc"] == closed["fees_usdc"]
    assert row["observations"] == 2 and row["observation_events"] == 1 and row["events"] == 3
    assert row["evidence_sha256"] == "a" * 64 and row["evidence_digest"] == "b" * 64
    assert set(row) == set(paper.PAPER_SECTIONS["paper_positions"])


def test_an_open_position_has_no_exit_in_its_row():
    _, observed, _ = lifecycle()
    row = paper.position_row(stored_position(observed))
    assert row["status"] == "open" and row["exit_time"] is None and row["exit_reason"] is None and row["exit_price"] is None


def test_each_transition_names_its_fill_and_fingerprints_its_stored_payload():
    opened, observed, closed = lifecycle()
    open_payload = opened
    close_payload = {"position": closed, "book": book(1020, 100.8, 100.81), "funding_rows_added": 0}
    funding_payload = {"position": closed, "book": None, "funding_rows_added": 1}

    entry = paper.event_row(stored_event("opened", open_payload))
    assert (entry["fill_price"], entry["fill_quantity"]) == (opened["entry_price"], opened["quantity"])
    assert entry["fee_usdc"] == opened["fees"]["entry_usdc"] and entry["fill_cost_usdc"] == opened["slippage"]["entry"]["cost_usdc"]
    assert entry["funding_rows_added"] is None and entry["exit_reason"] is None

    exit_ = paper.event_row(stored_event("closed", close_payload))
    assert exit_["fill_price"] == closed["exit_price"] and exit_["fee_usdc"] == closed["fees"]["exit_usdc"]
    assert exit_["fill_cost_usdc"] == closed["slippage"]["exit"]["cost_usdc"] and exit_["exit_reason"] == "operator_close"

    settled = paper.event_row(stored_event("funding_settled", funding_payload))
    assert settled["fill_price"] is None and settled["funding_rows_added"] == 1

    for row, payload in ((entry, open_payload), (exit_, close_payload), (settled, funding_payload)):
        assert row["payload_sha256"] == audit_export.digest_of(json.loads(json.dumps(payload)))
        assert set(row) == set(paper.PAPER_SECTIONS["paper_position_events"])
    assert entry["payload_sha256"] != exit_["payload_sha256"]


def test_a_kill_switch_close_carries_who_closed_it_and_why():
    _, observed, _ = lifecycle()
    killed = kill_close(observed, book(1030, 100.2, 100.21), 1030, operator="chase", reason="drawdown check")
    payload = {"position": killed, "book": book(1030, 100.2, 100.21), "funding_rows_added": 0,
               "kill_switch": {"operator": "chase", "reason": "drawdown check"}}
    row = paper.event_row(stored_event("closed", payload))
    assert row["exit_reason"] == "kill_switch" and row["kill_switch"] == {"operator": "chase", "reason": "drawdown check"}


def test_the_built_export_carries_the_paper_sections_with_their_digests_and_notes():
    opened, _, closed = lifecycle()
    rehearsal = {"id": "r1", "created_at": "2026-09-16T09:00:00+00:00", "opportunity_id": "o1", "symbol": "BTC-PERP",
                 "direction": "LONG", "size_usd": 250.0, "status": "rehearsed",
                 "plan": {"action": "Paper market order", "api_key": "sk-must-not-leave"},
                 "risk_verdict": {"allowed": True, "reason_code": "OK"}, "fill": {"fill_price": 100.02},
                 "market": {"spread_bps": 2.0}, "evidence_digest": "c" * 64}
    sections = {
        "paper_rehearsals": [rehearsal],
        "paper_positions": [paper.position_row(stored_position(closed))],
        "paper_position_events": [paper.event_row(stored_event("opened", opened))],
    }
    built = audit_export.build(sections, **WINDOW)
    rehearsals, positions, events = (built["sections"][name] for name in paper.PAPER_SECTIONS)
    assert rehearsals["row_count"] == 1 and rehearsals["redacted_fields"] == 1
    assert rehearsals["rows"][0]["plan"]["api_key"] == audit_export.REDACTED
    assert "sk-must-not-leave" not in json.dumps(built)
    assert positions["stored_digests"] == ["evidence_digest", "evidence_sha256"]
    assert rehearsals["stored_digests"] == ["evidence_digest"] and events["stored_digests"] == []
    assert events["computed_digests"] == ["payload_sha256"] and positions["computed_digests"] == []
    assert all(built["sections"][name]["note"] for name in paper.PAPER_SECTIONS)
    assert built["sections"]["orders"]["note"] is None
    assert audit_export.build(sections, **WINDOW)["content_digest"] == built["content_digest"]


@pytest.mark.parametrize("section", sorted(paper.PAPER_SECTIONS))
def test_each_paper_section_writes_a_csv_with_its_declared_header(section):
    text = audit_export.to_csv(section, [])
    assert text.strip() == ",".join(paper.PAPER_SECTIONS[section])


def test_the_paper_notes_the_page_prints_avoid_retired_wording():
    texts = [*paper.SECTION_NOTES.values(), audit_export.build({}, **WINDOW)["note"]]
    assert [text for text in texts if RETIRED.search(text)] == []
