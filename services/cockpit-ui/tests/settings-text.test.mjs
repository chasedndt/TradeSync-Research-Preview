import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const {
  CACHED_STATE_KEYS,
  executorLine,
  fetchCensus,
  killLine,
  retentionLine,
  signerLine,
  timezoneLine,
} = await importTs('src/components/settings/settingsText.ts')

test('the kill switch reads engaged, clear, missing or unknown, never guessed', () => {
  const engaged = killLine({ active: true, operator: 'Chase', reason: 'venue outage', changed_at: '2026-09-16T12:00:00Z' })
  assert.equal(engaged.label, 'Engaged')
  assert.equal(engaged.tone, 'bad')
  assert.match(engaged.detail, /Engaged by Chase at 2026-09-16 12:00:00 UTC: venue outage/)
  assert.equal(killLine({ active: false, operator: 'Chase', reason: 'resumed', changed_at: '2026-09-16T12:00:00Z' }).tone, 'good')
  assert.equal(killLine(null).label, 'Not recorded')
  assert.equal(killLine(undefined).label, 'Checking')
  assert.equal(killLine(undefined, true).label, 'Unknown')
})

test('the executor is described from the circuit state the API reports', () => {
  assert.equal(executorLine(undefined).label, 'Not reported')
  assert.equal(executorLine({ venue: 'hyperliquid', circuit_open: 'unknown' }).label, 'Not running')
  const responding = executorLine({ venue: 'hyperliquid', circuit_open: false })
  assert.equal(responding.label, 'Responding')
  assert.match(responding.detail, /EXECUTION_ENABLED/)
  assert.equal(executorLine({ venue: 'hyperliquid', circuit_open: true, error: 'tripped' }).detail, 'tripped')
})

test('an unreachable signer is the expected state, and a running one is flagged', () => {
  const offline = signerLine({ reachable: false, status: 'offline' })
  assert.equal(offline.label, 'Not running')
  assert.equal(offline.tone, 'good')
  assert.match(offline.detail, /deliberate operator act/)
  const running = signerLine({ reachable: true, available: true, status: 'ready' })
  assert.equal(running.tone, 'warn')
  assert.match(running.detail, /reports "ready" and says it is available/)
  assert.equal(signerLine(undefined, true).label, 'Unknown')
})

test('retention says how long and in what detail', () => {
  assert.equal(
    retentionLine({ kept_days: 90, full_detail_days: 3, downsampled_to_minutes: 15 }),
    '90 days: every minute for 3 days, then one per 15 minutes',
  )
  assert.equal(retentionLine({ kept_days: 180, full_detail_days: null, downsampled_to_minutes: null }), '180 days')
})

test('the Cockpit counts its own readings honestly', () => {
  assert.equal(fetchCensus(0, 0).label, 'Nothing read yet')
  assert.equal(fetchCensus(12, 0).tone, 'good')
  const failing = fetchCensus(12, 2)
  assert.equal(failing.label, '2 failing')
  assert.equal(failing.detail, '2 of 12 readings failed their last request.')
})

test('the timezone is the browser\'s own report, and clearing touches browser caches only', () => {
  assert.equal(timezoneLine('Europe/London'), 'This browser reports its timezone as Europe/London.')
  assert.equal(timezoneLine(undefined), 'This browser did not report a timezone.')
  assert.deepEqual([...CACHED_STATE_KEYS], ['tradesync_preview_cache', 'tradesync_execution_cache'])
})
