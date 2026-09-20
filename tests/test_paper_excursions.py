"""Maximum favourable and adverse excursion: recorded by the lifecycle, recomputable from its own observations."""

import copy

import pytest

from tradesync_core import paper_depth as depth
from tradesync_core import paper_excursions as excursions
from tradesync_core.managed_paper import advance, advance_on_candle, open_position, open_position_on_candle
from tradesync_core.paper_kill import kill_close

COST_BOOK = {'bids': [[99.9, 1000.0]], 'asks': [[100.1, 1000.0]]}
COST_SOURCE = depth.snapshot(COST_BOOK, observed_at=900, received_at=901, source='market_depth_snapshots', precision='aggregated_3_sig_figs')


def book(at, bid, ask, size=100.0):
    return {'poll_ts': at * 1000, 'best_bid': bid, 'best_ask': ask,
            'bids': [{'price': bid, 'size': size}], 'asks': [{'price': ask, 'size': size}]}


def bar(time, open, high, low, close):
    return {'time': time, 'open': open, 'high': high, 'low': low, 'close': close}


def long_scalp(at=1000):
    # ATR 1: entry 100.01, stop 98.51, target 103.01.
    return open_position('long', 'scalp', 1000, 1, book(at, 99.99, 100.01), at)


def test_the_worked_example_by_hand():
    record = excursions.start()
    for price, at in ((100.30, 1), (99.60, 2), (100.80, 3), (99.90, 4)):
        record = excursions.track(record, 'long', 100.0, [(price, at)])
    result = excursions.describe(record, 'long', 100.0, 2.0)
    assert result['status'] == 'measured' and result['observations'] == 4
    assert result['favourable'] == {'distance': pytest.approx(0.80), 'bps': pytest.approx(80.0), 'usdc': pytest.approx(1.60),
                                    'price': 100.80, 'at': 3.0}
    assert result['adverse'] == {'distance': pytest.approx(0.40), 'bps': pytest.approx(40.0), 'usdc': pytest.approx(0.80),
                                 'price': 99.60, 'at': 2.0}


def test_a_short_is_measured_on_the_ask_with_the_sides_mirrored():
    prices = [excursions.quote_prices('short', at, bid, ask)[0] for at, bid, ask in ((1, 99.0, 99.1), (2, 101.0, 101.2))]
    assert prices == [(99.1, 1), (101.2, 2)]
    record = excursions.start()
    for price in prices:
        record = excursions.track(record, 'short', 100.0, [price])
    result = excursions.describe(record, 'short', 100.0, 1.0)
    assert result['favourable']['price'] == 99.1 and result['favourable']['distance'] == pytest.approx(0.9)
    assert result['adverse']['price'] == 101.2 and result['adverse']['distance'] == pytest.approx(1.2)


def test_a_position_never_in_favour_has_a_zero_mfe_that_still_names_its_best_price():
    record = excursions.track(excursions.start(), 'long', 100.0, [(99.5, 10)])
    result = excursions.describe(record, 'long', 100.0, 1.0)
    assert result['favourable'] == {'distance': 0.0, 'bps': 0.0, 'usdc': 0.0, 'price': 99.5, 'at': 10.0}
    assert result['adverse']['distance'] == pytest.approx(0.5)


def test_nothing_observed_is_no_measurement_and_never_a_zero():
    opened = long_scalp()
    result = excursions.summary(opened)
    assert result['status'] == 'no_observation' and result['favourable'] is None and result['adverse'] is None


def test_the_lifecycle_records_every_quote_after_entry_and_the_exit_but_not_the_entry():
    p = long_scalp()
    assert p['excursion'] == excursions.start()
    quotes = [(1010, 100.4, 100.41), (1020, 99.2, 99.21), (1030, 101.2, 101.21)]
    for at, bid, ask in quotes:
        p = advance(p, book(at, bid, ask), at)
    closed = advance(p, book(1040, 98.4, 98.41), 1040)
    assert closed['exit_reason'] == 'stop'
    record = closed['excursion']
    assert record['observations'] == 4 and record['first_at'] == 1010 and record['last_at'] == 1040
    assert record['favourable'] == {'price': 101.2, 'at': 1030.0}
    assert record['adverse'] == {'price': 98.4, 'at': 1040.0}
    result = excursions.summary(closed)
    assert result['adverse']['distance'] == pytest.approx(closed['entry_price'] - 98.4)
    assert result['adverse']['usdc'] == pytest.approx((closed['entry_price'] - 98.4) * closed['quantity'])
    # A closed position records nothing further.
    assert advance(closed, book(1050, 90.0, 90.01), 1050)['excursion'] == record


