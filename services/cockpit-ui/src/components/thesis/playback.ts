import type { ThesisEdition } from '../../api/types'
import type { PriceLevel } from '../canvas/chartTypes'

export const PLAYBACK_INTERVALS = ['1w', '1d', '12h', '8h', '4h', '2h', '1h'] as const
export type PlaybackInterval = (typeof PLAYBACK_INTERVALS)[number]

export interface SubtitleCue {
  start: number
  end: number
  text: string
}

export interface PlaybackScene {
  id: string
  symbol: string
  interval: PlaybackInterval
  start: number
  end: number
  title: string
  narration: string
  phase: 'overview' | 'market' | 'scenario'
}

function clockSeconds(value: string): number {
  const match = value.trim().match(/^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$/)
  if (!match) return Number.NaN
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) + Number(match[4]) / 1000
}

/** Parse only timed SRT cues. Malformed blocks are ignored rather than assigned invented times. */
export function parseSrt(source: string): SubtitleCue[] {
  return source
    .trim()
    .split(/\r?\n\s*\r?\n/)
    .map((block) => {
      const lines = block.split(/\r?\n/)
      const timingIndex = lines.findIndex((line) => line.includes('-->'))
      if (timingIndex < 0) return null
      const [rawStart, rawEnd] = lines[timingIndex].split('-->').map((part) => part.trim())
      const start = clockSeconds(rawStart)
      const end = clockSeconds(rawEnd)
      const text = lines.slice(timingIndex + 1).join(' ').replace(/<[^>]+>/g, '').trim()
      return Number.isFinite(start) && Number.isFinite(end) && end > start && text
        ? { start, end, text }
        : null
    })
    .filter((cue): cue is SubtitleCue => cue !== null)
    .sort((a, b) => a.start - b.start)
}

function fallbackCues(edition: ThesisEdition): SubtitleCue[] {
  const labels = ['Market overview', ...edition.symbols, 'End of edition']
  return labels.map((text, index) => ({ start: index * 16, end: (index + 1) * 16, text }))
}

/**
 * Turn the edition's real subtitle timing into calm semantic scenes. One
 * spoken cue drives one chart state: an earlier implementation divided every
 * cue across seven intervals, which made the picture change faster than a
 * person could read it and disconnected captions from the chart.
 */
export function buildPlaybackScenes(edition: ThesisEdition, parsedCues: SubtitleCue[]): PlaybackScene[] {
  const cues = parsedCues.length ? parsedCues : fallbackCues(edition)
  const firstSymbol = edition.outlook && 'leads' in edition.outlook
    ? edition.outlook.leads[0]?.symbol || edition.symbols[0]
    : edition.symbols[0]
  const scenes: PlaybackScene[] = []
  if ('horizon_context' in edition.outlook && edition.outlook.horizon_context && cues.length >= 6) {
    const sol = edition.symbols.includes('SOL-PERP') ? 'SOL-PERP' : firstSymbol
    const story: { symbol: string; interval: PlaybackInterval; title: string; phase: PlaybackScene['phase'] }[] = [
      { symbol: firstSymbol, interval: '1w', title: 'Market map · month and week first', phase: 'overview' },
      { symbol: 'BTC-PERP', interval: '1d', title: 'Bitcoin · higher to lower timeframe', phase: 'market' },
      { symbol: 'ETH-PERP', interval: '1d', title: 'Ethereum · relative strength', phase: 'market' },
      { symbol: sol, interval: '1d', title: 'Altcoin breadth · participation, not a pair call', phase: 'market' },
      { symbol: 'BTC-PERP', interval: '4h', title: 'Macro and scheduled risk', phase: 'market' },
      { symbol: 'BTC-PERP', interval: '1h', title: 'Scenario workshop · entry, target and invalidation', phase: 'scenario' },
    ]
    return story.map((item, index) => ({ ...item, id: `story:${index}:${item.interval}`, start: cues[index].start, end: cues[index].end, narration: cues[index].text }))
  }
  const opening = cues[0]
  if (opening && firstSymbol) {
    scenes.push({ id: 'overview:1w', symbol: firstSymbol, interval: '1w', start: opening.start, end: opening.end, title: 'Market map · higher timeframe first', narration: opening.text, phase: 'overview' })
  }

  edition.symbols.forEach((symbol, index) => {
    const cue = cues[index + 1] ?? {
      start: (index + 1) * 16,
      end: (index + 2) * 16,
      text: edition.theses?.[symbol]?.text || symbol,
    }
    const interval: PlaybackInterval = symbol === 'BTC-PERP' || symbol === 'ETH-PERP' ? '1d' : '4h'
    scenes.push({ id: `${symbol}:${interval}`, symbol, interval, start: cue.start, end: cue.end, title: `${symbol.replace('-PERP', '')} · measured ${interval} context`, narration: cue.text, phase: 'market' })
  })

  const close = cues[edition.symbols.length + 1]
  if (close && firstSymbol) {
    scenes.push({
      id: 'scenario:1h',
      symbol: firstSymbol,
      interval: '1h',
      start: close.start,
      end: close.end,
      title: 'Scenario workshop · entry, target and invalidation',
      narration: close.text,
      phase: 'scenario',
    })
  }
  return scenes
}

export function sceneIndexAtTime(scenes: PlaybackScene[], time: number): number {
  if (!scenes.length) return 0
  const exact = scenes.findIndex((scene) => time >= scene.start && time < scene.end)
  if (exact >= 0) return exact
  if (time >= scenes[scenes.length - 1].end) return scenes.length - 1
  const next = scenes.findIndex((scene) => scene.start > time)
  return next <= 0 ? 0 : next - 1
}

function finitePrice(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
}

/** Price-aligned, presentation-only lines for the current chapter. */
export function sceneLevels(edition: ThesisEdition, scene: PlaybackScene): PriceLevel[] {
  const thesis = edition.theses?.[scene.symbol]
  if (!thesis) return []
  const anchors = thesis.anchors
  const levels: PriceLevel[] = []
  const add = (id: string, price: number | null | undefined, label: string, colour: string) => {
    if (finitePrice(price)) levels.push({ drawingId: `playback:${scene.id}:${id}`, price, label, colour, style: 'dotted' })
  }

  if (scene.interval === '1w' || scene.interval === '1d') {
    add('high', anchors.high_24h, 'Edition 24h high', '#5aa0ff')
    add('low', anchors.low_24h, 'Edition 24h low', '#5aa0ff')
  } else if (scene.interval === '12h' || scene.interval === '8h' || scene.interval === '4h' || scene.interval === '2h') {
    add('high', anchors.high_4h, 'Edition 4h high', '#8b7cf6')
    add('low', anchors.low_4h, 'Edition 4h low', '#8b7cf6')
  } else {
    add('high', anchors.high_1h, 'Edition 1h high', '#38bdf8')
    add('low', anchors.low_1h, 'Edition 1h low', '#38bdf8')
  }
  add('close', anchors.last_close, 'Edition close', '#d9e2ef')
  add('invalidation', thesis.invalidation.level, 'Invalidation', '#e0574a')
  return levels
}
