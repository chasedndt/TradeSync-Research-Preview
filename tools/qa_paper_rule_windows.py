#!/usr/bin/env python
"""Search real Hyperliquid candles for windows where each exit rule fires under the declared rules.

Read-only. Public tables are only read (the books TradeSync recorded, and the
opportunities that give a direction), candles come from market-data's own route, and
nothing is written anywhere. Run inside the state-api container against this checkout's
code:

    python tools/run_in_state_api.py tools/qa_paper_rule_windows.py -- [hours] [entries_per_symbol]

For every tracked symbol it takes real opportunities spread across the window, enters at
the closed minute the opportunity falls in, prices that entry from the book recorded at
or before it, and advances the position on every closed 1-minute candle since, exactly as
the replay acceptance does. It reports, per exit rule, the shortest real window that fired
it — with its exact times, levels and prices — and a census of what every attempt did.

A symbol whose candles market-data cannot serve is recorded as unavailable and the search
carries on; nothing is ever replaced by a guess. The rules are
``managed-paper-lifecycle-v3`` as declared: nothing here tunes a parameter, and no result
is evidence of an edge.
"""

import asyncio
import json
import os
import sys
import time
from bisect import bisect_right
from datetime import datetime, timezone

import asyncpg
import httpx

from app import editions
from tradesync_core import paper_depth as depth
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance_on_candle, atr, open_position_on_candle
from tradesync_core.paper_lifecycle_rules import COMMON, RULES

MARKET = os.environ.get("MARKET_DATA_URL", "http://market-data:8005")
STYLES = ("scalp", "intraday", "swing")
NOTIONAL = 250.0
BAR_S = 60
PAGE_CANDLES = 500  # the route serves at most 1000 per request; smaller pages answer faster
INTERVAL_S = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
# Latest candles to ask for per ATR interval: the window plus the period the ATR needs before its oldest entry.
HISTORY_CANDLES = {"15m": 300, "1h": 120, "4h": 80}
BOOK_LEVELS = 5  # a 250 USDC walk never reaches further; keeps the search small inside the container
WANTED = ("target", "time_expiry", "gap_at_open")
ATTEMPTS = 3


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def note(message):
    print(message, file=sys.stderr, flush=True)


