import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const format = await importTs('src/components/ledger/reconciliation/reconciliationFormat.ts')

const execution = (over = {}) => ({
  window_hours: 24, decisions: 0, orders: 0, matched: 0, divergences: [], orders_outside_window: [], clean: true,
  summary: '0 of 0 decisions reconciled with no divergence', paper_mode: true, execution_gate_open: false, note: '', ...over,
})

test('a view that compared nothing reads as nothing compared, never as clean', () => {
  assert.deepEqual(format.viewStatus({ considered: 0, findings: [] }), { text: 'Nothing compared', tone: 'dim' })
  assert.deepEqual(format.viewStatus({ considered: 3, findings: [] }), { text: 'Clean', tone: 'good' })
  assert.deepEqual(format.viewStatus({ considered: 3, findings: [{}] }), { text: '1 finding', tone: 'warn' })
  assert.deepEqual(format.viewStatus({ considered: 3, findings: [{}, {}] }), { text: '2 findings', tone: 'warn' })
})

test('a view window reads as exact UTC times at both ends, including the microseconds state-api sends', () => {
  assert.equal(format.windowText('2026-09-15T12:00:00+00:00 to 2026-09-16T12:00:00+00:00 (24h)'),
    '2026-09-15 12:00:00 UTC to 2026-09-16 12:00:00 UTC (24h)')
  assert.equal(format.windowText('2026-09-15T12:00:00.123456+00:00 to 2026-09-16T12:00:00.654321+00:00 (24h)'),
    '2026-09-15 12:00:00 UTC to 2026-09-16 12:00:00 UTC (24h)')
  assert.equal(format.utcStamp('2026-09-16T08:30:05.987654+00:00'), '2026-09-16 08:30:05 UTC')
  assert.equal(format.windowText('the 24h before the reading'), 'the 24h before the reading')
})

test('the execution reconciliation sits beside the views, and an empty one is not called clean', () => {
  // That route answers clean: true over zero decisions and zero orders. The card must not.
  const view = format.executionAsView(execution(), Date.UTC(2026, 8, 16, 12, 0, 0))
  assert.equal(view.name, 'decisions_against_orders')
  assert.equal(view.considered, 0)
  assert.equal(format.viewStatus(view).text, 'Nothing compared')
  assert.match(view.window, /the 24h before the reading received 2026-09-16 12:00:00 UTC/)
})

test('an execution divergence keeps its field, its subject and the counterparts outside the window', () => {
  const view = format.executionAsView(execution({
    window_hours: 6, decisions: 1, orders: 1, matched: 1, clean: false, orders_outside_window: ['d0'],
    divergences: [{ kind: 'field_mismatch', decision_id: 'd1', order_id: 'o1', field: 'side', expected: 'long', actual: 'short',
      detail: 'recorded intent and recorded action disagree on side' }],
  }), Date.UTC(2026, 8, 16))
  assert.equal(view.considered, 2)
  assert.equal(view.findings[0].subject_id, 'd1')
  assert.match(view.findings[0].detail, /\(side\)$/)
  assert.deepEqual(view.outside_window, ['d0'])
  assert.equal(format.viewStatus(view).text, '1 finding')
})

test('a reading received at no known time says so rather than inventing one', () => {
  assert.match(format.executionAsView(execution(), 0).window, /received —$/)
})

test('views and findings are named in words', () => {
  assert.equal(format.viewTitle('orphaned_events'), 'Orphaned events')
  assert.equal(format.viewTitle('decisions_against_orders'), 'Decisions against orders')
  assert.equal(format.viewTitle('something_new'), 'Something new')
  assert.equal(format.findingLabel('duplicate_evidence_digest'), 'Duplicate evidence digest')
})

test('a missing measure is a dash, and a real zero still reads as zero', () => {
  assert.equal(format.ratioText(null), '—')
  assert.equal(format.ratioText(undefined), '—')
  assert.equal(format.ratioText(Number.NaN), '—')
  assert.equal(format.ratioText(0), '0.0%')
  assert.equal(format.ratioText(0.6), '60.0%')
})

test('abstentions are counted by reason', () => {
  assert.equal(format.abstentionText({}), 'none abstained')
  assert.equal(format.abstentionText({ undeclared: 12, unlabelled: 3 }),
    'abstained: 12 no expectation declared by the rulebook, 3 no entry regime labelled')
})

test('departures read as what went wrong, not as the name of the check that failed', () => {
  assert.equal(format.departureText(['stop_respected', 'time_respected']), 'stop passed without the stop firing; held past its expiry')
  assert.equal(format.departureText(['a_new_check']), 'A new check')
})

test('the export stays inside its bounds and names only real sections', () => {
  assert.equal(format.exportDays(0), 1)
  assert.equal(format.exportDays(45), 31)
  assert.equal(format.exportDays(7.4), 7)
  assert.equal(format.exportDays(Number.NaN), 7)
  assert.equal(format.exportUrl('/api', 'json', 90), '/api/state/audit/export?days=31')
  assert.equal(format.exportUrl('/api', 'csv', 7, 'orders'), '/api/state/audit/export.csv?section=orders&days=7')
  assert.equal(format.exportUrl('/api', 'csv', 7, 'wallets'), null)
  assert.equal(format.exportUrl('/api', 'csv', 7), null)
  assert.deepEqual([...format.EXPORT_SECTIONS], ['decisions', 'approvals', 'orders', 'outcomes'])
})

test('window choices read as hours and days', () => {
  assert.equal(format.windowChoiceLabel(1), '1 hour')
  assert.equal(format.windowChoiceLabel(6), '6 hours')
  assert.equal(format.windowChoiceLabel(24), '1 day')
  assert.equal(format.windowChoiceLabel(720), '30 days')
})
