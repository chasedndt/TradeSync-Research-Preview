import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { importTs } from './support/importTs.mjs'

const {
  atSeconds,
  conditionLine,
  conditionMark,
  conditionTone,
  conditionsCount,
  fitTone,
  fitWords,
  isFixedPlan,
  openedLine,
  priceWords,
  ratioWords,
  readLine,
  shortDigest,
  stateTone,
  usdcWords,
} = await importTs('src/components/opportunity/brief/briefText.ts')

const OPENED = Date.UTC(2026, 8, 16, 12, 0, 0) / 1000

test('every regime fit reads as words with an honest tone', () => {
  assert.equal(fitWords('with'), 'With the regime')
  assert.equal(fitWords('against'), 'Against the regime')
  assert.equal(fitWords('flat'), 'Regime flat')
  assert.equal(fitWords('unlabelled'), 'Regime not labelled')
  assert.equal(fitTone('with'), 'good')
  assert.equal(fitTone('against'), 'warn')
  assert.equal(fitTone('unlabelled'), 'dim')
})

test('a condition shows the stored value beside what it needed, in its own unit', () => {
  const coverage = { label: 'Evidence coverage', measured: 0.55, required: 0.3, comparator: '>=', unit: 'share', met: true }
  assert.equal(conditionLine(coverage), 'Evidence coverage 0.55, needing at least 0.30')
  const age = { label: 'Oldest contributing reading', measured: 1000, required: 120000, comparator: '<=', unit: 'ms', met: true }
  assert.equal(conditionLine(age), 'Oldest contributing reading 1s, needing at most 2m')
  const missing = { label: 'Directional coverage', measured: null, required: 0.5, comparator: '>=', unit: 'share', met: null }
  assert.equal(conditionLine(missing), 'Directional coverage not stored, needing at least 0.50')
})

test('met, not met and not stored are three different things', () => {
  assert.deepEqual([conditionTone(true), conditionTone(false), conditionTone(null)], ['good', 'bad', 'dim'])
  assert.deepEqual([conditionMark(true), conditionMark(false), conditionMark(null)], ['met', 'not met', 'not stored'])
})

test('a plan has levels only when a paper position was opened', () => {
  assert.equal(isFixedPlan({ status: 'none' }), false)
  assert.equal(isFixedPlan({ status: 'open' }), true)
  assert.equal(isFixedPlan({ status: 'closed' }), true)
})

test('times are the exact moments they name, and the age is the one the brief was read at', () => {
  assert.equal(atSeconds(OPENED), '2026-09-16 12:00:00 UTC')
  assert.equal(atSeconds(null), 'unknown')
  assert.equal(openedLine(OPENED, 200), 'Opened 2026-09-16 12:00:00 UTC · 3m 20s old')
  assert.equal(openedLine(null, null), 'Opening time not stored')
  assert.equal(readLine(OPENED + 5), 'Read 2026-09-16 12:00:05 UTC')
})

test('figures read as stored, with a dash for anything missing', () => {
  assert.equal(priceWords(64250.5), '64,250.5')
  assert.equal(priceWords(98), '98.00')
  assert.equal(priceWords(0.0123456), '0.01235')
  assert.equal(priceWords(null), '—')
  assert.equal(usdcWords(4.4), '4.40 USDC')
  assert.equal(ratioWords(1.7273), '1.73 to 1')
  assert.equal(ratioWords(null), '—')
  assert.equal(shortDigest('abcdef0123456789'), 'abcdef012345')
  assert.equal(shortDigest(null), 'not stored')
})

test('the paper state tone never reads a pause, an unknown or live execution as good', () => {
  const base = { position: 'none', entries_paused: false, execution_enabled: false, label: 'Open to a paper entry' }
  assert.equal(stateTone(base), 'good')
  assert.equal(stateTone({ ...base, entries_paused: true, label: 'Paper entries paused' }), 'warn')
  assert.equal(stateTone({ ...base, entries_paused: null, label: 'Paper entry state unknown' }), 'warn')
  assert.equal(stateTone({ ...base, label: 'Paper research only' }), 'dim')
  assert.equal(stateTone({ ...base, position: 'open', label: 'Paper position open' }), 'good')
  assert.equal(stateTone({ ...base, execution_enabled: true }), 'bad')
})

test('the conditions count says when an older opportunity stored none', () => {
  assert.equal(conditionsCount({ schema: 'paper_signal_v1', conditions_met: 4, conditions_checked: 4 }), '4 of 4 conditions met')
  assert.equal(conditionsCount({ schema: 'legacy', conditions_met: 0, conditions_checked: 0 }), 'Conditions not stored')
})

test('the brief wording derives nothing: no maths beyond units', async () => {
  const source = await readFile(new URL('../src/components/opportunity/brief/briefText.ts', import.meta.url), 'utf8')
  // Scaling seconds to milliseconds is a unit; tanh, logs, square roots and averages would be a calculation.
  assert.ok(!/Math\.(tanh|log|sqrt|exp|pow|abs|max|min)\b/.test(source), 'briefText must not calculate')
})
