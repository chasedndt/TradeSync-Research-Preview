import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const text = await importTs('src/components/harness/harnessControlText.ts')

const STOP_COMMAND =
  'wsl.exe -d Ubuntu --cd /home/operator/runtimes/hermes-home -- env HERMES_HOME=/home/operator/runtimes/hermes-home ' +
  '/home/operator/runtimes/hermes-home/hermes-agent/venv/bin/hermes gateway stop'
const base = {
  schema_version: 'agent_harness_control_v1',
  generated_at: '2026-09-15T18:30:00+00:00',
  desired: { state: 'running', operator: 'migration 034', reason: 'installed', requested_at: '2026-09-15T18:00:00+00:00', command_id: null },
  host: { status: 'none', command_id: null, claimed_at: null, result: null, last_poll_at: null, seconds_since_poll: null, poll_interval_s: 10 },
  gateway: { status: 'live', last_seen_at: '2026-09-15T18:29:55+00:00', seconds_since_seen: 5, last_error: null, consecutive_failures: 0 },
  gate: { open: true, reason: null },
  agreement: { state: 'agree', message: 'Running; the gateway answers.' },
  history: [],
  note: '',
}
const control = (patch) => ({ ...base, ...patch })
const result = (status, extra = {}) => ({
  command_id: 'c1', status, command: STOP_COMMAND, exit_status: 0, is_active: 'inactive', detail: 'the gateway is stopped',
  at: '2026-09-15T18:21:00+00:00', for_current_command: true, ...extra,
})
const stoppedDesired = { ...base.desired, state: 'stopped', operator: 'chase', reason: 'Maintenance window', command_id: 'c1' }

test('the header reads running with Stop, and stopping, stopped or failed with Start', () => {
  assert.deepEqual(text.switchView(control({})), { label: 'running', tone: 'good', action: 'stop', warning: null })
  const pending = { ...base.host, status: 'pending', command_id: 'c1' }
  assert.deepEqual(text.switchView(control({ desired: stoppedDesired, host: pending, agreement: { state: 'pending', message: 'Stop requested' } })),
    { label: 'stopping…', tone: 'warn', action: 'start', warning: null })
  const applied = { ...pending, status: 'applied', result: result('applied') }
  assert.deepEqual(text.switchView(control({ desired: stoppedDesired, host: applied, agreement: { state: 'agree', message: 'Stopped' } })),
    { label: 'stopped', tone: 'bad', action: 'start', warning: null })
  const failed = control({ desired: stoppedDesired, host: { ...pending, status: 'failed', result: result('failed') },
    agreement: { state: 'disagree', message: 'Stop failed at 2026-09-15 18:21:00 UTC' } })
  assert.deepEqual(text.switchView(failed), { label: 'stop failed', tone: 'bad', action: 'start', warning: 'Stop failed at 2026-09-15 18:21:00 UTC' })
  const answering = control({ desired: stoppedDesired, host: applied, agreement: { state: 'disagree', message: 'Stopped, but the gateway answered' } })
  assert.deepEqual(text.switchView(answering), { label: 'stopped', tone: 'bad', action: 'start', warning: 'Stopped, but the gateway answered' })
  const down = control({ agreement: { state: 'disagree', message: 'Running is requested, but the gateway has not answered' } })
  assert.deepEqual(text.switchView(down), { label: 'running', tone: 'warn', action: 'stop', warning: 'Running is requested, but the gateway has not answered' })
  const starting = control({ host: { ...pending, status: 'applying' }, agreement: { state: 'pending', message: 'Starting' } })
  assert.deepEqual(text.switchView(starting), { label: 'starting…', tone: 'warn', action: 'stop', warning: null })
})

test('without an answer from the State API the switch offers no action', () => {
  assert.deepEqual(text.switchView(undefined, false), { label: 'checking', tone: 'dim', action: null, warning: null })
  const unavailable = text.switchView(undefined, true)
  assert.equal(unavailable.label, 'unavailable')
  assert.equal(unavailable.action, null)
  assert.match(unavailable.warning, /cannot be read/)
})

