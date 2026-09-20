"""Fills the observed book can only take in part: the style's depth bound, exits in parts, and exact accounts."""

import pytest

from test_paper_account_ledger import stored
from tradesync_core import paper_depth as depth
from tradesync_core import paper_exit_fills as fills
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, advance_on_candle, open_position, settle_funding
from tradesync_core.paper_account import mark
from tradesync_core.paper_account_ledger import compare, expected_entries, funding_adjustment, money, realised_entry

# Buying from 100.1 or selling into 99.9 costs 10 bps against the 100 mid; 1000 units a side fills anything here.
COST_BOOK = {'bids': [[99.9, 1000.0]], 'asks': [[100.1, 1000.0]]}
THIN_BOOK = {'bids': [[99.9, 2.0]], 'asks': [[100.1, 2.0]]}
COST_SOURCE = depth.snapshot(COST_BOOK, observed_at=900, received_at=901, source='market_depth_snapshots',
                             precision='aggregated_3_sig_figs')
H = 3600


def book(at, bid, ask, size=100.0):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': size}], 'asks': [{'price': ask, 'size': size}]}


def bar(time, open, high, low, close):
    return {'time': time, 'open': open, 'high': high, 'low': low, 'close': close}


def long_scalp(at=1000):
    # ATR 1: entry 100.01, stop 98.51, target 103.01. The scalp bound is 5 bps past the touch.
    return open_position('long', 'scalp', 1000, 1, book(at, 99.99, 100.01), at)


def settlement(state, hour, rate=1e-4):
    return funding.settle(state['side'], fills.held_quantity(state, hour), hour, {'funding_rate': rate},
                          {'value': 100.0, 'source': 'test'})


def test_a_walk_takes_no_level_past_the_bound_and_says_what_stopped_it():
    ladder = {'bids': [[99.99, 1.0], [99.90, 100.0]], 'asks': [[100.01, 1.0], [100.10, 100.0]]}
    within = depth.walk(ladder, 'sell', quantity=1.0, max_depth_bps=5)
    assert within['complete'] is True and within['levels_within_bound'] == 1 and within['unfilled'] == 0.0
    partial = depth.walk(ladder, 'sell', quantity=4.0, max_depth_bps=5, partial=True)
    assert partial['complete'] is False and partial['quantity'] == pytest.approx(1.0)
    assert partial['unfilled'] == pytest.approx(3.0) and partial['limited_by'] == 'depth_bound'
    assert '5 bps past the touch' in partial['shortfall'] and partial['mark_price'] == pytest.approx(99.99)
    with pytest.raises(depth.InsufficientDepth, match='depth bound'):
        depth.walk(ladder, 'sell', quantity=4.0, max_depth_bps=5)
    unbounded = depth.walk(ladder, 'sell', quantity=4.0)
    assert unbounded['complete'] is True and unbounded['levels_within_bound'] == 2


def test_an_entry_the_book_can_only_fill_past_the_bound_is_refused_with_the_share_it_could_fill():
    # 100.08 is 7 bps past the touch: outside the scalp bound of 5, so the size is not taken at all.
    deep = dict(book(1000, 99.99, 100.01), asks=[{'price': 100.01, 'size': 4}, {'price': 100.08, 'size': 50}])
    with pytest.raises(ValueError, match='40.0% of the size'):
        open_position('long', 'scalp', 1000, 1, deep, 1000)
    with pytest.raises(ValueError, match='depth bound'):
        open_position('long', 'scalp', 1000, 1, deep, 1000)
    # Swing declares 20 bps, so the same book fills the same size.
    swing = open_position('long', 'swing', 1000, 1, deep, 1000)
    assert [level[0] for level in swing['slippage']['entry']['levels_taken']] == [100.01, 100.08]
    assert swing['rules']['max_depth_bps'] == 20.0


