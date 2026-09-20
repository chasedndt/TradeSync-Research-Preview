#!/usr/bin/env python
"""Replay the real windows where each exit rule fires, in an isolated schema, and emit their fixtures.

Each window is given as ``symbol:style:side:entry_epoch:opportunity:rule``, exactly as
``tools/qa_paper_rule_windows.py`` found it. The replay is the real one: the entry is the
closed minute's open moved by the book TradeSync recorded at or before it, every closed
1-minute candle since is evaluated, and funding settles from Hyperliquid's published rates
at the oracle prices recorded in ``market_open_interest``.

Everything written lands in one throwaway schema inside one transaction that is rolled
back; public tables are only read, and the public portfolio and entry pause are checked
untouched afterwards. The report carries the checks and one fixture per rule, which the
host writes under ``tests/fixtures/paper_rules`` as a regression test.

    python tools/run_in_state_api.py tools/qa_paper_rule_fixtures.py \
        --with tools/qa_paper_rule_windows.py -- SYMBOL:style:side:epoch:opportunity:rule ...
"""

import asyncio
import json
import math
import os
import sys
import time
import uuid

import asyncpg
import httpx

from app import paper_funding_store
from qa_paper_rule_windows import BAR_S, HISTORY_CANDLES, NOTIONAL, book_at, candles, latest_candles, note, recorded_books, utc
from tradesync_core import paper_depth as depth
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance_on_candle, atr, open_position_on_candle, settle_funding
from tradesync_core.paper_lifecycle_rules import COMMON, RULES
from tradesync_core.paper_opening import order_sides

MIGRATIONS = ("023_managed_paper_positions.sql", "026_paper_control.sql", "032_managed_paper_funding.sql")
MARKET = os.environ.get("MARKET_DATA_URL", "http://market-data:8005")
CANDLE_KEYS = ("time", "open", "high", "low", "close")


def near(a, b):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


class Checks:
    def __init__(self):
        self.results = {}

    def __call__(self, name, passed, detail=None):
        self.results[name] = {"passed": bool(passed), **({"detail": detail} if detail is not None else {})}
        note(f"[{'PASS' if passed else 'FAIL'}] {name}" + ("" if passed or detail is None else f": {detail}"))
        return bool(passed)

    @property
    def passed(self):
        return bool(self.results) and all(result["passed"] for result in self.results.values())


def sections(name):
    up, down = QA_FILES[f"ops/migrations/{name}"].split("-- DOWN")  # noqa: F821 - provided by the launcher
    return up.replace("-- UP", "", 1), down


def parse(text):
    symbol, style, side, entry_time, opportunity, rule = text.split(":")
    return {"symbol": symbol, "style": style, "side": side, "entry_time": int(float(entry_time)),
            "opportunity": uuid.UUID(opportunity), "rule": rule}


async def gather(conn, client, spec, now):
    """The real inputs of one window: its minutes, the candles its ATR is measured on, and the recorded books."""
    rules = RULES[spec["style"]]
    entry_time = spec["entry_time"]
    end = min(now, entry_time + rules.max_hold_s + 2 * BAR_S)
    bars = [bar for bar in await candles(client, spec["symbol"], "1m", entry_time, end)
            if bar["time"] >= entry_time and bar["time"] + BAR_S <= now]
    history = await latest_candles(client, spec["symbol"], rules.atr_interval, HISTORY_CANDLES[rules.atr_interval])
    atr_bars = [c for c in history if c["time"] + rules.atr_seconds <= entry_time][-(rules.atr_period + 1):]
    books = await recorded_books(conn, spec["symbol"], entry_time, end)
    return bars, atr_bars, books


def replay(spec, bars, atr_bars, books, now):
    rules = RULES[spec["style"]]
    volatility = atr(atr_bars, rules.atr_seconds, spec["entry_time"], rules.atr_period)
    entry_book = book_at(books, spec["entry_time"])
    floor = funding.planning_bps_hour({}, COMMON.planning_funding_floor_bps_hour)
    state = open_position_on_candle(spec["side"], spec["style"], NOTIONAL, volatility, bars[0], entry_book[1],
                                    cost_source=entry_book[2], planning_funding=floor)
    used = []
    for bar in bars:
        if state["status"] != "open":
            break
        cost = book_at(books, bar["time"])
        state = advance_on_candle(state, bar, BAR_S, cost[1], now, cost_source=cost[2])
        used.append(bar)
    return state, volatility, used