test('a change needs a name and a reason of 5 to 240 characters', () => {
  assert.equal(text.canSubmit('chase', 'Maintenance window'), true)
  assert.equal(text.canSubmit('  ', 'Maintenance window'), false)
  assert.equal(text.canSubmit('chase', ' ok  '), false)
  assert.equal(text.canSubmit('chase', 'x'.repeat(241)), false)
  assert.equal(text.canSubmit('c'.repeat(81), 'Maintenance window'), false)
  assert.equal(text.desiredFor('stop'), 'stopped')
  assert.equal(text.desiredFor('start'), 'running')
})

test('the stop confirmation says plainly what stops and what continues', () => {
  const copy = text.CHANGE_COPY.stop
  const words = [copy.lead, ...copy.points, copy.after].join(' ')
  for (const phrase of ['stops the Hermes gateway', 'hermes gateway stop', 'every Hermes cron job stops', 'StrikeZone', 'Community Server',
    'Discord bots go offline', "TradeSync's Hermes readings", "core-scorer's claim reading", 'Paper trading and market data continue',
    'ChaseOS coordination daemon is separate']) {
    assert.ok(words.includes(phrase), phrase)
  }
  assert.equal(copy.confirmLabel, 'Stop agent harness')
  assert.match(text.CHANGE_COPY.start.lead, /logon script/)
  assert.match(text.SCOPE_NOTE, /never touches it/)
})

test('host, gateway and history lines say what happened, with exact times', () => {
  assert.equal(text.commandName(STOP_COMMAND), 'hermes gateway stop')
  assert.equal(text.commandName('wsl.exe -d Ubuntu -- systemctl --user start hermes-gateway.service'), 'systemctl --user start hermes-gateway')
  assert.equal(text.commandName(null), '—')
  assert.equal(text.hostLine(base.host), 'No stop or start has been requested from TradeSync.')
  assert.equal(text.hostLine({ ...base.host, status: 'pending' }), 'Waiting for the host control process; it has not checked in since the State API started.')
  assert.equal(text.hostLine({ ...base.host, status: 'pending', seconds_since_poll: 4 }), 'Waiting for the host control process (last checked in 4s ago).')
  assert.equal(text.hostLine({ ...base.host, status: 'applying', claimed_at: '2026-09-15T18:20:07+00:00' }), 'Applying since 2026-09-15 18:20:07 UTC.')
  assert.equal(text.hostLine({ ...base.host, status: 'applied', result: result('applied') }),
    'Applied 2026-09-15 18:21:00 UTC · hermes gateway stop · exit 0 · systemd inactive')
  assert.equal(text.gatewayLine(base.gateway), 'Answering · last answer 5s ago')
  assert.equal(text.gatewayLine({ ...base.gateway, status: 'offline' }), 'Not answering since 2026-09-15 18:29:55 UTC')
  assert.equal(text.gatewayLine({ ...base.gateway, status: 'offline', last_seen_at: null }), 'Not answering since the State API started')
  assert.equal(text.gatewayLine({ ...base.gateway, status: 'not_configured' }), 'Not configured in TradeSync (AGENT_HARNESS_URL is unset).')
  assert.equal(text.requestLine(stoppedDesired), 'Stopped · by chase at 2026-09-15 18:00:00 UTC')
  const requested = {
    id: 'e1', created_at: '2026-09-15T18:20:00+00:00', kind: 'requested', command_id: 'c1', desired_state: 'stopped', previous_state: 'running',
    operator: 'chase', reason: 'Maintenance window', command: null, exit_status: null, is_active: null, detail: null,
  }
  assert.deepEqual(text.eventLine(requested), { title: 'Stop requested by chase', detail: 'Maintenance window' })
  assert.deepEqual(text.eventLine({ ...requested, kind: 'applying', operator: null, reason: null }), { title: 'Stop taken up by the host control process', detail: '' })
  assert.deepEqual(
    text.eventLine({ ...requested, kind: 'applied', operator: null, reason: null, command: STOP_COMMAND, exit_status: 0, is_active: 'inactive', detail: 'the gateway is stopped' }),
    { title: 'Stopped by the host control process', detail: 'hermes gateway stop · exit 0 · systemd inactive · the gateway is stopped' },
  )
  assert.equal(text.eventLine({ ...requested, kind: 'failed', desired_state: 'running' }).title, 'Start failed')
  assert.equal(text.agreementTone('disagree'), 'bad')
  assert.equal(text.agreementTone('pending'), 'warn')
  assert.equal(text.utcStamp('2026-09-15T18:20:00+00:00'), '2026-09-15 18:20:00 UTC')
})
