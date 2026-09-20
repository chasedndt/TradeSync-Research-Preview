import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const {
  ageWords,
  componentTone,
  confidenceTone,
  exactUtc,
  headline,
  heldLine,
  readingLine,
  regimeWords,
  statusWords,
} = await importTs('src/components/market/regime/regimeSummaryText.ts')

const READ_AT = Date.UTC(2026, 8, 16, 12, 0, 4)

function summary(over = {}) {
  return {
    symbol: 'BTC-PERP',
    read_at_ms: READ_AT,
    observed_at_ms: READ_AT - 1000,
    snapshot_age_ms: 1000,
    source_read: true,
    current: { condition: 'trending_healthy', label: 'Trending, healthy', known: true, trend: 'strong_trend', trend_basis: 'derived' },
    confidence: { level: 'high', usable_inputs: 3, required_inputs: 3, share_usable: 1, reported_by_market_data: 'high' },
    history: { held: null, transitions: [], readings: 0 },
    ...over,
  }
}

test('a reading time is the exact moment, in UTC, to the second', () => {
  assert.equal(exactUtc(READ_AT), '2026-09-16 12:00:04 UTC')
  assert.equal(exactUtc(null), 'unknown')
  assert.equal(exactUtc(undefined), 'unknown')
})

test('ages read in their two largest units', () => {
  assert.equal(ageWords(4200), '4s')
  assert.equal(ageWords(200_000), '3m 20s')
  assert.equal(ageWords(180_000), '3m')
  assert.equal(ageWords(7_500_000), '2h 5m')
  assert.equal(ageWords(null), 'unknown')
})

test('a regime label reads as words rather than an identifier', () => {
  assert.equal(regimeWords('strong_trend'), 'strong trend')
  assert.equal(regimeWords('extreme_positive'), 'extreme positive')
  assert.equal(regimeWords(null), 'unknown')
})

test('confidence and each input carry an honest tone', () => {
  assert.equal(confidenceTone('high'), 'good')
  assert.equal(confidenceTone('medium'), 'warn')
  assert.equal(confidenceTone('low'), 'bad')
  assert.equal(componentTone({ usable: true, present: true }), 'good')
  // A proxy is present but unusable: it must never read as good evidence.
  assert.equal(componentTone({ usable: false, present: true }), 'warn')
  assert.equal(componentTone({ usable: false, present: false }), 'bad')
})

test('a status says what the reading actually is, naming a proxy as a proxy', () => {
  assert.equal(statusWords({ status: 'REAL' }), 'read from the venue')
  assert.equal(statusWords({ status: 'DERIVED' }), 'derived from venue readings')
  assert.equal(statusWords({ status: 'PROXY' }), 'proxy')
  assert.equal(statusWords({ status: 'NOT_READ' }), 'not read')
  assert.equal(statusWords({ status: 'UNAVAILABLE' }), 'unavailable')
})

test('the headline counts the evidence, and an unclassified regime promises the missing inputs are named', () => {
  assert.match(headline(summary()), /Trending, healthy · high confidence · 3 of 3 required inputs usable/)
  const unknown = headline(summary({
    current: { condition: 'unknown', label: 'Not classified', known: false, trend: 'range', trend_basis: 'derived' },
    confidence: { level: 'low', usable_inputs: 1, required_inputs: 3, share_usable: 0.33, reported_by_market_data: 'low' },
  }))
  assert.match(unknown, /Not classified/)
  assert.match(unknown, /1 of 3 required inputs usable/)
  assert.match(unknown, /every missing input is named below/)
  // The bare word must never stand alone as the whole answer.
  assert.ok(!/^UNKNOWN$/i.test(unknown))
})

test('the reading line gives both the reading time and when the market behind it was read', () => {
  assert.equal(
    readingLine(summary()),
    'Read 2026-09-16 12:00:04 UTC · market read 2026-09-16 12:00:03 UTC (1s old)',
  )
})

test('an unread source says so instead of implying a fresh market reading', () => {
  const line = readingLine(summary({ source_read: false, observed_at_ms: null, snapshot_age_ms: null }))
  assert.match(line, /market-data did not answer/)
  assert.match(line, /^Read 2026-09-16 12:00:04 UTC/)
})

test('the recorded regime says how long it has stood, or that there is none yet', () => {
  assert.match(heldLine(summary()), /No regime has been recorded/)
  const held = heldLine(summary({
    history: { held: { regime: 'rising', readings: 2, since_ms: READ_AT - 60_000, basis: 'closed candles' }, transitions: [], readings: 2 },
  }))
  assert.match(held, /rising across the last 2 readings/)
  assert.match(held, /2026-09-16 11:59:04 UTC/)
})

test('a market reading without an age says so rather than "unknown old"', () => {
  const line = readingLine(summary({ snapshot_age_ms: null }))
  assert.match(line, /market read 2026-09-16 12:00:03 UTC \(age unknown\)/)
  assert.doesNotMatch(line, /unknown old/)
})