def verify(checks, spec, state, bars, books, rows):
    label = f"{spec['rule']} {spec['symbol']} {spec['style']}"
    record = state["exit"]
    sign = 1 if state["side"] == "long" else -1
    quantity, bound = state["quantity"], state["rules"]["max_depth_bps"]
    if not checks(f"{label}: the position closed on a real candle", state["status"] == "closed"):
        return
    fired_at = record["trigger_observation"].get("open_time")
    bar = next((b for b in bars if b["time"] == fired_at), None)
    cost = book_at(books, fired_at) if fired_at is not None else None
    if spec["rule"] == "target":
        checks(f"{label}: the target fired at its declared level",
               record["rule"] == "target" and near(record["level"], state["target"]),
               {"rule": record["rule"], "level": record["level"], "target": state["target"]})
    elif spec["rule"] == "time_expiry":
        checks(f"{label}: the time expiry fired at or after the declared expiry, at the candle's close",
               record["rule"] == "time_expiry" and record["at"] >= state["expiry"] and record["path"] == "close",
               {"at": record["at"], "expiry": state["expiry"], "path": record["path"]})
    else:
        adverse = sign * (record["fill_price"] - record["level"]) < 0
        checks(f"{label}: the gap at the open fired at the open, past the level, and filled worse than it",
               record["path"] == "open" and record["gap_fill"] is True and bar is not None
               and near(record["trigger_price"], bar["open"]) and adverse,
               {"open": None if bar is None else bar["open"], "level": record["level"], "fill": record["fill_price"],
                "rule": record["rule"]})
    checks(f"{label}: the exit fill is the trigger price moved by the book recorded at or before that candle",
           cost is not None and near(record["fill_price"], depth.priced(
               record["trigger_price"], depth.walk(cost[1], order_sides(state["side"])[1], quantity=quantity, max_depth_bps=bound))))
    fees = state["fees"]
    checks(f"{label}: each fee is the taker rate on its own fill",
           near(fees["entry_usdc"], fees["rate"] * state["entry_price"] * quantity)
           and near(fees["exit_usdc"], fees["rate"] * state["exit_price"] * quantity))
    hours = [int(row["settled_at"]) for row in rows]
    checks(f"{label}: a funding row or a missing marker for every hour crossed",
           sorted(hours + state["funding"]["missing_hours"]) == funding.settlement_hours(state["entry_time"], state["exit_time"]))
    checks(f"{label}: each payment is side x quantity x price x rate",
           all(near(row["payment_usdc"], sign * row["quantity"] * row["price"] * row["funding_rate"]) for row in rows))
    checks(f"{label}: net is gross minus fees minus settled funding",
           near(state["net_estimate_usdc"], state["gross_pnl_usdc"] - state["fees_usdc"] - state["funding_usdc"]))


def fixture(spec, state, volatility, bars, atr_bars, books, rows, recorded_at):
    record = state["exit"]
    used = [entry for entry in books if entry[0] <= bars[-1]["time"] + BAR_S]
    rules = RULES[spec["style"]]
    return {
        "rule": spec["rule"], "symbol": spec["symbol"], "style": spec["style"], "side": spec["side"],
        "notional_usdc": NOTIONAL, "lifecycle_version": state["version"], "recorded_at": recorded_at,
        "source": {
            "candles": f"Hyperliquid 1-minute candles, read through market-data /candles/hyperliquid/{spec['symbol']}",
            "atr_candles": f"Hyperliquid {rules.atr_interval} candles, the closed ones before the entry",
            "books": "public.market_depth_snapshots, n_sig_figs = 3, first five levels a 250 USDC walk can reach",
            "opportunity": str(spec["opportunity"]),
            "note": "Real venue data replayed under managed-paper-lifecycle-v3; no parameter was tuned on it.",
        },
        "window": {"entry_time": spec["entry_time"], "entry_at": utc(spec["entry_time"]),
                   "exit_time": state["exit_time"], "exit_at": utc(state["exit_time"]),
                   "last_candle_at": utc(bars[-1]["time"]), "candles": len(bars)},
        "atr": volatility,
        "atr_candles": [{key: bar[key] for key in CANDLE_KEYS} for bar in atr_bars],
        "candles": [{key: bar[key] for key in CANDLE_KEYS} for bar in bars],
        "books": [{"recorded_at": at, "observed_at": source["observed_at"], "bids": book["bids"], "asks": book["asks"]}
                  for at, book, source in used],
        "funding_rows": rows,
        "expected": {
            "rule": record["rule"], "path": record["path"], "gap_fill": record["gap_fill"], "level": record["level"],
            "trigger_price": record["trigger_price"], "fill_price": record["fill_price"], "at": record["at"],
            "parts": record["parts"], "entry_price": state["entry_price"], "quantity": state["quantity"],
            "stop": state["stop"], "target": state["target"], "expiry": state["expiry"], "candles": state["candles"],
            "gross_pnl_usdc": state["gross_pnl_usdc"], "fees_usdc": state["fees_usdc"],
            "funding_usdc": state["funding_usdc"], "net_estimate_usdc": state["net_estimate_usdc"],
        },
    }


