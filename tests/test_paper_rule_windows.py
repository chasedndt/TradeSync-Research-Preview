"""Real Hyperliquid windows where each exit rule fires, replayed from stored fixtures.

Each fixture holds one real window: its 1-minute candles, the candles its average true
range was measured on, the books TradeSync recorded (3 significant figures), the funding
that settled, and the exit the declared rules produced when it was replayed in the
isolated acceptance schema (``tools/qa_paper_rule_fixtures.py``). Its ``source`` names
where every part came from and its ``window`` the exact times.

Replaying them here keeps those windows as regression evidence: the target, the time
expiry and an adverse fill at a candle's open each fire on real venue data, not only on
constructed books. A change to the rules changes these outcomes, and the fixtures must
then be re-recorded under the new version rather than edited.
"""

import json
from bisect import bisect_right
from pathlib import Path

import pytest

from tradesync_core import paper_depth as depth
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance_on_candle, atr, open_position_on_candle, settle_funding
from tradesync_core.paper_lifecycle_rules import COMMON, RULES

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "paper_rules"
FIXTURES = sorted(FIXTURE_DIR.glob("*.json"))
BAR_S = 60


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def by_rule(rule):
    return load(FIXTURE_DIR / f"{rule}.json")


def books_of(fixture):
    books = []
    for entry in fixture["books"]:
        book = {"bids": entry["bids"], "asks": entry["asks"]}
        books.append((entry["recorded_at"], book,
                      depth.snapshot(book, observed_at=entry["observed_at"], received_at=entry["recorded_at"],
                                     source="market_depth_snapshots", precision="aggregated_3_sig_figs")))
    return books


def book_at(books, at):
    return books[bisect_right([book[0] for book in books], at) - 1]


def replay(fixture):
    """The window replayed exactly as the acceptance replayed it: entry at the minute's open, then every closed minute."""
    rules = RULES[fixture["style"]]
    entry_time = fixture["window"]["entry_time"]
    bars, books = fixture["candles"], books_of(fixture)
    volatility = atr(fixture["atr_candles"], rules.atr_seconds, entry_time, rules.atr_period)
    entry_book = book_at(books, entry_time)
    now = fixture["window"]["exit_time"] + 2 * BAR_S
    state = open_position_on_candle(
        fixture["side"], fixture["style"], fixture["notional_usdc"], volatility, bars[0], entry_book[1],
        cost_source=entry_book[2], planning_funding=funding.planning_bps_hour({}, COMMON.planning_funding_floor_bps_hour))
    for bar in bars:
        if state["status"] != "open":
            break
        cost = book_at(books, bar["time"])
        state = advance_on_candle(state, bar, BAR_S, cost[1], now, cost_source=cost[2])
    return settle_funding(state, fixture["funding_rows"]), volatility


def test_every_rule_this_branch_proved_has_a_recorded_window():
    assert {load(path)["rule"] for path in FIXTURES} == {"target", "time_expiry", "gap_at_open"}
    for path in FIXTURES:
        fixture = load(path)
        assert fixture["source"]["candles"].startswith("Hyperliquid") and fixture["window"]["entry_at"].endswith("Z")
        assert fixture["candles"] and fixture["books"] and fixture["atr_candles"]


@pytest.mark.parametrize("path", FIXTURES, ids=[path.stem for path in FIXTURES])
def test_the_recorded_window_fires_its_rule_exactly_as_it_did_on_real_candles(path):
    fixture = load(path)
    state, volatility = replay(fixture)
    expected = fixture["expected"]
    # A rules revision changes these outcomes: re-record the windows under the new version.
    assert state["version"] == fixture["lifecycle_version"]
    assert volatility == pytest.approx(fixture["atr"])
    assert state["status"] == "closed" and state["candles"] == expected["candles"]
    assert state["exit"]["rule"] == expected["rule"] and state["exit"]["path"] == expected["path"]
    assert state["exit"]["gap_fill"] is expected["gap_fill"] and state["exit"]["parts"] == expected["parts"]
    assert state["exit"]["at"] == expected["at"] and state["exit_time"] == expected["at"]
    for key in ("entry_price", "quantity", "stop", "target", "expiry"):
        assert state[key] == pytest.approx(expected[key]), key
    assert state["exit"]["level"] == pytest.approx(expected["level"])
    assert state["exit"]["fill_price"] == pytest.approx(expected["fill_price"])
    for key in ("gross_pnl_usdc", "fees_usdc", "funding_usdc", "net_estimate_usdc"):
        assert state[key] == pytest.approx(expected[key]), key
    assert state["net_estimate_usdc"] == pytest.approx(state["gross_pnl_usdc"] - state["fees_usdc"] - state["funding_usdc"])


def test_the_target_window_fires_at_the_declared_level_inside_a_real_candle():
    fixture = by_rule("target")
    state, _ = replay(fixture)
    assert state["exit"]["rule"] == "target" and state["exit"]["level"] == pytest.approx(state["target"])
    assert state["exit"]["gap_fill"] is False and state["exit"]["at"] < state["expiry"]


def test_the_time_expiry_window_fires_at_or_after_the_declared_expiry():
    fixture = by_rule("time_expiry")
    state, _ = replay(fixture)
    assert state["exit"]["rule"] == "time_expiry" and state["exit"]["path"] == "close"
    assert state["exit"]["at"] >= state["expiry"] and state["exit"]["at"] - state["entry_time"] >= RULES[fixture["style"]].max_hold_s


def test_the_gap_at_a_candle_open_fills_at_the_open_past_the_level_and_worse_than_it():
    fixture = by_rule("gap_at_open")
    state, _ = replay(fixture)
    record = state["exit"]
    opened = next(bar for bar in fixture["candles"] if bar["time"] == record["trigger_observation"]["open_time"])
    sign = 1 if state["side"] == "long" else -1
    assert record["path"] == "open" and record["gap_fill"] is True
    assert record["trigger_price"] == pytest.approx(opened["open"])
    # The level was already passed when the candle opened, so the fill is worse than the level, never at it.
    assert sign * (record["fill_price"] - record["level"]) < 0
    assert sign * (opened["open"] - record["level"]) < 0
