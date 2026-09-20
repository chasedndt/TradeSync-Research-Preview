"""Session A's script for ``tools/qa_paper_risk_sql.py``: every statement and check it runs, in order.

Moved out of ``tools/qa_paper_risk_sql.py`` unchanged. The runner drives two psql
connections and watches the entry lock; this module only builds the text session A
executes: a throwaway schema, 023, 026 and 031 UP, 031 DOWN, 031 UP again, the seed,
ledger, limit and kill-switch checks, and state-api's own statements imported and
prepared as they are, ending with the entry lock held and rolled back.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

from app.paper_account_store import CLOSE_STATE_SQL, INSERT_ENTRY_SQL, POSITION_ENTRIES_SQL, STATES_AT_SQL, UPDATE_BALANCES_SQL  # noqa: E402
from app.paper_reconciliation_store import CLOSE_STATES_SQL, GAP_PAIRS_SQL, LAST_SEEN_SQL, LATEST_STATES_SQL, UPSERT_GAP_SQL  # noqa: E402
from ops.migrate import up_sql  # noqa: E402

ENTRY_LOCK = 230914
MIGRATIONS = ROOT / "ops" / "migrations"
P1, P2 = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"


def migration(name: str) -> tuple[str, str]:
    text = (MIGRATIONS / name).read_text(encoding="utf-8-sig")
    return up_sql(text), text.split("-- DOWN", 1)[1].strip()


def check(condition: str, failure: str) -> str:
    message = failure.replace("'", "''")
    return f"DO $$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'QA FAIL: {message}'; END IF; END $$;"


def refused(statement: str, sqlstate: str) -> str:
    return f"SELECT pg_temp.qa_refused($q${statement}$q$, '{sqlstate}');"


HELPERS = """CREATE FUNCTION pg_temp.qa_refused(statement text, expected text) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
  BEGIN
    EXECUTE statement;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = expected THEN RETURN; END IF;
    RAISE;
  END;
  RAISE EXCEPTION 'QA FAIL: expected SQLSTATE % from %', expected, statement;
END $f$;
CREATE FUNCTION pg_temp.qa_assert(ok boolean, message text) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
  IF ok IS NOT TRUE THEN RAISE EXCEPTION 'QA FAIL: %', message; END IF;
