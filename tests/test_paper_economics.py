"""Per-position paper economics and expectancy, read from the lifecycle's own state."""

import copy

import pytest

from tradesync_core import paper_economics as economics
from tradesync_core import paper_funding as funding
from tradesync_core.managed_paper import advance, open_position, settle_funding
from tradesync_core.paper_account_ledger import realised_entry


def book(at, bid, ask, size=100.0):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': size}], 'asks': [{'price': ask, 'size': size}]}


def long_scalp(at=1000):
    return open_position('long', 'scalp', 1000, 1, book(at, 99.99, 100.01), at)


def closed_long():
    p = long_scalp(at=3500)
    p = advance(p, book(3510, 100.9, 100.91), 3510)
    p = advance(p, book(3520, 99.4, 99.41), 3520)
    row = funding.settle('long', p['quantity'], 3600, {'funding_rate': 1e-4, 'premium': 0.0},
                         {'value': 100.0, 'source': 'market_open_interest.oracle_price', 'observed_at': 3590})
    return advance(p, book(3610, 101.2, 101.21), 3610, manual_close=True, funding_rows=[row])


def row(status, realised, risk, provisional=False, gap=False):
    return {'status': status, 'r_multiple': realised / risk if realised is not None and risk else None,
            'pnl': {'realised_usdc': realised, 'provisional': provisional}, 'observation_gap': gap}


def test_the_worked_example_by_hand():
    result = economics.expectancy([row('closed', 3.0, 2.0), row('closed', -1.0, 2.0), row('closed', -0.5, 1.0)])
    assert result['sample_size'] == 3 and result['sample_size_r'] == 3
    assert result['expectancy_usdc'] == pytest.approx(0.5)
    assert result['win_rate'] == pytest.approx(1 / 3) and result['loss_rate'] == pytest.approx(2 / 3)
    assert result['mean_win_usdc'] == pytest.approx(3.0) and result['mean_loss_usdc'] == pytest.approx(0.75)
    # E = w * W - l * L
    assert result['win_rate'] * result['mean_win_usdc'] - result['loss_rate'] * result['mean_loss_usdc'] == pytest.approx(0.5)
    assert result['expectancy_r'] == pytest.approx(0.5 / 3)
    assert result['total_realised_usdc'] == pytest.approx(1.5)


def test_no_closed_position_is_no_expectancy_and_never_a_zero():
    result = economics.expectancy([row('open', None, 2.0)])
    assert result['sample_size'] == 0 and result['expectancy_usdc'] is None and result['expectancy_r'] is None
    assert result['reason'] == 'no closed paper position in this reading'
    assert economics.expectancy([])['expectancy_usdc'] is None


def test_open_positions_and_unknown_risk_stay_out_of_the_means_that_cannot_use_them():
    result = economics.expectancy([row('closed', 2.0, None), row('closed', -1.0, 1.0), row('open', None, 1.0),
                                   row('closed', 0.0, 1.0, provisional=True, gap=True)])
    assert result['sample_size'] == 3 and result['sample_size_r'] == 2 and result['flat'] == 1
    assert result['expectancy_usdc'] == pytest.approx(1 / 3) and result['expectancy_r'] == pytest.approx(-0.5)
    assert result['provisional'] == 1 and result['with_observation_gap'] == 1


