import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { buildPlaybackScenes, parseSrt, sceneIndexAtTime, sceneLevels } = await importTs('src/components/thesis/playback.ts')

const edition = {
  id: 'edition-1',
  symbols: ['BTC-PERP', 'ETH-PERP'],
  outlook: { leads: [{ symbol: 'BTC-PERP' }] },
  theses: {
    'BTC-PERP': {
      text: 'Bitcoin read.',
      anchors: { last_close: 75_000, high_1h: 75_400, low_1h: 74_800, high_4h: 76_000, low_4h: 74_000, high_24h: 78_000, low_24h: 72_000 },
      invalidation: { level: 76_500 },
    },
    'ETH-PERP': { text: 'Ether read.', anchors: {}, invalidation: { level: null } },
  },
}

const srt = `1
00:00:00,000 --> 00:00:08,000
Market overview

2
00:00:08,000 --> 00:00:24,000
Bitcoin chapter

3
00:00:24,000 --> 00:00:40,000
Ether chapter

4
00:00:40,000 --> 00:00:46,000
Risk boundary
`

test('SRT timing becomes ordered spoken cues', () => {
  const cues = parseSrt(srt)
  assert.equal(cues.length, 4)
  assert.deepEqual(cues[1], { start: 8, end: 24, text: 'Bitcoin chapter' })
})

test('each spoken cue holds one readable chart state and ends with the scenario', () => {
  const scenes = buildPlaybackScenes(edition, parseSrt(srt))
  assert.equal(scenes.length, 4)
  assert.deepEqual(scenes.map((scene) => scene.interval), ['1w', '1d', '1d', '1h'])
  assert.equal(scenes.at(-1).phase, 'scenario')
  assert.equal(sceneIndexAtTime(scenes, 25), scenes.findIndex((scene) => scene.symbol === 'ETH-PERP'))
})

test('playback lines use stored edition levels and change with the timeframe', () => {
  const scenes = buildPlaybackScenes(edition, parseSrt(srt))
  const daily = sceneLevels(edition, scenes.find((scene) => scene.symbol === 'BTC-PERP' && scene.phase === 'market'))
  const hourly = sceneLevels(edition, scenes.find((scene) => scene.phase === 'scenario'))
  assert.ok(daily.some((level) => level.price === 78_000 && level.label.includes('24h high')))
  assert.ok(hourly.some((level) => level.price === 75_400 && level.label.includes('1h high')))
  assert.ok(hourly.some((level) => level.price === 76_500 && level.label === 'Invalidation'))
  assert.ok(hourly.every((level) => level.drawingId.startsWith('playback:')))
})

test('malformed subtitle blocks are ignored instead of receiving invented times', () => {
  assert.deepEqual(parseSrt('1\nnot a timing line\nwords'), [])
})

test('an integrated edition uses six aligned story chapters instead of every pair', () => {
  const storyEdition = { ...edition, symbols: ['BTC-PERP', 'ETH-PERP', 'SOL-PERP', 'HYPE-PERP'], outlook: { horizon_context: { 'BTC-PERP': {}, 'ETH-PERP': {} }, leads: [{ symbol: 'BTC-PERP' }] } }
  const storySrt = Array.from({ length: 6 }, (_, i) => `${i + 1}\n00:00:${String(i * 10).padStart(2, '0')},000 --> 00:00:${String((i + 1) * 10).padStart(2, '0')},000\nchapter ${i + 1}`).join('\n\n')
  const scenes = buildPlaybackScenes(storyEdition, parseSrt(storySrt))
  assert.equal(scenes.length, 6)
  assert.deepEqual(scenes.map((scene) => scene.symbol), ['BTC-PERP', 'BTC-PERP', 'ETH-PERP', 'SOL-PERP', 'BTC-PERP', 'BTC-PERP'])
  assert.equal(scenes.at(-1).phase, 'scenario')
})