def test_the_stored_record_is_recomputed_exactly_from_the_observations_its_events_kept():
    p = long_scalp()
    books = [book(1010, 100.4, 100.41), book(1020, 100.4, 100.41), book(1030, 99.2, 99.21), book(1040, 101.6, 101.61)]
    for current in books:
        p = advance(p, current, current['poll_ts'] / 1000)
    observed = [{'observed_at': b['poll_ts'] / 1000, 'best_bid': b['best_bid'], 'best_ask': b['best_ask']} for b in books]
    # The entry book, an observation after the last evaluation and a funding event's missing book are all ignored.
    extra = [{'observed_at': 1000, 'best_bid': 50.0, 'best_ask': 50.1}, {'observed_at': 1100, 'best_bid': 200.0, 'best_ask': 200.1}]
    assert excursions.recompute(p, list(reversed(observed)) + extra) == p['excursion']
    assert p['excursion']['favourable'] == {'price': 101.6, 'at': 1040.0}


def test_a_tie_keeps_the_earlier_extreme():
    record = excursions.start()
    for at in (10, 20):
        record = excursions.track(record, 'long', 100.0, [(100.4, at)])
    assert record['favourable'] == {'price': 100.4, 'at': 10.0} and record['adverse'] == {'price': 100.4, 'at': 10.0}


def test_a_kill_switch_close_is_an_observation_like_any_other():
    p = advance(long_scalp(), book(1010, 100.6, 100.61), 1010)
    closed = kill_close(p, book(1020, 99.0, 99.01), 1020, operator='chase', reason='testing the record')
    assert closed['exit_reason'] == 'kill_switch'
    assert closed['excursion']['observations'] == 2 and closed['excursion']['adverse'] == {'price': 99.0, 'at': 1020.0}


def test_a_candle_that_fired_nothing_contributes_its_high_and_low():
    p = advance_on_candle(long_scalp(), bar(1020, 100.2, 101.4, 99.0, 100.5), 60, COST_BOOK, 1080, cost_source=COST_SOURCE)
    assert p['status'] == 'open'
    assert p['excursion']['favourable'] == {'price': 101.4, 'at': 1020.0}
    assert p['excursion']['adverse'] == {'price': 99.0, 'at': 1020.0}


def test_a_candle_that_held_an_exit_contributes_only_its_open_and_the_exit_price():
    closed = advance_on_candle(long_scalp(), bar(1020, 100.5, 104.0, 98.0, 101.0), 60, COST_BOOK, 1080, cost_source=COST_SOURCE)
    assert closed['status'] == 'closed' and closed['exit_reason'] == 'stop' and closed['exit']['ambiguous_candle'] is True
    # Its high of 104 and low of 98 lie beyond prices the position is known to have held through: the order of a
    # candle's high and low is unknown, and it left at the stop.
    assert closed['excursion']['adverse'] == {'price': pytest.approx(98.51), 'at': 1020.0}
    assert closed['excursion']['favourable'] == {'price': 100.5, 'at': 1020.0}
    assert closed['excursion']['observations'] == 1


def test_a_candle_entry_starts_the_record_like_a_quote_entry():
    p = open_position_on_candle('long', 'scalp', 1000, 1, bar(2000, 100.0, 100.2, 99.9, 100.1), COST_BOOK, cost_source=COST_SOURCE)
    assert p['excursion'] == excursions.start()


def test_a_position_opened_before_excursions_were_recorded_stays_untracked():
    legacy = copy.deepcopy(long_scalp())
    del legacy['excursion']
    advanced = advance(legacy, book(1010, 101.0, 101.01), 1010)
    assert 'excursion' not in advanced
    result = excursions.summary(advanced)
    assert result['status'] == 'not_tracked' and result['favourable'] is None and 'reconstruction' in result['reason']


@pytest.mark.parametrize('prices', [[], [(0.0, 1)], [(100.0, None)], [(float('nan'), 1)]])
def test_an_observation_without_a_positive_price_and_a_time_is_refused(prices):
    with pytest.raises(ValueError):
        excursions.track(excursions.start(), 'long', 100.0, prices)


def test_an_unknown_side_or_entry_is_refused():
    with pytest.raises(ValueError):
        excursions.track(excursions.start(), 'flat', 100.0, [(100.0, 1)])
    with pytest.raises(ValueError):
        excursions.describe(excursions.start(), 'long', 0.0, 1.0)
