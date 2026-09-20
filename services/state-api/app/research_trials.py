"""Immutable research-trial registration and its forward evaluation.

The registry freezes a protocol and reports on the cohort it admits; the paper
module opens, observes and closes positions. Nothing here can open one.

Registration freezes the symbol universe **as market-data reports it**, so a
trial's population cannot drift when the configured universe changes, and a
universe that cannot be read registers nothing at all. Which version a trial uses
is carried on every answer: the listing, the registration and the evaluation.
v1 stays evaluable for anything registered under it and is no longer offered for
new registrations (``tradesync_core.research_trials``).

Registration starts no job, opens no position and changes no weight.
"""
import asyncio
import time
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app import editions
from app.managed_paper import decode, serial
from tradesync_core import research_trials as registry


class TrialRequest(BaseModel):
    style: str = Field(pattern='^(scalp|intraday|swing)$')
    version: str = Field(default=registry.LATEST, max_length=64)


def register(app, state, *, market_data_url):
    def pool():
        if state.pool is None: raise HTTPException(503, 'Paper-position database unavailable')
        return state.pool

    def described(row):
        spec = decode(row['specification'])
        return {**dict(row), 'specification': spec, 'version': spec.get('schema') if isinstance(spec, dict) else None}

    @app.get('/state/research-trials')
    async def trials():
        async with pool().acquire() as conn:
            rows = await conn.fetch('SELECT * FROM research_trials ORDER BY registered_at DESC LIMIT 100')
        return {'trials':[described(r) for r in rows],
                'registerable_version': registry.LATEST, 'versions': list(registry.VERSIONS),
                'authority':'research_only', 'note':'Registration freezes a protocol; it does not start a job or open a position. Results require later entries and resolved outcomes.'}

    @app.get('/state/research-trials/{identity}/evaluation')
    async def trial_evaluation(identity: uuid.UUID):
        async with pool().acquire() as conn:
            trial = await conn.fetchrow('SELECT * FROM research_trials WHERE id=$1', identity)
            if trial is None:
                raise HTTPException(404, 'Research trial not found')
            spec = decode(trial['specification'])
            if registry.fingerprint(spec) != trial['specification_sha256']:
                raise HTTPException(409, 'Stored specification fingerprint mismatch')
            try:
                version = registry.version_of(spec)
            except ValueError as exc:
                raise HTTPException(409, str(exc))
            rows = await conn.fetch('SELECT id,symbol,entry_evidence,evidence_sha256,position_state FROM managed_paper_positions WHERE created_at >= $1 ORDER BY created_at,id LIMIT 10001', trial['registered_at'])
        if len(rows) > 10000:
            return {'state':'incomplete_record_window', 'version':version, 'promotion_allowed':False,
                    'note':'More than 10000 candidate records; evaluation refused rather than silently truncating outcomes.'}
        records = [{**dict(r), 'id':str(r['id']), 'entry_evidence':decode(r['entry_evidence']), 'position_state':decode(r['position_state'])} for r in rows]
        try:
            # Verifying each stored evidence digest is real work; it stays off the event loop.
            result = await asyncio.to_thread(registry.evaluate, spec, trial['registered_at'].timestamp(), time.time(), records)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {'trial_id':str(identity), 'specification_sha256':trial['specification_sha256'],
                'version':version, 'records_considered':len(records), **result}

    @app.post('/state/research-trials')
    async def register_trial(body: TrialRequest):
        # The universe is read from the API and frozen into the specification. An
        # unreadable universe registers nothing rather than a trial over no markets.
        symbols = await editions.tracked_symbols(market_data_url)
        try:
            spec = registry.specification(body.style, version=body.version, symbols=symbols)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        digest = registry.fingerprint(spec)
        async with pool().acquire() as conn:
            async with conn.transaction():
                inserted = await conn.fetchval('INSERT INTO research_trials(id,specification,specification_sha256) VALUES($1,$2::jsonb,$3) ON CONFLICT(specification_sha256) DO NOTHING RETURNING id', uuid.uuid4(), serial(spec), digest)
                row = await conn.fetchrow('SELECT * FROM research_trials WHERE specification_sha256=$1', digest)
        return {**described(row), 'duplicate':inserted is None,
                'authority':'research_only', 'note':'No trade, schedule, source weight or execution permission changed.'}
