import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const page = await importTs('src/components/activity/activityFormat.ts')
const row = await importTs('src/components/activity/rowFormat.ts')
const reconciliation = await importTs('src/components/ledger/reconciliation/reconciliationFormat.ts')

const WINDOW = { from: '2026-09-09T12:00:00.123456+00:00', to: '2026-09-16T12:00:00.654321+00:00' }

test('the address names a tab and a window, and anything else falls back rather than failing', () => {
  assert.deepEqual(page.TABS.map((tab) => tab.id), ['decisions', 'approvals', 'orders', 'alerts', 'outcomes'])
  for (const tab of page.TABS) assert.equal(page.tabFromParam(tab.id), tab.id)
  assert.equal(page.tabFromParam(null), 'decisions')
  assert.equal(page.tabFromParam('wallets'), 'decisions')

  assert.equal(page.windowDaysFromParam('14'), 14)
  assert.equal(page.windowDaysFromParam(null), 7)
  assert.equal(page.windowDaysFromParam('3'), 7)
  assert.equal(page.windowDaysFromParam('45'), 7)
  assert.equal(page.windowDaysFromParam('seven'), 7)
  assert.equal(page.windowDaysLabel(1), '1 day')
  assert.equal(page.windowDaysLabel(31), '31 days')
})

test('every window offered is one the export serves', () => {
  for (const days of page.WINDOW_DAYS) {
    assert.equal(reconciliation.exportDays(days), days)
    assert.ok(days <= reconciliation.EXPORT_MAX_DAYS)
  }
  assert.ok(page.WINDOW_DAYS.includes(page.DEFAULT_WINDOW_DAYS))
  assert.ok(page.PAGE_ROWS <= reconciliation.EXPORT_MAX_ROWS)
})

test('a failed request is never read as an empty result, and a failed refresh keeps the earlier reading', () => {
  assert.equal(page.readingState({ data: undefined, isError: false }), 'reading')
  assert.equal(page.readingState({ data: undefined, isError: true }), 'unanswered')
  assert.equal(page.readingState({ data: { rows: [] }, isError: false }), 'ready')
  assert.equal(page.readingState({ data: [], isError: false }), 'ready')
  assert.equal(page.readingState({ data: { rows: [] }, isError: true }), 'stale')
})

test('the empty, failed and earlier-reading messages say different things', () => {
  const empty = page.emptySectionText('orders', WINDOW)
  const failed = page.unansweredText('Not Found (HTTP 404)')
  const stale = page.staleText('Failed to fetch', '2026-09-16 12:00:00 UTC')
  assert.equal(empty, 'Nothing in this window: no order was recorded between 2026-09-09 12:00:00 UTC and 2026-09-16 12:00:00 UTC.')
  assert.match(failed, /not an empty result: Not Found \(HTTP 404\)$/)
  assert.match(stale, /^The latest refresh failed \(Failed to fetch\)\. What is shown is the earlier reading, taken 2026-09-16 12:00:00 UTC\.$/)
  assert.doesNotMatch(failed, /Nothing in this window/)
})

test('tab counts come only from what a reading holds, with a plus where it was capped', () => {
  assert.equal(page.sectionCount(undefined), null)
  assert.equal(page.sectionCount({ row_count: 0, truncated: false }), '0')
  assert.equal(page.sectionCount({ row_count: 3, truncated: false }), '3')
  assert.equal(page.sectionCount({ row_count: 200, truncated: true }), '200+')
  assert.equal(page.alertCount(undefined, 100), null)
  assert.equal(page.alertCount([], 100), '0')
  assert.equal(page.alertCount([{}, {}], 100), '2')
  assert.equal(page.alertCount(new Array(100).fill({}), 100), '100+')
})

test('a capped section says the window holds more, and never offers the probe row as a total', () => {
  assert.equal(page.heldText('decisions', { row_count: 1, truncated: false, row_cap: 200 }), '1 decision in this window.')
  assert.equal(page.heldText('outcomes', { row_count: 3, truncated: false, row_cap: 200 }), '3 outcomes in this window.')
  assert.equal(page.heldText('outcomes', { row_count: 200, truncated: true, row_cap: 200 }),
    'The newest 200 outcomes. This window holds more than the 200 shown here.')
  assert.equal(page.alertsHeldText(4, 100), '4 alerts: every alert the stream holds.')
  assert.equal(page.alertsHeldText(1, 100), '1 alert: every alert the stream holds.')
  assert.match(page.alertsHeldText(100, 100), /^The newest 100 alerts\. Any older alert/)
})

test('redactions are counted in words, and none is silence', () => {
  assert.equal(page.redactedText(0), null)
  assert.match(page.redactedText(1), /^1 field under a secret-looking key was replaced/)
  assert.match(page.redactedText(2), /^2 fields under a secret-looking key were replaced/)
})

test('an alert time in milliseconds reads as an exact UTC stamp, and no time is a dash', () => {
  assert.equal(page.msStamp(Date.UTC(2026, 8, 16, 12, 0, 5)), '2026-09-16 12:00:05 UTC')
  assert.equal(page.msStamp(0), '—')
  assert.equal(page.msStamp(undefined), '—')
  assert.equal(page.msStamp(Number.NaN), '—')
})