async def one(conn, client, spec, checks):
    now = time.time()
    bars, atr_bars, books = await gather(conn, client, spec, now)
    label = f"{spec['rule']} {spec['symbol']} {spec['style']}"
    if not checks(f"{label}: real candles and a recorded book cover the window",
                  bool(bars) and bars[0]["time"] == spec["entry_time"] and book_at(books, spec["entry_time"]) is not None,
                  {"candles": len(bars), "books": len(books)}):
        return None
    state, volatility, used = replay(spec, bars, atr_bars, books, now)
    identity = uuid.uuid4()
    await conn.execute("INSERT INTO opportunities SELECT * FROM public.opportunities WHERE id = $1 ON CONFLICT DO NOTHING",
                       spec["opportunity"])
    await conn.execute(
        "INSERT INTO managed_paper_positions (id, opportunity_id, symbol, entry_evidence, evidence_sha256, initial_plan, "
        "position_state) VALUES ($1, $2, $3, '{}'::jsonb, $4, $5::jsonb, $5::jsonb)",
        identity, spec["opportunity"], spec["symbol"], f"rule window {spec['rule']}", json.dumps(state))
    hours = funding.settlement_hours(state["entry_time"], state["exit_time"])
    rates, received = await paper_funding_store.published(MARKET, spec["symbol"], hours) if hours else ({}, None)
    await paper_funding_store.store(conn, identity, spec["symbol"], state, rates, received, state["exit_time"])
    rows = await paper_funding_store.rows(conn, identity)
    state = settle_funding(state, rows)
    await conn.execute("UPDATE managed_paper_positions SET position_state = $2::jsonb WHERE id = $1", identity, json.dumps(state))
    stored = json.loads(await conn.fetchval("SELECT position_state FROM managed_paper_positions WHERE id = $1", identity))
    checks(f"{label}: the stored state reads back from JSONB unchanged", stored == json.loads(json.dumps(state)))
    verify(checks, spec, state, used, books, rows)
    return fixture(spec, state, volatility, used, atr_bars, books, rows, utc(now))


async def main(specs):
    checks = Checks()
    report = {"classification": ("Real Hyperliquid candles and the books TradeSync recorded, replayed in a throwaway schema "
                                 "inside one rolled-back transaction. Engineering acceptance, not strategy performance."),
              "started_at": utc(time.time()), "windows": [f"{s['symbol']} {s['style']} {s['side']} {utc(s['entry_time'])}" for s in specs]}
    conn = await asyncpg.connect(os.environ["PG_DSN"], statement_cache_size=0)
    reader = await asyncpg.connect(os.environ["PG_DSN"], statement_cache_size=0)
    schema = "qa_paper_rules_" + uuid.uuid4().hex[:12]
    outer = conn.transaction()
    await outer.start()
    try:
        await reader.execute("BEGIN READ ONLY")
        public_positions = await reader.fetchval("SELECT count(*) FROM managed_paper_positions")
        await conn.execute(f"CREATE SCHEMA {schema}")
        await conn.execute(f"SET LOCAL search_path TO {schema}, public")
        await conn.execute(f"CREATE TABLE {schema}.opportunities (LIKE public.opportunities INCLUDING ALL)")
        for name in MIGRATIONS:
            await conn.execute(sections(name)[0])
        checks("isolated tables shadow the public ones",
               await conn.fetchval("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                                   "WHERE c.oid = to_regclass('managed_paper_positions')") == schema)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), trust_env=False) as client:
            report["fixtures"] = {spec["rule"]: await one(conn, client, spec, checks) for spec in specs}
    except Exception as exc:
        checks("acceptance ran to completion", False, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        await outer.rollback()
        await reader.execute("ROLLBACK")
        report["schema_after_rollback"] = await conn.fetchval("SELECT count(*) FROM pg_namespace WHERE nspname = $1", schema)
        report["public_positions_before_after"] = [public_positions,
                                                   await conn.fetchval("SELECT count(*) FROM public.managed_paper_positions")]
        report["public_entries_paused_after"] = await conn.fetchval("SELECT entries_paused FROM public.managed_paper_control")
        checks("rolled back: schema gone, public portfolio and pause untouched",
               report["schema_after_rollback"] == 0
               and report["public_positions_before_after"][0] == report["public_positions_before_after"][1]
               and report["public_entries_paused_after"] is True)
        await conn.close()
        await reader.close()
        report["finished_at"] = utc(time.time())
        report["checks"] = checks.results
        report["result"] = "PASS" if checks.passed else "FAIL"
        print(json.dumps(report, default=str, indent=1))
    return 0 if checks.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main([parse(text) for text in sys.argv[1:]])))
