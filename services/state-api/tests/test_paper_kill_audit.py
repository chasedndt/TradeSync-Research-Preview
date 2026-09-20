"""A kill-switch exit the displayed book held owed is audited by whichever path fills it."""

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app import paper_control_store as control
from app import paper_kill_audit
from paper_fakes import SYMBOL, FakeMarket, book, market_routes
from paper_fakes import FakeConn as PositionsConn
from test_paper_positions_routes import build, held_position, position_handlers
from tradesync_core.managed_paper import advance
from tradesync_core.paper_kill import kill_close

OPERATOR = 'chase'
REASON = 'Stop all paper risk for review'


@pytest.fixture
def market():
    FakeMarket.routes, FakeMarket.requested = market_routes(), []
    with patch('httpx.AsyncClient', FakeMarket):
        yield FakeMarket


def owed(now, **authority):
    """A position whose kill-switch exit the displayed book could not fill, its stop hit at the same quote."""
    return kill_close(held_position(now), book(now - 5, bid=49.0, ask=49.02, size=0.1), now - 5, **authority)


def test_the_observer_filling_a_held_kill_switch_exit_writes_the_same_close_audit(market, monkeypatch):
    now = time.time()
    state = owed(now, operator=OPERATOR, reason=REASON)
    assert state['status'] == 'open' and state['pending_exit']['rule'] == 'kill_switch'
    conn = PositionsConn(position_handlers(state))
    _, handles = build(conn)
    audited = AsyncMock()
    monkeypatch.setattr(control, 'kill_event', audited)
    identity = uuid.uuid4()
    with patch('app.managed_paper.record_position_event', AsyncMock()):
        result = asyncio.run(handles.update(identity))
    assert result['status'] == 'closed' and result['exit_reason'] == 'kill_switch'
    kwargs = audited.await_args.kwargs
    assert (kwargs['action'], kwargs['operator'], kwargs['reason']) == ('close', OPERATOR, REASON)
    assert kwargs['position_id'] == identity
    detail = kwargs['detail']
    assert detail['symbol'] == SYMBOL and detail['coincided_rule'] == 'stop'
    assert detail['held'] is True and detail['filled_by'] == 'observer'
    assert detail['exit_price'] == result['exit_price'] and detail['exit_time'] == result['exit_time']
    (_, _, kind, payload), = conn.statements('INSERT INTO managed_paper_events')
    assert kind == 'closed' and json.loads(payload)['kill_switch'] == {'operator': OPERATOR, 'reason': REASON}


def test_an_ordinary_operator_close_writes_no_kill_switch_audit(market, monkeypatch):
    conn = PositionsConn(position_handlers(held_position(time.time())))
    _, handles = build(conn)
    audited = AsyncMock()
    monkeypatch.setattr(control, 'kill_event', audited)
    with patch('app.managed_paper.record_position_event', AsyncMock()):
        result = asyncio.run(handles.update(uuid.uuid4(), manual=True))
    assert result['exit_reason'] == 'operator_close'
    audited.assert_not_awaited()


def test_the_standing_kill_names_a_close_whose_owed_exit_recorded_no_authority(monkeypatch):
    now = time.time()
    state = owed(now)  # owed before its kill recorded an operator and reason
    assert 'kill_switch' not in state['pending_exit']
    closed = advance(state, book(now, bid=49.0, ask=49.02), now)
    audited = AsyncMock()
    monkeypatch.setattr(control, 'kill_event', audited)
    monkeypatch.setattr(control, 'kill_state', AsyncMock(return_value={'active': True, 'operator': 'operator on duty',
                                                                      'reason': 'Standing kill switch'}))
    assert asyncio.run(paper_kill_audit.record_close(object(), 'p1', SYMBOL, closed, filled_by='kill_switch')) is True
    assert audited.await_args.kwargs['operator'] == 'operator on duty'
    assert audited.await_args.kwargs['reason'] == 'Standing kill switch'


def test_other_closes_are_not_audited_and_an_unattributable_kill_close_refuses(monkeypatch):
    now = time.time()
    audited = AsyncMock()
    monkeypatch.setattr(control, 'kill_event', audited)
    monkeypatch.setattr(control, 'kill_state', AsyncMock(return_value=None))
    ordinary = advance(held_position(now), book(now, bid=49.0, ask=49.02), now)
    assert ordinary['exit_reason'] == 'stop'
    assert asyncio.run(paper_kill_audit.record_close(object(), 'p1', SYMBOL, ordinary, filled_by='observer')) is False
    assert asyncio.run(paper_kill_audit.record_close(object(), 'p1', SYMBOL, {'status': 'open'}, filled_by='observer')) is False
    audited.assert_not_awaited()
    orphan = advance(owed(now), book(now, bid=49.0, ask=49.02), now)
    with pytest.raises(ValueError, match='operator and reason'):
        asyncio.run(paper_kill_audit.record_close(object(), 'p1', SYMBOL, orphan, filled_by='observer'))