END $f$;"""


def seeds() -> list[str]:
    positions = (
        "INSERT INTO managed_paper_positions (id, opportunity_id, symbol, created_at, entry_evidence, evidence_sha256, initial_plan, position_state) VALUES "
        f"('{P1}', '11111111-1111-4111-8111-111111111111', 'BTC-PERP', now() - interval '1200 seconds', '{{}}', 'qa', '{{\"status\":\"open\"}}', '{{\"status\":\"open\",\"observations\":2,\"last_quote_time\":2}}'), "
        f"('{P2}', '22222222-2222-4222-8222-222222222222', 'ETH-PERP', now() - interval '1200 seconds', '{{}}', 'qa', '{{\"status\":\"open\"}}', '{{\"status\":\"closed\",\"observations\":1,\"last_quote_time\":1,\"exit_time\":1}}');")
    events = (
        "INSERT INTO managed_paper_events (id, position_id, kind, payload, created_at) VALUES "
        f"(gen_random_uuid(), '{P1}', 'opened', '{{\"status\":\"open\",\"observations\":0,\"last_quote_time\":0}}', now() - interval '1200 seconds'), "
        f"(gen_random_uuid(), '{P1}', 'observed', '{{\"position\":{{\"status\":\"open\",\"observations\":1,\"last_quote_time\":1}}}}', now() - interval '1195 seconds'), "
        f"(gen_random_uuid(), '{P1}', 'observed', '{{\"position\":{{\"status\":\"open\",\"observations\":2,\"last_quote_time\":2}}}}', now() - interval '1100 seconds'), "
        f"(gen_random_uuid(), '{P2}', 'opened', '{{\"status\":\"open\",\"observations\":0,\"last_quote_time\":0}}', now() - interval '1200 seconds'), "
        f"(gen_random_uuid(), '{P2}', 'closed', '{{\"position\":{{\"status\":\"closed\",\"observations\":1,\"last_quote_time\":1,\"exit_time\":1}}}}', now() - interval '1190 seconds');")
    return ["INSERT INTO opportunities VALUES ('11111111-1111-4111-8111-111111111111'), ('22222222-2222-4222-8222-222222222222');", positions, events]


def ledger_checks() -> list[str]:
    realised = ("INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, gross_pnl_usdc, fees_usdc, funding_usdc, "
                "balance_after_usdc) VALUES (gen_random_uuid(), 'realised', ")
    adjust = ("INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, funding_usdc, balance_after_usdc) "
              "VALUES (gen_random_uuid(), 'funding_adjustment', ")
    return [
        "INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc) VALUES (gen_random_uuid(), 'capital', clock_timestamp(), 10000, 10000);",
        "INSERT INTO paper_account (starting_capital_usdc, cash_usdc, last_sequence, peak_equity_usdc, peak_equity_at) SELECT 10000, 10000, max(sequence), 10000, clock_timestamp() FROM paper_account_ledger;",
        refused("UPDATE paper_account_ledger SET amount_usdc = 1", "P0001"),
        refused("DELETE FROM paper_account_ledger", "P0001"),
        refused("TRUNCATE paper_account_ledger", "P0001"),
        refused("INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc) VALUES (gen_random_uuid(), 'capital', clock_timestamp(), 1, 1)", "23505"),
        refused("INSERT INTO paper_account (starting_capital_usdc, cash_usdc, last_sequence, peak_equity_usdc, peak_equity_at) VALUES (1, 1, 1, 1, now())", "23505"),
        *seeds(),
        realised + f"'{P2}', clock_timestamp(), -1.5, -1, 0.4, 0.1, 9998.5);",
        refused(realised + f"'{P1}', clock_timestamp(), 5, 1, 0, 0, 1)", "23514"),
        refused(realised + f"'{P2}', clock_timestamp(), -1.5, -1, 0.4, 0.1, 9997)", "23505"),
        refused("INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc) VALUES (gen_random_uuid(), 'realised', clock_timestamp(), 1, 1)", "23514"),
        adjust + f"'{P2}', clock_timestamp(), -0.25, 0.25, 9998.25);",
        adjust + f"'{P2}', clock_timestamp(), 0.1, -0.1, 9998.35);",
        refused(adjust + f"'{P2}', clock_timestamp(), 0.25, 0.25, 1)", "23514"),
        refused(adjust + f"'{P2}', clock_timestamp(), 0, 0, 1)", "23514"),
        refused("INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, gross_pnl_usdc, funding_usdc, balance_after_usdc) "
                f"VALUES (gen_random_uuid(), 'funding_adjustment', '{P2}', clock_timestamp(), 0.75, 1, 0.25, 1)", "23514"),
        refused("INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, funding_usdc, balance_after_usdc) "
                "VALUES (gen_random_uuid(), 'funding_adjustment', clock_timestamp(), -0.25, 0.25, 1)", "23514"),
        "\\echo PASS ledger: append-only against UPDATE, DELETE and TRUNCATE; one capital row; one realised entry per position with amount "
        "equal to gross less fees and funding; any number of funding adjustments per position, each tied to it, with only funding and an amount of minus it",
    ]


def limit_and_kill_checks() -> list[str]:
    return [
        refused("UPDATE paper_risk_limits SET max_symbol_exposure_fraction = 0.5", "23514"),
        refused("UPDATE paper_risk_limits SET max_drawdown_fraction = 1", "23514"),
        refused("UPDATE paper_risk_limits SET max_concurrent_positions = 0", "23514"),
        refused("INSERT INTO paper_risk_limits (singleton) VALUES (false)", "23514"),
        refused("INSERT INTO paper_risk_limit_events (id, operator, reason, previous, updated) VALUES (gen_random_uuid(), 'qa', 'shrt', '{}', '{}')", "23514"),
        "INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES (gen_random_uuid(), 'kill', 'qa', 'Acceptance kill switch row');",
        refused("INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES (gen_random_uuid(), 'close', 'qa', 'Close without a position')", "23514"),
        refused("UPDATE paper_kill_switch_events SET reason = 'Rewritten afterwards'", "P0001"),
        "\\echo PASS limits and kill switch: ordering and ranges enforced, singletons, audit rows append-only with meaningful reasons",
    ]


def prepared_reads() -> list[str]:
    return [
        f"PREPARE qa_upsert_gap(uuid, uuid, text, timestamptz, timestamptz) AS {UPSERT_GAP_SQL};",
        f"EXECUTE qa_upsert_gap(gen_random_uuid(), '{P1}', 'BTC-PERP', now() - interval '1195 seconds', NULL);",
        f"EXECUTE qa_upsert_gap(gen_random_uuid(), '{P1}', 'BTC-PERP', now() - interval '1195 seconds', now() - interval '1100 seconds');",
        f"EXECUTE qa_upsert_gap(gen_random_uuid(), '{P1}', 'BTC-PERP', now() - interval '1195 seconds', NULL);",
        check("(SELECT count(*) FROM paper_observation_gaps) = 1 AND (SELECT ended_at FROM paper_observation_gaps) = now() - interval '1100 seconds'",
              "gap upsert must gain its end once and never lose it"),
        refused(f"INSERT INTO paper_observation_gaps (id, position_id, symbol, started_at, ended_at) VALUES (gen_random_uuid(), '{P1}', 'BTC-PERP', now(), now() - interval '1 second')", "23514"),
        f"PREPARE qa_gap_pairs(float8) AS {GAP_PAIRS_SQL};",
        "CREATE TEMP TABLE qa_gaps AS EXECUTE qa_gap_pairs(45);",
        check("(SELECT count(*) FROM qa_gaps) = 1 AND (SELECT round((ended_s - started_s)::numeric) FROM qa_gaps) = 95", "gap pairs"),
        f"PREPARE qa_last_seen AS {LAST_SEEN_SQL};",
        "CREATE TEMP TABLE qa_seen AS EXECUTE qa_last_seen;",
        check("(SELECT count(*) FROM qa_seen) = 1 AND (SELECT symbol = 'BTC-PERP' AND last_at = now() - interval '1100 seconds' FROM qa_seen)", "last observation of open positions"),
        f"PREPARE qa_latest AS {LATEST_STATES_SQL};",
        "CREATE TEMP TABLE qa_latest_rows AS EXECUTE qa_latest;",
        check("(SELECT count(*) FROM qa_latest_rows) = 5", "latest lifecycle candidates"),
        f"PREPARE qa_closes AS {CLOSE_STATES_SQL};",
        "CREATE TEMP TABLE qa_close_rows AS EXECUTE qa_closes;",
        check("(SELECT count(*) FROM qa_close_rows) = 1", "closed-event states"),
        f"PREPARE qa_states_at(timestamptz, float8) AS {STATES_AT_SQL};",
        "CREATE TEMP TABLE qa_states AS EXECUTE qa_states_at(now() - interval '1150 seconds', extract(epoch FROM now() - interval '1150 seconds'));",
        check("(SELECT count(*) FROM qa_states) = 2", "states at a day boundary"),
        "\\echo PASS state-api reads as prepared: gap upsert, one 95-second gap, last observation, lifecycle candidates, closed-event states, boundary states",
    ]


def prepared_booking() -> list[str]:
    return [
        "SELECT last_sequence AS qa_last FROM paper_account \\gset",
        f"PREPARE qa_position_entries AS {POSITION_ENTRIES_SQL};",
        f"PREPARE qa_close_state AS {CLOSE_STATE_SQL};",
        f"PREPARE qa_insert_entry AS {INSERT_ENTRY_SQL};",
        f"PREPARE qa_update_balances AS {UPDATE_BALANCES_SQL};",
        f"CREATE TEMP TABLE qa_close_state_row AS EXECUTE qa_close_state('{P2}');",
        check("(SELECT count(*) FROM qa_close_state_row) = 1", "a position's closed-event state"),
        # An INSERT ... RETURNING cannot feed CREATE TABLE AS; psql captures its one row instead (qa_sequence).
        f"EXECUTE qa_insert_entry(gen_random_uuid(), 'funding_adjustment', '{P2}', 1789.5, -0.3, 0, 0, 0.3, 0, 9999.7, "
        "'{\"funding_source\": \"settled\"}') \\gset qa_",
        "EXECUTE qa_update_balances(9999.7, -0.3, 0, 0, 0.3, 0, 0, :qa_sequence, :qa_last);",
        "EXECUTE qa_update_balances(9999.4, -0.3, 0, 0, 0.3, 0, 0, :qa_sequence, :qa_last);",
        "SELECT pg_temp.qa_assert((SELECT cash_usdc = 9999.7 AND funding_usdc = 0.3 AND realised_pnl_usdc = -0.3 AND closed_positions = 0 "
        "AND last_sequence = :qa_sequence FROM paper_account), 'a booked adjustment moves cash, funding and realised by exactly its amount, and only once');",
        f"CREATE TEMP TABLE qa_booked AS EXECUTE qa_position_entries('{P2}');",
        check("(SELECT count(*) FROM qa_booked) = 4 AND (SELECT sum(funding_usdc) FROM qa_booked) = 0.55", "a position's booked funding"),
        "\\echo PASS state-api booking as prepared: a funding adjustment appended and the balances moved by exactly it, a repeat against the old sequence refused, the position's booked funding read back",
    ]


def session_a_script(schema: str, application: str, hold_s: float) -> str:
    up23, _ = migration("023_managed_paper_positions.sql")
    up26, _ = migration("026_paper_control.sql")
    up31, down31 = migration("031_paper_risk_engine.sql")
    return "\n".join([
        f"SET application_name = '{application}';",
        "BEGIN;",
        f"CREATE SCHEMA {schema};",
        f"SET LOCAL search_path TO {schema};",
        "CREATE TABLE opportunities (id uuid PRIMARY KEY);",
        up23 + ";", up26 + ";", up31 + ";",
        "\\echo PASS 031 UP applied after 023 and 026 in an isolated schema",
        down31,
        check("to_regclass('paper_account') IS NULL AND to_regclass('paper_risk_limits') IS NULL AND NOT EXISTS (SELECT 1 FROM information_schema.columns "
              "WHERE table_schema = current_schema() AND table_name = 'managed_paper_control_events' AND column_name = 'operator')",
              "031 DOWN left objects behind"),
        "\\echo PASS 031 DOWN removed its tables, function and the operator column",
        up31 + ";",
        "\\echo PASS 031 UP applied again",
        HELPERS,
        check("(SELECT count(*) FROM paper_risk_limits) = 1 AND (SELECT daily_loss_limit_usdc = 200 AND max_drawdown_fraction = 0.06 AND max_concurrent_positions = 3 FROM paper_risk_limits)",
              "limit seeds"),
        check("(SELECT active FROM paper_kill_switch) IS FALSE AND (SELECT entries_paused FROM managed_paper_control) IS TRUE", "kill and pause seeds"),
        "INSERT INTO managed_paper_control_events (id, entries_paused, reason) VALUES (gen_random_uuid(), true, 'Earlier route without an operator');",
        check("(SELECT operator FROM managed_paper_control_events) = 'unrecorded'", "operator default on pause audit rows"),
        "\\echo PASS seeds: conservative limits, kill switch disengaged, entries paused, pause audit operator defaults to unrecorded",
        *ledger_checks(),
        *limit_and_kill_checks(),
        *prepared_reads(),
        *prepared_booking(),
        f"SELECT pg_advisory_xact_lock({ENTRY_LOCK});",
        f"SELECT pg_sleep({hold_s});",
        "SELECT 'A_RELEASE_AT ' || extract(epoch FROM clock_timestamp());",
        "ROLLBACK;",
        "\\echo PASS session A rolled back",
    ])