test('payload fields are read as stored, without guessing at another shape', () => {
  const plan = { symbol: ' BTC-PERP ', size_usd: 100, action: '', nested: { symbol: 'x' }, api_key: '[redacted]' }
  assert.equal(row.payloadText(plan, 'symbol'), 'BTC-PERP')
  assert.equal(row.payloadText(plan, 'size_usd'), '100')
  assert.equal(row.payloadText(plan, 'action'), null)
  assert.equal(row.payloadText(plan, 'nested'), null)
  assert.equal(row.payloadText(null, 'symbol'), null)
  assert.equal(row.payloadNumber(plan, 'size_usd'), 100)
  assert.equal(row.payloadNumber(plan, 'symbol'), null)
})

test('a decision shows the verdict and policy reason it stored, and a row without one says so', () => {
  assert.deepEqual(row.decisionVerdict({ allowed: true }), { text: 'Allowed', tone: 'good' })
  assert.deepEqual(row.decisionVerdict({ allowed: false }), { text: 'Blocked', tone: 'bad' })
  assert.deepEqual(row.decisionVerdict({ verdict: 'allow' }), { text: 'No verdict stored', tone: 'dim' })
  assert.deepEqual(row.decisionVerdict(null), { text: 'No verdict stored', tone: 'dim' })
  assert.equal(row.decisionReason({ reason_code: 'OK', reason: 'All risk checks passed' }), 'OK: All risk checks passed')
  assert.equal(row.decisionReason({ reason_code: 'COOLDOWN' }), 'COOLDOWN')
  assert.equal(row.decisionReason({ reason: 'Max open positions reached' }), 'Max open positions reached')
  assert.equal(row.decisionReason({}), '—')
})

test('order statuses are the ones the rows carry, each once, in the order first seen', () => {
  const statuses = ['rejected', 'placed', 'rejected', null, 'partially_filled'].map((status) => row.orderStatus(status).text)
  assert.deepEqual(row.distinct(statuses), ['Rejected', 'Placed', 'No status stored', 'Partially filled'])
  assert.equal(row.orderStatus('placed').tone, 'good')
  assert.equal(row.orderStatus('error').tone, 'bad')
  assert.equal(row.orderStatus('partially_filled').tone, 'plain')
  assert.deepEqual(row.distinct(['', undefined, 'Paper', 'Paper']), ['Paper'])
})

test('the paper flag and the boundary error read as stored', () => {
  assert.equal(row.orderMode(true), 'Paper')
  assert.equal(row.orderMode(false), 'Live')
  assert.equal(row.orderMode(null), '—')
  assert.equal(row.orderError({ error: { code: 'EXEC_DISABLED', message: 'Execution disabled' } }), 'EXEC_DISABLED: Execution disabled')
  assert.equal(row.orderError({ error: { message: 'Venue service returned 502' } }), 'Venue service returned 502')
  assert.equal(row.orderError({ error: 'boundary unreachable' }), 'boundary unreachable')
  assert.equal(row.orderError({ error: null, ok: true }), null)
  assert.equal(row.orderError(null), null)
})

test('an approval is consumed or not, which is all an envelope row can say', () => {
  assert.equal(row.approvalState('2026-09-16T12:00:00+00:00'), 'Consumed')
  assert.equal(row.approvalState(null), 'Not consumed')
})

test('outcome statuses read in words', () => {
  assert.deepEqual(row.outcomeStatus('measured'), { text: 'Measured', tone: 'plain' })
  assert.deepEqual(row.outcomeStatus('pending'), { text: 'Pending', tone: 'warn' })
  assert.deepEqual(row.outcomeStatus('insufficient_candles'), { text: 'Insufficient candles', tone: 'dim' })
})

test('a measured percentage is shown as state-api sent it, never rescaled, and a missing one is a dash', () => {
  assert.equal(row.percentText(0.5), '+0.500%')
  assert.equal(row.percentText(-1.5), '−1.500%')
  assert.equal(row.percentText(0), '0.000%')
  assert.equal(row.percentText(null), '—')
  assert.equal(row.percentText(Number.NaN), '—')
})

test('prices, sizes and horizons are formatted and never recomputed', () => {
  assert.equal(row.priceText(77944.5), '77,944.5')
  assert.equal(row.priceText(0.003695), '0.003695')
  assert.equal(row.priceRangeText(100.25, 101), '100.25 → 101')
  assert.equal(row.priceRangeText(null, null), '—')
  assert.equal(row.usdText(1234.567), '1,234.57 USD')
  assert.equal(row.usdText(undefined), '—')
  assert.equal(row.horizonText(240), '240 min')
})

test('identifiers and digests are shortened for a cell only when they are long', () => {
  assert.equal(row.shortId('3f2a9c1e-77aa-4c1b-9d7e-0123456789ab'), '3f2a9c1e…')
  assert.equal(row.shortId('a'.repeat(64), 12), `${'a'.repeat(12)}…`)
  assert.equal(row.shortId('o1'), 'o1')
  assert.equal(row.shortId(null), '—')
})

test('market alerts name their metric and change in words', () => {
  assert.equal(row.alertMetric('oi'), 'Open interest')
  assert.equal(row.alertMetric('funding'), 'Funding')
  assert.equal(row.alertMetric('market_condition'), 'Market condition')
  assert.equal(row.alertType('regime_change'), 'Regime change')
  assert.equal(row.alertChange('neutral', 'extreme_positive'), 'neutral → extreme positive')
  assert.equal(row.alertChange(undefined, 'strong_trend'), 'strong trend')
})