def test_a_closed_position_states_fees_funding_slippage_and_its_realised_result():
    state = closed_long()
    assert state['status'] == 'closed' and state['funding']['status'] == 'complete'
    result = economics.position('p1', 'BTC-PERP', state, opportunity_id='o1', opened_at='2026-09-16T12:00:00+00:00')
    fees, paid, slip, pnl = result['fees'], result['funding'], result['slippage'], result['pnl']

    assert fees['entry_usdc'] == pytest.approx(state['fees']['entry_usdc']) and fees['exit_usdc'] == pytest.approx(state['fees']['exit_usdc'])
    assert fees['exit_estimate_usdc'] is None and fees['total_usdc'] == pytest.approx(fees['entry_usdc'] + fees['exit_usdc'])
    assert paid['accrued_usdc'] == pytest.approx(state['quantity'] * 100 * 1e-4) and paid['missing_hours'] == []
    assert slip['total_usdc'] == pytest.approx(slip['entry']['cost_usdc'] + slip['exit']['cost_usdc'])
    assert pnl['realised_usdc'] == pytest.approx(pnl['gross_usdc'] - pnl['fees_usdc'] - pnl['funding_usdc'])
    assert pnl['net_equals_gross_less_fees_less_funding'] is True and pnl['provisional'] is False
    assert pnl['unrealised_estimate_usdc'] is None
    # The same realised figure the paper account ledger books for this close.
    assert float(realised_entry('p1', state).amount_usdc) == pytest.approx(pnl['realised_usdc'], abs=1e-8)
    assert result['r_multiple'] == pytest.approx(pnl['realised_usdc'] / state['planned_risk_usdc'])
    assert result['exit_reason'] == 'operator_close' and result['exit_price'] == state['exit_price']
    excursion = result['excursions']
    assert excursion['status'] == 'measured' and excursion['observations'] == 3
    assert excursion['favourable']['price'] == 101.2 and excursion['adverse']['price'] == 99.4


def test_an_open_position_estimates_its_exit_fee_and_has_no_realised_result():
    state = advance(long_scalp(), book(1010, 100.5, 100.51), 1010)
    result = economics.position('p2', 'ETH-PERP', state)
    assert result['status'] == 'open' and result['exit_time'] is None and result['exit_reason'] is None
    assert result['fees']['exit_usdc'] is None and result['fees']['exit_estimate_usdc'] == pytest.approx(state['fees']['exit_estimate_usdc'])
    assert 'estimated' in result['fees']['basis']
    assert result['pnl']['realised_usdc'] is None and result['pnl']['unrealised_estimate_usdc'] == pytest.approx(state['net_estimate_usdc'])
    assert result['slippage']['exit'] is None and result['slippage']['total_usdc'] == pytest.approx(state['slippage']['entry']['cost_usdc'])
    assert result['r_multiple'] is None


def test_a_close_still_waiting_for_a_funding_hour_is_provisional():
    p = long_scalp(at=3500)
    closed = advance(p, book(3610, 100.5, 100.51), 3610, manual_close=True)
    assert closed['funding']['missing_hours'] == [3600]
    result = economics.position('p3', 'SOL-PERP', closed)
    assert result['pnl']['provisional'] is True and result['funding']['missing_hours'] == [3600]
    settled = settle_funding(closed, [funding.settle('long', closed['quantity'], 3600, {'funding_rate': 1e-4, 'premium': 0.0},
                                                     {'value': 100.0, 'source': 'oracle', 'observed_at': 3590})])
    assert economics.position('p3', 'SOL-PERP', settled)['pnl']['provisional'] is False


def test_a_net_that_disagrees_with_its_parts_is_reported_not_hidden():
    state = copy.deepcopy(closed_long())
    state['net_estimate_usdc'] += 0.01
    assert economics.position('p4', 'BTC-PERP', state)['pnl']['net_equals_gross_less_fees_less_funding'] is False


def test_an_unreadable_state_says_so_rather_than_failing_the_reading():
    state = copy.deepcopy(closed_long())
    state['side'] = None
    result = economics.position('p5', 'BTC-PERP', state)
    assert result['excursions']['status'] == 'unreadable' and result['excursions']['favourable'] is None


def test_the_text_the_outcomes_tab_prints_avoids_retired_wording():
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_ui_wording import RETIRED
    from tradesync_core import paper_excursions

    state = closed_long()
    texts = [economics.NOTE, paper_excursions.BASIS, paper_excursions.NOT_TRACKED]
    for result in (economics.position('p', 'BTC-PERP', state), economics.position('q', 'BTC-PERP', long_scalp()),
                   economics.expectancy([]), economics.expectancy([row('closed', 1.0, 1.0)])):
        stack = [result]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, str):
                texts.append(item)
    assert [text for text in texts if RETIRED.search(text)] == []
