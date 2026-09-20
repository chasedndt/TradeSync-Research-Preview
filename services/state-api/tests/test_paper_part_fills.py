"""An exit the observed book can only fill in part, through the observer and the funding store."""

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app import paper_funding_store
from paper_fakes import H, SYMBOL, FakeConn, FakeMarket, book, market_routes
from test_paper_positions_routes import build, held_position, position_handlers
from tradesync_core.managed_paper import advance, open_position

ENTRY = 10 * H + 600


def rates(*hours, rate=1.25e-05):
    return {hour: {'funding_rate': rate, 'premium': 0.0} for hour in hours}


def part_filled():
    """A position whose exit filled part of itself a minute before the hour and the rest a minute after."""
    plan = open_position('long', 'intraday', 250, 0.5, book(ENTRY), ENTRY)
    part = advance(plan, book(11 * H - 60, size=0.1), 11 * H - 60, manual_close=True)
    return plan, part, advance(part, book(11 * H + 60), 11 * H + 60)


@pytest.fixture
def thin_market():
    FakeMarket.routes = [(f'/depth/hyperliquid/{SYMBOL}', lambda url, params: (200, book(time.time(), size=0.1)))] + market_routes()
    FakeMarket.requested = []
    with patch('httpx.AsyncClient', FakeMarket):
        yield FakeMarket


def test_the_exit_fills_what_the_bound_allows_and_owes_the_rest():
    plan, part, closed = part_filled()
    assert part['status'] == 'open' and part['pending_exit']['rule'] == 'operator_close'
    assert 0 < part['open_quantity'] < plan['quantity']
    # The intraday bound of 10 bps past the touch reaches five of the ten displayed levels, 0.1 each.
    assert part['exit_parts'][0]['quantity'] == pytest.approx(0.5)
    assert part['exit_parts'][0]['fill_price'] == pytest.approx(49.97)
    assert part['exit_parts'][0]['fill']['limited_by'] == 'depth_bound'
    assert closed['status'] == 'closed' and closed['exit']['parts'] == 2 and closed['open_quantity'] == 0.0


def test_each_stored_settlement_pays_the_quantity_held_at_that_hour():
    plan, part, closed = part_filled()
    conn = FakeConn(position_handlers(closed))
    added = asyncio.run(paper_funding_store.store(conn, uuid.uuid4(), SYMBOL, closed, rates(11 * H), 11 * H + 90, 11 * H + 90))
    assert added == 1 and len(conn.funding) == 1
    row = conn.funding[0]
    assert part['open_quantity'] < plan['quantity']
    assert row['quantity'] == pytest.approx(part['open_quantity'])
    assert row['payment_usdc'] == pytest.approx(part['open_quantity'] * 50.5 * 1.25e-05)


def test_an_open_position_settles_only_the_hours_it_has_been_observed_past():
    plan, part, _ = part_filled()
    conn = FakeConn(position_handlers(part))
    # Evaluated only to a minute before the hour: the settlement waits for an observation past it,
    # because a part filled in between would change the quantity that hour is paid on.
    assert asyncio.run(paper_funding_store.store(conn, uuid.uuid4(), SYMBOL, part, rates(11 * H), 11 * H + 90, 11 * H + 90)) == 0
    assert conn.funding == []
    observed = advance(plan, book(11 * H + 60), 11 * H + 60)
    assert asyncio.run(paper_funding_store.store(conn, uuid.uuid4(), SYMBOL, observed, rates(11 * H), 11 * H + 90, 11 * H + 90)) == 1
    assert conn.funding[0]['quantity'] == pytest.approx(plan['quantity'])


def test_the_observer_records_a_part_fill_and_leaves_the_rest_owed(thin_market):
    conn = FakeConn(position_handlers(held_position(time.time())))
    _, handles = build(conn)
    with patch('app.managed_paper.record_position_event', AsyncMock()):
        result = asyncio.run(handles.update(uuid.uuid4(), manual=True))
    assert result['status'] == 'open' and result['pending_exit']['rule'] == 'operator_close'
    assert len(result['exit_parts']) == 1 and 0 < result['open_quantity'] < result['quantity']
    assert result['pending_exit']['remaining_quantity'] == pytest.approx(result['open_quantity'])
    (_, _, kind, _), = conn.statements('INSERT INTO managed_paper_events')
    assert kind == 'observed'
