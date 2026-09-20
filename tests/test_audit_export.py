"""The audit export: bounded, checkable, and carrying no secret.

The secret test is the one that must never be allowed to go soft: it asserts the
absence of the secret *values* from the rendered JSON and CSV, not merely that
some field was renamed.
"""

import csv
import io
import json

import pytest

from tradesync_core import audit_export


WINDOW = {"window_days": 7.0, "window_from": "2026-09-09T00:00:00+00:00",
          "window_to": "2026-09-16T00:00:00+00:00", "generated_at": "2026-09-16T12:00:00+00:00"}

SECRETS = ("hl-secret-value", "sk-live-01234567890", "correct horse battery staple",
           "0xdeadbeefprivatekey", "Bearer abcdef123456")


def order_row():
    """An order whose free-form payloads carry every kind of secret we refuse to export."""
    return {
        "id": "o1", "created_at": "2026-09-15T10:00:00+00:00", "decision_id": "d1", "venue": "hyperliquid",
        "status": "placed", "dry_run": True, "txid": None,
        "request": {"symbol": "BTC-PERP", "side": "long", "size_usd": 100.0,
                    "api_key": "sk-live-01234567890",
                    "auth": {"token": "hl-secret-value", "Authorization": "Bearer abcdef123456"}},
        "response": {"ok": True, "private_key": "0xdeadbeefprivatekey",
                     "headers": [{"cookie": "correct horse battery staple"}]},
        # A column no section declares; it must not reach the export.
        "internal_note": "should never be exported",
    }


def test_no_secret_token_or_key_appears_anywhere_in_the_export():
    """The load-bearing assertion: the values are gone from both renderings."""
    export = audit_export.build({"orders": [order_row()]}, **WINDOW)
    rendered = json.dumps(export)
    for secret in SECRETS:
        assert secret not in rendered, secret

    as_csv = audit_export.to_csv("orders", export["sections"]["orders"]["rows"])
    for secret in SECRETS:
        assert secret not in as_csv, secret

    assert export["redacted_fields"] == 5
    assert audit_export.REDACTED in rendered


def test_secrets_are_replaced_by_a_marker_rather_than_silently_dropped():
    """A dropped field is indistinguishable from one that was never there."""
    row = audit_export.build({"orders": [order_row()]}, **WINDOW)["sections"]["orders"]["rows"][0]
    assert row["request"]["api_key"] == audit_export.REDACTED
    assert row["request"]["auth"]["token"] == audit_export.REDACTED
    assert row["request"]["auth"]["Authorization"] == audit_export.REDACTED
    assert row["response"]["private_key"] == audit_export.REDACTED
    assert row["response"]["headers"][0]["cookie"] == audit_export.REDACTED
    # The rest of the payload is untouched, so the export is still worth reading.
    assert row["request"]["symbol"] == "BTC-PERP" and row["request"]["size_usd"] == 100.0
    assert row["response"]["ok"] is True


def test_a_column_no_section_declares_cannot_reach_the_export():
    """A column added to a table in future does not export itself."""
    row = audit_export.build({"orders": [order_row()]}, **WINDOW)["sections"]["orders"]["rows"][0]
    assert "internal_note" not in row
    assert set(row) == set(audit_export.SECTIONS["orders"])


def test_the_digests_the_rows_already_store_are_carried_through():
    """They are what an export is checked against; scrubbing must not take them."""
    approval = {"envelope_id": "e1", "approval_id": "a1", "approval_decision_id": "dec1",
                "approval_digest": "d" * 64, "approved_at": "2026-09-15T09:00:00+00:00",
                "candidate_id": "c1", "candidate_hash": "h" * 64,
                "created_at": "2026-09-15T09:00:00+00:00", "consumed_at": None, "consumed_by": None}
    built = audit_export.build({"approvals": [approval]}, **WINDOW)["sections"]["approvals"]
    assert built["rows"][0]["approval_digest"] == "d" * 64
    assert built["rows"][0]["candidate_hash"] == "h" * 64
    assert built["stored_digests"] == ["approval_digest", "candidate_hash"]


def test_a_section_is_capped_and_says_so():
    rows = [{"id": f"o{i}", "status": "placed"} for i in range(12)]
    built = audit_export.section("orders", rows, cap=10)
    assert built["row_count"] == 10 and built["rows_available_in_window"] == 12
    assert built["truncated"] is True and built["row_cap"] == 10


