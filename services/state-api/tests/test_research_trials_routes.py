"""Registration and evaluation of research trials through the API."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json
import uuid

from fastapi.testclient import TestClient

from app.main import app, state
from tradesync_core import research_trial as v1
from tradesync_core import research_trial_v2 as v2
from tradesync_core import research_trials as registry

client = TestClient(app)
UNIVERSE = ['BTC-PERP', 'ETH-PERP', 'HYPE-PERP']


def pool(conn):
    @asynccontextmanager
    async def acquire(): yield conn
    return MagicMock(acquire=acquire)


def trial_row(spec, registered_at=None):
    return {'id': uuid.uuid4(), 'registered_at': registered_at or datetime.now(timezone.utc),
            'specification': json.dumps(spec), 'specification_sha256': registry.fingerprint(spec)}


def universe(symbols=UNIVERSE):
    return patch('app.research_trials.editions.tracked_symbols', AsyncMock(return_value=symbols))


def test_registration_freezes_the_universe_the_api_reported():
    spec = v2.specification('scalp', UNIVERSE)
    conn = MagicMock(fetchval=AsyncMock(return_value=uuid.uuid4()), fetchrow=AsyncMock(return_value=trial_row(spec)),
                     execute=AsyncMock(), transaction=MagicMock(return_value=AsyncMock()))
    with patch.object(state, 'pool', pool(conn)), universe():
        result = client.post('/state/research-trials', json={'style': 'scalp'})
    assert result.status_code == 200
    body = result.json()
    assert body['version'] == 'research-trial-v2'
    assert body['specification']['universe'] == UNIVERSE
    assert body['duplicate'] is False and body['authority'] == 'research_only'
    # The stored specification is the one that was fingerprinted.
    stored = json.loads(conn.fetchval.await_args.args[2])
    assert stored['universe'] == UNIVERSE and stored['schema'] == 'research-trial-v2'


def test_a_universe_that_cannot_be_read_registers_nothing():
    conn = MagicMock(fetchval=AsyncMock(), fetchrow=AsyncMock())
    with patch.object(state, 'pool', pool(conn)), universe([]):
        result = client.post('/state/research-trials', json={'style': 'scalp'})
    assert result.status_code == 409
    assert 'universe' in result.json()['detail']
    conn.fetchval.assert_not_awaited()


def test_the_frozen_v1_protocol_is_no_longer_offered_for_new_registrations():
    conn = MagicMock(fetchval=AsyncMock(), fetchrow=AsyncMock())
    with patch.object(state, 'pool', pool(conn)), universe():
        result = client.post('/state/research-trials', json={'style': 'scalp', 'version': 'research-trial-v1'})
    assert result.status_code == 409
    assert 'research-trial-v2' in result.json()['detail']
    conn.fetchval.assert_not_awaited()


def test_the_listing_says_which_version_each_trial_uses():
    rows = [trial_row(v2.specification('swing', UNIVERSE)), trial_row(v1.specification('scalp'))]
    conn = MagicMock(fetch=AsyncMock(return_value=rows))
    with patch.object(state, 'pool', pool(conn)):
        body = client.get('/state/research-trials').json()
    assert [trial['version'] for trial in body['trials']] == ['research-trial-v2', 'research-trial-v1']
    assert body['registerable_version'] == 'research-trial-v2'
    assert body['versions'] == ['research-trial-v1', 'research-trial-v2']


def test_each_trial_is_evaluated_by_the_evaluator_of_its_own_version():
    for spec, expected in ((v2.specification('scalp', UNIVERSE), 'research-trial-v2'),
                           (v1.specification('scalp'), 'research-trial-v1')):
        row = trial_row(spec)
        conn = MagicMock(fetchrow=AsyncMock(return_value=row), fetch=AsyncMock(return_value=[]))
        with patch.object(state, 'pool', pool(conn)):
            body = client.get(f"/state/research-trials/{row['id']}/evaluation").json()
        assert body['version'] == body['schema'] == expected
        assert body['state'] == 'collecting' and body['promotion_allowed'] is False


def test_a_v2_evaluation_reads_the_stored_evidence_digest():
    """The digest column is selected, so a rewritten document cannot pass as evidence."""
    row = trial_row(v2.specification('scalp', UNIVERSE))
    conn = MagicMock(fetchrow=AsyncMock(return_value=row), fetch=AsyncMock(return_value=[]))
    with patch.object(state, 'pool', pool(conn)):
        client.get(f"/state/research-trials/{row['id']}/evaluation")
    assert 'evidence_sha256' in conn.fetch.await_args.args[0]


def test_an_altered_specification_fails_before_any_position_is_read():
    row = trial_row(v2.specification('scalp', UNIVERSE))
    row['specification_sha256'] = 'wrong'
    conn = MagicMock(fetchrow=AsyncMock(return_value=row), fetch=AsyncMock())
    with patch.object(state, 'pool', pool(conn)):
        result = client.get(f"/state/research-trials/{row['id']}/evaluation")
    assert result.status_code == 409
    conn.fetch.assert_not_awaited()


def test_an_unknown_stored_version_is_refused_rather_than_guessed():
    spec = {'schema': 'research-trial-v9', 'style': 'scalp'}
    row = trial_row(spec)
    conn = MagicMock(fetchrow=AsyncMock(return_value=row), fetch=AsyncMock())
    with patch.object(state, 'pool', pool(conn)):
        result = client.get(f"/state/research-trials/{row['id']}/evaluation")
    assert result.status_code == 409
    conn.fetch.assert_not_awaited()
