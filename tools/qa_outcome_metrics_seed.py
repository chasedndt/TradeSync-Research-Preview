"""What the outcome metrics acceptance seeds into its throwaway database.

Moved out of ``qa_outcome_metrics_sql.py`` unchanged, so that script holds the checks and this one the
rows they are checked against: a divergence for every reconciliation view and a row each view must
not report, calls under three rulebooks, the adherence worked example, and two fields whose
secret-looking keys the export must scrub. Imported by that script, which puts the library on the path.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from tradesync_core.regime_weights import config_digest

ROOT = Path(__file__).resolve().parents[1]

SECRETS = ("qa-api-key-must-never-be-exported", "qa-signature-must-never-be-exported")
RULEBOOK = json.loads((ROOT / "config" / "regime" / "regime-rulebook-v1.json").read_text(encoding="utf-8"))
EXPECTING = {**RULEBOOK, "version": "1.0.1-qa-expectation",
             "regime_expectation": {"schema": "regime_expectation_v1", "LONG": ["rising"], "SHORT": ["falling"]}}
LATER = {**RULEBOOK, "version": "1.0.2-qa-later",
         "regime_expectation": {"schema": "regime_expectation_v1", "LONG": ["falling"], "SHORT": ["rising"]}}
# The worked example from tradesync_core.thesis_adherence: three checks pass, two fail.
PLAN = {"side": "long", "stop": 98.5, "target": 103.0, "expiry": 4600.0, "rules": {"max_depth_bps": 5.0},
        "slippage": {"entry": {"mid": 100.0, "fill_price": 100.02, "half_spread_bps": 1.0}}}
CLOSED = {"side": "long", "status": "closed", "exit": {"rule": "operator_close", "fill_price": 98.2, "at": 5000.0}}
OPEN = {"side": "long", "status": "open"}


async def insert_rulebook(conn, config) -> str:
    digest = config_digest(config)
    await conn.execute(
        "INSERT INTO regime_rulebooks (rulebook_id, version, schema_version, status, environment, horizon, config_digest, "
        "config, created_by) VALUES ($1, $2, $3, 'draft', 'paper', $4, $5, $6::jsonb, 'qa')",
        config["rulebook_id"], config["version"], config["schema_version"], config["horizon"], digest, json.dumps(config))
    return digest


async def seed(conn) -> tuple[dict[str, uuid.UUID], str, str]:
    ids = {name: uuid.uuid4() for name in ("e1", "e2", "o1", "o2", "o3", "o4", "d1", "p1", "p2")}
    plain, expecting = await insert_rulebook(conn, RULEBOOK), await insert_rulebook(conn, EXPECTING)
    for name, minutes in (("e1", 6), ("e2", 5)):
        await conn.execute(
            "INSERT INTO events (id, ts, source, kind, symbol, timeframe, payload, hash) VALUES "
            "($1, now() - make_interval(mins => $2), 'hyperliquid', 'trade', 'BTC-PERP', '1m', '{}'::jsonb, $3)",
            ids[name], minutes, f"qa-{ids[name]}")
    await conn.execute(
        "INSERT INTO signals (agent, symbol, timeframe, kind, confidence, dir, features, event_ids, created_at) VALUES "
        "('qa', 'BTC-PERP', '1m', 'qa', 0.5, 'LONG', '{}'::jsonb, $1::uuid[], now() - interval '5 minutes')", [ids["e1"]])
    shared = "a" * 64
    for name, symbol, side, age_s, evidence, rulebook in (
            ("o1", "BTC-PERP", "LONG", 12000.0, shared, expecting), ("o2", "BTC-PERP", "LONG", 11995.0, shared, expecting),
            ("o3", "ETH-PERP", "SHORT", 1800.0, "b" * 64, plain), ("o4", "SOL-PERP", "LONG", 600.0, "c" * 64, "f" * 64)):
        await conn.execute(
            "INSERT INTO opportunities (id, symbol, timeframe, snapshot_ts, bias, quality, confluence, dir, links) VALUES "
            "($1, $2, '1m', now() - make_interval(secs => $3), 0.3, 55, $4::jsonb, $5, $6::jsonb)",
            ids[name], symbol, age_s, json.dumps({"evidence": {"rulebook_digest": rulebook}}), side,
            json.dumps({"evidence_digest": evidence}))
    for name, symbol, regime in (("o1", "BTC-PERP", "rising"), ("o2", "BTC-PERP", "falling"), ("o3", "ETH-PERP", "falling")):
        await conn.execute(
            "INSERT INTO opportunity_entry_regimes (opportunity_id, symbol, regime, trailing_return_pct, lookback_minutes, "
            "candles_used) VALUES ($1, $2, $3, 0.1, 60, 60)", ids[name], symbol, regime)
    for horizon, status in ((15, "measured"), (60, "pending")):
        await conn.execute(
            "INSERT INTO opportunity_outcomes (opportunity_id, symbol, direction, horizon_minutes, status, opened_at) VALUES "
            "($1, 'BTC-PERP', 'LONG', $2, $3, now() - interval '200 minutes')", ids["o1"], horizon, status)
    for name, hours in (("stale", 6), ("fresh", 1)):
        await conn.execute(
            "INSERT INTO control_envelopes (envelope_id, approval_id, approval_decision_id, approval_digest, approved_at, "
            "candidate_id, candidate_hash, candidate, authority, created_at) VALUES ($1, $2, $3, $4, "
            "now() - make_interval(hours => $5), $6, $7, '{}'::jsonb, '{}'::jsonb, now() - make_interval(hours => $5))",
            f"qa-env-{name}", f"qa-approval-{name}", f"qa-decision-{name}", (name * 16)[:64], hours,
            f"qa-candidate-{name}", (name[::-1] * 16)[:64])
    await conn.execute(
        "INSERT INTO decisions (id, opportunity_id, venue, requested, risk, created_at) VALUES "
        "($1, $2, 'hyperliquid', $3::jsonb, '{}'::jsonb, now() - interval '12 minutes')", ids["d1"], ids["o1"],
        json.dumps({"symbol": "BTC-PERP", "side": "long", "size_usd": 100.0, "venue": "hyperliquid", "api_key": SECRETS[0]}))
    await conn.execute(
        "INSERT INTO exec_orders (decision_id, venue, request, response, status, dry_run, created_at) VALUES "
        "($1, 'hyperliquid', $2::jsonb, $3::jsonb, 'placed', true, now() - interval '10 minutes')", ids["d1"],
        json.dumps({"symbol": "BTC-PERP", "side": "long", "size_usd": 100.0, "venue": "hyperliquid"}),
        json.dumps({"filled_usd": 60.0, "signature": SECRETS[1]}))
    for name, opportunity, state in (("p1", "o3", CLOSED), ("p2", "o4", OPEN)):
        await conn.execute(
            "INSERT INTO managed_paper_positions (id, opportunity_id, symbol, entry_evidence, evidence_sha256, initial_plan, "
            "position_state) VALUES ($1, $2, 'ETH-PERP', '{}'::jsonb, $3, $4::jsonb, $5::jsonb)",
            ids[name], ids[opportunity], "e" * 64, json.dumps(PLAN), json.dumps(state))
    return ids, plain, expecting