def test_a_section_inside_its_cap_is_not_truncated():
    built = audit_export.section("orders", [{"id": "o1"}], cap=10)
    assert built["truncated"] is False and built["row_count"] == 1


def test_the_window_is_bounded_and_the_refusal_names_the_bound():
    with pytest.raises(audit_export.AuditExportError) as raised:
        audit_export.check_window(audit_export.MAX_WINDOW_DAYS + 1)
    assert str(audit_export.MAX_WINDOW_DAYS) in str(raised.value)
    for bad in (0, -1, True):
        with pytest.raises(audit_export.AuditExportError):
            audit_export.check_window(bad)
    assert audit_export.check_window(audit_export.MAX_WINDOW_DAYS) == float(audit_export.MAX_WINDOW_DAYS)


def test_an_unknown_section_is_refused_by_name():
    with pytest.raises(audit_export.AuditExportError):
        audit_export.section("wallets", [])
    with pytest.raises(audit_export.AuditExportError):
        audit_export.to_csv("wallets", [])


def test_the_content_digest_does_not_depend_on_key_order_but_does_on_the_values():
    first = audit_export.section("orders", [{"id": "o1", "status": "placed", "venue": "hyperliquid"}])
    same = audit_export.section("orders", [{"venue": "hyperliquid", "id": "o1", "status": "placed"}])
    different = audit_export.section("orders", [{"id": "o1", "status": "filled", "venue": "hyperliquid"}])
    assert first["content_digest"] == same["content_digest"]
    assert first["content_digest"] != different["content_digest"]


def test_the_export_digest_is_stable_across_the_time_it_was_taken():
    """A digest including generated_at would differ on every call and check nothing."""
    first = audit_export.build({"orders": [order_row()]}, **WINDOW)
    later = audit_export.build({"orders": [order_row()]},
                               **{**WINDOW, "generated_at": "2026-09-17T23:59:00+00:00"})
    assert first["content_digest"] == later["content_digest"]


def test_the_csv_header_is_the_declared_columns_even_with_no_rows():
    text = audit_export.to_csv("decisions", [])
    assert text.strip() == ",".join(audit_export.SECTIONS["decisions"])


def test_the_csv_encodes_nested_payloads_and_survives_a_round_trip():
    """A cell holding a comma and a quote must read back as exactly what went in.

    Asserted by parsing the CSV rather than by matching its text: a quoted cell
    doubles its inner quotes, so a substring check would be asserting the
    escaping rather than the content.
    """
    awkward = 'a comma, and a "quote"'
    rows = audit_export.section("decisions", [{
        "id": "d1", "created_at": "2026-09-15T10:00:00+00:00", "opportunity_id": "op1", "venue": "hyperliquid",
        "requested": {"symbol": "BTC-PERP", "size_usd": 100.0},
        "risk": {"note": awkward},
    }])["rows"]
    text = audit_export.to_csv("decisions", rows)

    header, row = list(csv.reader(io.StringIO(text)))
    assert header == list(audit_export.SECTIONS["decisions"])
    cells = dict(zip(header, row))
    assert cells["id"] == "d1" and cells["venue"] == "hyperliquid"
    assert json.loads(cells["requested"]) == {"symbol": "BTC-PERP", "size_usd": 100.0}
    assert json.loads(cells["risk"])["note"] == awkward


def test_the_csv_and_the_json_agree_on_the_rows():
    export = audit_export.build({"orders": [order_row(), {**order_row(), "id": "o2"}]}, **WINDOW)
    rows = export["sections"]["orders"]["rows"]
    text = audit_export.to_csv("orders", rows)
    assert len(text.strip().splitlines()) == len(rows) + 1  # a header plus a line per row


def test_every_section_is_present_even_when_nothing_was_found():
    """An empty section is a result. No order has ever been placed."""
    export = audit_export.build({}, **WINDOW)
    assert set(export["sections"]) == set(audit_export.SECTIONS)
    assert export["row_count"] == 0 and export["truncated"] is False
    assert export["sections"]["orders"]["row_count"] == 0
    assert "expected to be empty" in export["note"]


def test_the_export_states_its_bounds():
    export = audit_export.build({}, **WINDOW)
    assert export["bounds"]["max_rows_per_section"] == audit_export.MAX_ROWS_PER_SECTION
    assert export["bounds"]["max_window_days"] == audit_export.MAX_WINDOW_DAYS
    assert export["window"]["from"] == WINDOW["window_from"]
