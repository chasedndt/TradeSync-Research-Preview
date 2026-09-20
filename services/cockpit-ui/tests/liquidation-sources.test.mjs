import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const {
  SOURCE_STANDING,
  directionAllowed,
  proxyLine,
  receivedLine,
  sideWords,
  skewWords,
  usd,
} = await importTs('src/components/market/liquidations/liquidationSources.ts')

const KINDS = ['observed_events', 'venue_mechanics', 'inferred_pressure', 'legacy_proxy']

test('every liquidation source is classified once, and says what it is and why', () => {
  assert.deepEqual(Object.keys(SOURCE_STANDING), KINDS)
  for (const kind of KINDS) {
    const standing = SOURCE_STANDING[kind]
    assert.equal(standing.kind, kind)
    assert.ok(standing.title && standing.basis && standing.directionNote && standing.authority)
  }
})

test('only the source that records real side-labelled events may show a side', () => {
  assert.equal(directionAllowed('observed_events'), true)
  assert.equal(directionAllowed('venue_mechanics'), false)
  assert.equal(directionAllowed('inferred_pressure'), false)
  // The whole point: a proxy must never read as an observed fact.
  assert.equal(directionAllowed('legacy_proxy'), false)
})

test('asking a source for a side it cannot support is refused rather than guessed', () => {
  assert.equal(sideWords('observed_events', 'long'), 'longs closed')
  assert.equal(sideWords('observed_events', 'short'), 'shorts closed')
  assert.equal(sideWords('observed_events', null), 'side not given')
  for (const kind of ['legacy_proxy', 'inferred_pressure', 'venue_mechanics']) {
    assert.throws(() => sideWords(kind, 'long'), /cannot carry a side/)
  }
})

test('the proxy states a total only, and its note explains the missing split', () => {
  assert.equal(proxyLine(1_250_000), '$1.3m estimated over the last hour, as a total only.')
  assert.equal(proxyLine(null), 'No proxy estimate in this reading.')
  const note = SOURCE_STANDING.legacy_proxy.directionNote
  assert.match(note, /fifty-fifty/)
  assert.match(note, /assumption/)
  assert.ok(!/\blongs?\s+\$/i.test(proxyLine(1_250_000)), 'the proxy line must not pair a side with a figure')
})

test('Hyperliquid mechanics say plainly that no market-wide feed is published', () => {
  assert.match(SOURCE_STANDING.venue_mechanics.directionNote, /no market-wide liquidation feed/i)
})

test('received liquidations carry their sides, because the venues published them', () => {
  assert.equal(
    receivedLine({ long_usd: 2_400_000, short_usd: 900_000, net_usd: 1_500_000, events: 12 }),
    '12 events: $2.4m of longs and $900k of shorts closed, longs the heavier side.',
  )
  assert.match(receivedLine({ long_usd: 0, short_usd: 0, net_usd: 0, events: 0 }), /No liquidation was recorded/)
  assert.match(receivedLine(undefined), /No liquidations recorded/)
})

test('inferred levels describe where they sit, never which way price will go', () => {
  const above = skewWords(0.42)
  assert.match(above, /More estimated levels sit above price/)
  assert.match(skewWords(-0.42), /More estimated levels sit below price/)
  assert.match(skewWords(0), /evenly placed/)
  assert.match(skewWords(null), /No estimated levels within 3%/)
  // Placement, not a call: no source may turn this into a long or short read.
  for (const words of [above, skewWords(-0.42), skewWords(0)]) {
    assert.ok(!/\b(buy|sell|bullish|bearish|long signal|short signal)\b/i.test(words))
  }
})

test('dollar figures stay compact and keep their sign', () => {
  assert.equal(usd(95), '$95')
  assert.equal(usd(840_000), '$840k')
  assert.equal(usd(1_200_000), '$1.2m')
  assert.equal(usd(-1_200_000), '−$1.2m')
  assert.equal(usd(null), '—')
})