def test_an_exit_fills_in_parts_each_with_its_own_price_fee_and_book():
    position = long_scalp()
    first = advance(position, book(1010, 98.0, 98.01, size=4.0), 1010)
    assert first['status'] == 'open' and first['pending_exit']['rule'] == 'stop'
    assert first['pending_exit']['remaining_quantity'] == pytest.approx(position['quantity'] - 4.0)
    second = advance(first, book(1025, 97.5, 97.51, size=3.0), 1025)
    assert second['status'] == 'open' and len(second['exit_parts']) == 2
    closed = advance(second, book(1040, 97.0, 97.01), 1040)
    parts, rate = closed['exit_parts'], closed['fees']['rate']
    rest = closed['quantity'] - 7.0
    assert [p['quantity'] for p in parts] == [pytest.approx(4.0), pytest.approx(3.0), pytest.approx(rest)]
    assert [p['fill_price'] for p in parts] == [98.0, 97.5, 97.0]
    assert [p['fee_usdc'] for p in parts] == [pytest.approx(rate * 98.0 * 4), pytest.approx(rate * 97.5 * 3),
                                              pytest.approx(rate * 97.0 * rest)]
    assert [p['observation']['observed_at'] for p in parts] == [1010, 1025, 1040]
    assert [p['fill']['snapshot']['observed_at'] for p in parts] == [1010, 1025, 1040]
    assert closed['exit_reason'] == 'stop' and closed['exit_time'] == 1040 and closed['exit']['parts'] == 3
    assert closed['open_quantity'] == 0.0 and closed['pending_exit'] is None
    assert closed['fees']['exit_usdc'] == pytest.approx(sum(p['fee_usdc'] for p in parts))
    assert closed['gross_pnl_usdc'] == pytest.approx(sum((p['fill_price'] - closed['entry_price']) * p['quantity'] for p in parts))
    assert closed['exit_price'] == pytest.approx(sum(p['fill_price'] * p['quantity'] for p in parts) / closed['quantity'])
    assert closed['net_estimate_usdc'] == pytest.approx(closed['gross_pnl_usdc'] - closed['fees_usdc'] - closed['funding_usdc'])
    exit_fill = closed['slippage']['exit']
    assert exit_fill['basis'] == 'book_walk_parts' and exit_fill['parts'] == 3
    assert exit_fill['cost_usdc'] == pytest.approx(sum(p['fill']['cost_usdc'] for p in parts))
    assert exit_fill['fill_price'] == pytest.approx(closed['exit_price'])


def test_a_position_with_a_part_filled_marks_and_exposes_only_what_is_still_held():
    part = advance(long_scalp(), book(1010, 98.0, 98.01, size=4.0), 1010)
    held = part['quantity'] - 4.0
    rate = part['fees']['rate']
    assert part['open_quantity'] == pytest.approx(held) and part['mark_exit_price'] == pytest.approx(98.0)
    assert part['gross_pnl_usdc'] == pytest.approx((98.0 - part['entry_price']) * 4.0 + (98.0 - part['entry_price']) * held)
    assert part['fees']['exit_estimate_usdc'] == pytest.approx(rate * 98.0 * 4.0 + rate * 98.0 * held)
    marked = mark('p1', 'BTC-PERP', part)
    assert marked.quantity == pytest.approx(held) and marked.notional_usdc == pytest.approx(held * 98.0)
    assert marked.unrealised_usdc == part['net_estimate_usdc']


def test_each_settlement_pays_the_quantity_held_at_that_hour():
    position = long_scalp(at=H - 100)
    part = advance(position, book(H - 50, 98.0, 98.01, size=4.0), H - 50)
    assert fills.held_quantity(part, H - 100) == pytest.approx(position['quantity'])
    assert fills.held_quantity(part, H) == pytest.approx(position['quantity'] - 4.0)
    closed = advance(part, book(H + 100, 97.0, 97.01), H + 100)
    assert fills.held_quantity(closed, H) == pytest.approx(position['quantity'] - 4.0)
    assert fills.held_quantity(closed, 2 * H) == 0.0
    settled = settle_funding(closed, [settlement(closed, H)])
    assert settled['funding']['settled_hours'] == 1
    assert settled['funding_usdc'] == pytest.approx((position['quantity'] - 4.0) * 100.0 * 1e-4)
    assert settled['net_estimate_usdc'] == pytest.approx(settled['gross_pnl_usdc'] - settled['fees_usdc'] - settled['funding_usdc'])


