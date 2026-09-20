import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { bps, byStrength, chance, count, heldOut, horizon, polarity, ratio, rule, sampleState, verdict } =
  await importTs('src/components/ledger/comparison/comparisonFormat.ts')

const cell = (over = {}) => ({
  label: 'Resting liquidity balance near price', sign: 1, threshold: 0.2,
  sample_state: 'measured', tested: true, selects: false, economic: null,
  held_out: null, holdout_measured: 0, z: null, ...over,
})

test('returns read in basis points, the unit the paper panels use', () => {
  assert.equal(bps(0.88), '88.0 bps')
  assert.equal(bps(-0.32), '-32.0 bps')
  assert.equal(bps(null), '—')
  assert.equal(bps(undefined), '—')
  assert.equal(bps(Number.NaN), '—')
})

test('counts, ratios and chances keep their own precision', () => {
  assert.equal(count(1234), '1,234')
  assert.equal(count(null), '—')
  assert.equal(ratio(2.345), '2.35')
  assert.equal(chance(0.0004), '<0.001')
  assert.equal(chance(0.0125), '0.013')
  assert.equal(chance(null), '—')
})

test('horizons and polarities read as words', () => {
  assert.equal(horizon(15), '15 min')
  assert.equal(horizon(60), '1 h')
  assert.equal(horizon(240), '4 h')
  assert.equal(polarity('inverted'), 'inverted')
  assert.equal(polarity('as_read'), 'as read')
})

test('the rule a cell applied is stated in full, inverted cells included', () => {
  assert.equal(rule(cell()), 'kept when resting liquidity balance near price is at least 0.20')
  assert.equal(rule(cell({ sign: -1 })), 'kept when resting liquidity balance near price, inverted, is at least 0.20')
})

test('a cell that was never tested does not read as a negative result', () => {
  assert.equal(verdict(cell({ tested: false, sample_state: 'no_context' })), 'not tested · no reading in this population')
  assert.equal(
    verdict(cell({ tested: false, sample_state: 'too_few_independent_windows' })),
    'not tested · too few independent windows',
  )
  assert.equal(sampleState('one_sided'), 'every call fell on one side of the threshold')
  assert.equal(sampleState('something_new'), 'something new')
})

test('selection and making money are never collapsed into one verdict', () => {
  assert.equal(verdict(cell()), 'no selection at the family bar')
  assert.equal(verdict(cell({ selects: true, economic: false })), 'selects, still negative after costs')
  assert.equal(verdict(cell({ selects: true, economic: true })), 'selects, and positive after costs')
})

test('the hold-out says what it held on, or nothing at all', () => {
  assert.equal(heldOut(cell()), '—')
  assert.equal(heldOut(cell({ held_out: true, holdout_measured: 30 })), 'held on 30')
  assert.equal(heldOut(cell({ held_out: false, holdout_measured: 12 })), 'did not hold on 12')
})

test('tested cells come first, strongest first, so the best the family managed is visible', () => {
  const rows = [
    cell({ label: 'weak', z: 0.4 }),
    cell({ label: 'untested', tested: false, z: null }),
    cell({ label: 'strong', z: 2.9 }),
  ]
  assert.deepEqual(byStrength(rows).map((row) => row.label), ['strong', 'weak', 'untested'])
  // The input is not reordered in place.
  assert.equal(rows[0].label, 'weak')
})