async def request(client, path, params):
    """One market-data read, retried briefly; the last failure is raised for the caller to record."""
    for attempt in range(ATTEMPTS):
        try:
            response = await client.get(MARKET + path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            if attempt + 1 == ATTEMPTS:
                raise
            await asyncio.sleep(2 * (attempt + 1))


async def candles(client, symbol, interval, start_s, end_s):
    """Closed candles over a window, paged so no request exceeds the route's limit."""
    step, out, cursor = INTERVAL_S[interval], {}, start_s
    while cursor < end_s:
        stop = min(end_s, cursor + PAGE_CANDLES * step)
        payload = await request(client, f"/candles/hyperliquid/{symbol}",
                                {"interval": interval, "start_ms": int(cursor * 1000), "end_ms": int(stop * 1000)})
        for bar in payload.get("candles") or []:
            out[int(bar["time"])] = bar
        cursor = stop
    return [out[key] for key in sorted(out)]


async def latest_candles(client, symbol, interval, count):
    """The most recent ``count`` candles: one request, for the average true range behind each entry."""
    payload = await request(client, f"/candles/hyperliquid/{symbol}", {"interval": interval, "limit": count})
    return payload.get("candles") or []


async def recorded_books(conn, symbol, start_s, end_s):
    """The books TradeSync recorded (3 significant figures), trimmed to the levels a paper size can reach."""
    rows = await conn.fetch(
        "SELECT observed_at, recorded_at, bids, asks FROM public.market_depth_snapshots WHERE symbol = $1 AND n_sig_figs = 3 "
        "AND recorded_at BETWEEN to_timestamp($2) AND to_timestamp($3) ORDER BY recorded_at", symbol, start_s - 3600, end_s)
    books = []
    for row in rows:
        book = {"bids": json.loads(row["bids"])[:BOOK_LEVELS], "asks": json.loads(row["asks"])[:BOOK_LEVELS]}
        if not book["bids"] or not book["asks"]:
            continue
        source = depth.snapshot(book, observed_at=row["observed_at"].timestamp(), received_at=row["recorded_at"].timestamp(),
                                source="market_depth_snapshots", precision="aggregated_3_sig_figs")
        books.append((row["recorded_at"].timestamp(), book, source))
    return books


def book_at(books, at):
    index = bisect_right([b[0] for b in books], at) - 1
    return books[index] if index >= 0 else None


def fired(state):
    """Which of the rules this search looks for a window fired, and the exit record."""
    if state["status"] != "closed":
        return [], None
    record = state["exit"]
    rules = [record["rule"]]
    if record.get("path") == "open" and record.get("gap_fill"):
        rules.append("gap_at_open")
    return rules, record


def replay(side, style, entry_bar, bars, books, atr_bars, now):
    """One position entered at a closed minute and advanced on every closed minute since."""
    rules = RULES[style]
    entry_book = book_at(books, entry_bar["time"])
    if entry_book is None:
        return {"refused": "no book recorded at or before the entry minute"}
    volatility = atr(atr_bars, rules.atr_seconds, entry_bar["time"], rules.atr_period)
    floor = funding.planning_bps_hour({}, COMMON.planning_funding_floor_bps_hour)
    state = open_position_on_candle(side, style, NOTIONAL, volatility, entry_bar, entry_book[1],
                                    cost_source=entry_book[2], planning_funding=floor)
    evaluated = 0
    for bar in bars:
        if state["status"] != "open":
            break
        cost = book_at(books, bar["time"])
        if cost is None:
            continue
        state = advance_on_candle(state, bar, BAR_S, cost[1], now, cost_source=cost[2])
        evaluated += 1
    return {"state": state, "candles_evaluated": evaluated, "atr": volatility, "entry_book_recorded_at": entry_book[0]}


def summarise(symbol, style, side, opportunity, entry_bar, outcome):
    state = outcome["state"]
    rules, record = fired(state)
    return {
        "symbol": symbol, "style": style, "side": side, "opportunity": str(opportunity["id"]),
        "opportunity_at": utc(opportunity["snapshot_ts"].timestamp()),
        "entry_time": entry_bar["time"], "entry_at": utc(entry_bar["time"]),
        "entry_open": entry_bar["open"], "entry_price": state["entry_price"], "quantity": state["quantity"],
        "entry_cost_bps": state["slippage"]["entry"]["cost_bps"], "atr": outcome["atr"],
        "entry_book_recorded_at": utc(outcome["entry_book_recorded_at"]),
        "stop": state["stop"], "target": state["target"], "expiry": state["expiry"], "expiry_at": utc(state["expiry"]),
        "candles_evaluated": outcome["candles_evaluated"], "status": state["status"], "rules_fired": rules,
        "exit": None if record is None else {key: record.get(key) for key in
                                             ("rule", "level", "trigger_price", "fill_price", "at", "gap_fill", "path", "parts")},
        "exit_at": None if record is None else utc(record["at"]),
        "net_estimate_usdc": state["net_estimate_usdc"], "gross_pnl_usdc": state["gross_pnl_usdc"], "trail": state["trail"],
    }


async def symbol_search(conn, client, symbol, start, now, per_symbol, best, census, refusals):
    minutes = await candles(client, symbol, "1m", start, now)
    books = await recorded_books(conn, symbol, start, now)
    if not minutes or not books:
        refusals.setdefault("no candles or recorded books in the window", []).append(symbol)
        return 0
    history = {style: await latest_candles(client, symbol, RULES[style].atr_interval, HISTORY_CANDLES[RULES[style].atr_interval])
               for style in STYLES}
    rows = await conn.fetch(
        "SELECT id, dir, snapshot_ts FROM public.opportunities WHERE symbol = $1 AND lower(dir) IN ('long', 'short') "
        "AND snapshot_ts BETWEEN to_timestamp($2) AND to_timestamp($3) ORDER BY snapshot_ts", symbol, start, now - 900)
    by_minute = {bar["time"]: index for index, bar in enumerate(minutes)}
    step = max(1, len(rows) // per_symbol) if rows else 1
    attempts = 0
    for opportunity in rows[::step][:per_symbol]:
        index = by_minute.get(int(opportunity["snapshot_ts"].timestamp()) // BAR_S * BAR_S)
        if index is None:
            continue
        for style in STYLES:
            attempts += 1
            try:
                outcome = replay(opportunity["dir"].lower(), style, minutes[index], minutes[index:], books, history[style], now)
            except ValueError as exc:
                refusals.setdefault(str(exc), []).append(f"{symbol} {style}")
                continue
            if "refused" in outcome:
                refusals.setdefault(outcome["refused"], []).append(f"{symbol} {style}")
                continue
            record = summarise(symbol, style, opportunity["dir"].lower(), dict(opportunity), minutes[index], outcome)
            for rule in record["rules_fired"] or ["none"]:
                census[rule] = census.get(rule, 0) + 1
            for rule in record["rules_fired"]:
                if rule in WANTED and (rule not in best or record["candles_evaluated"] < best[rule]["candles_evaluated"]):
                    best[rule] = record
    note(f"[{symbol}] minutes={len(minutes)} books={len(books)} opportunities={len(rows)} attempts={attempts} found={sorted(best)}")
    return attempts


async def search(conn, client, hours, per_symbol):
    now = time.time()
    start = now - hours * 3600
    universe = await editions.tracked_symbols(MARKET)
    best, census, refusals, attempts = {}, {}, {}, 0
    for symbol in universe:
        try:
            attempts += await symbol_search(conn, client, symbol, start, now, per_symbol, best, census, refusals)
        except httpx.HTTPError as exc:  # recorded, never replaced by a guess
            refusals.setdefault(f"market data unavailable: {type(exc).__name__}", []).append(symbol)
            note(f"[{symbol}] market data unavailable: {type(exc).__name__}")
    return {"attempts": attempts, "universe": universe, "census": census,
            "refusals": {reason: sorted(set(where)) for reason, where in refusals.items()},
            "windows": {rule: best.get(rule) for rule in WANTED}}


async def main(hours, per_symbol):
    report = {"classification": ("Real Hyperliquid 1-minute candles and the books TradeSync recorded; read-only search, "
                                 "nothing written. Engineering evidence that each rule fires, not a strategy result."),
              "searched_hours": hours, "entries_per_symbol": per_symbol, "started_at": utc(time.time())}
    conn = await asyncpg.connect(os.environ["PG_DSN"], statement_cache_size=0)
    await conn.execute("BEGIN READ ONLY")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), trust_env=False) as client:
            report.update(await search(conn, client, hours, per_symbol))
    except Exception as exc:  # the report still prints, with what the search reached
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await conn.execute("ROLLBACK")
        await conn.close()
    report["finished_at"] = utc(time.time())
    print(json.dumps(report, default=str, indent=1))
    return 0 if all(report.get("windows", {}).get(rule) for rule in WANTED) else 1


if __name__ == "__main__":
    arguments = [float(a) for a in sys.argv[1:]]
    raise SystemExit(asyncio.run(main(arguments[0] if arguments else 40.0, int(arguments[1]) if len(arguments) > 1 else 12)))