def test_a_part_filled_close_books_once_and_late_funding_adjusts_by_exactly_the_change():
    position = long_scalp(at=H - 100)
    part = advance(position, book(H - 50, 98.0, 98.01, size=4.0), H - 50)
    at_close = advance(part, book(H + 100, 97.0, 97.01), H + 100)  # the hour's rate is not published yet
    assert at_close['funding']['missing_hours'] == [H] and at_close['funding_usdc'] == 0
    entry = realised_entry('p1', at_close)
    assert entry.gross_pnl_usdc == money(at_close['gross_pnl_usdc']) and entry.fees_usdc == money(at_close['fees_usdc'])
    assert entry.amount_usdc == entry.gross_pnl_usdc - entry.fees_usdc - entry.funding_usdc
    costs = at_close['slippage']['entry']['cost_usdc'] + sum(p['fill']['cost_usdc'] for p in at_close['exit_parts'])
    assert float(entry.slippage_usdc) == pytest.approx(costs)
    entries = expected_entries(10_000, 0.0, [('p1', at_close, at_close)])
    rows, account = stored(entries)
    assert compare(rows, account, entries) == []
    # The hour settles on the quantity still held at it, after the first part had already left.
    late = settle_funding(at_close, [settlement(at_close, H)])
    assert late['funding_usdc'] == pytest.approx((position['quantity'] - 4.0) * 100.0 * 1e-4)
    adjustment = funding_adjustment('p1', entry.funding_usdc, late, at_close['exit_time'])
    assert adjustment.funding_usdc == money(late['funding_usdc']) and adjustment.amount_usdc == -adjustment.funding_usdc
    with_late = expected_entries(10_000, 0.0, [('p1', at_close, late)])
    assert compare(*stored(with_late), with_late) == []


def test_a_candle_exit_the_recorded_book_can_only_part_fill_finishes_at_the_next_open():
    first = advance_on_candle(long_scalp(), bar(1020, 97.0, 97.5, 96.5, 97.2), 60, THIN_BOOK, 1080, cost_source=COST_SOURCE)
    assert first['status'] == 'open' and first['pending_exit']['rule'] == 'stop'
    assert first['exit_parts'][0]['quantity'] == pytest.approx(2.0)
    assert first['exit_parts'][0]['fill_price'] == pytest.approx(97.0 * 0.999)
    assert first['pending_exit']['remaining_quantity'] == pytest.approx(first['quantity'] - 2.0)
    closed = advance_on_candle(first, bar(1080, 96.8, 96.9, 96.0, 96.2), 60, COST_BOOK, 1140, cost_source=COST_SOURCE)
    assert closed['status'] == 'closed' and closed['exit']['parts'] == 2 and closed['exit_time'] == 1080
    assert closed['exit_parts'][1]['fill_price'] == pytest.approx(96.8 * 0.999)
    assert closed['exit']['trigger_observation']['open_time'] == 1020 and closed['exit']['fill_observation']['open_time'] == 1080
    assert closed['gross_pnl_usdc'] == pytest.approx(sum((p['fill_price'] - closed['entry_price']) * p['quantity']
                                                         for p in closed['exit_parts']))


def test_a_position_opened_under_the_earlier_rules_fills_whole_or_stays_wholly_owed():
    v2 = long_scalp()
    v2['rules'] = {**{k: value for k, value in v2['rules'].items() if k != 'max_depth_bps'},
                   'version': 'managed-paper-lifecycle-v2'}
    owed = advance(v2, book(1010, 98.0, 98.01, size=5), 1010)
    assert owed['status'] == 'open' and owed['exit_parts'] == [] and owed['pending_exit']['parts'] == 0
    assert owed['pending_exit']['remaining_quantity'] == pytest.approx(v2['quantity'])
    closed = advance(owed, book(1020, 99.0, 99.01), 1020)
    assert closed['exit_price'] == 99.0 and closed['exit']['parts'] == 1
    assert closed['slippage']['exit']['basis'] == 'book_walk'
