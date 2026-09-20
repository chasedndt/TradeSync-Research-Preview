import type { Candle } from '../../api/types'

export interface StructureCandidate {
  label: string
  detail: string
  authority: 'descriptive candidate'
}

/**
 * Deterministic, presentation-only structure labels. These do not score a
 * setup. A candidate needs a later forward-test before it can earn authority.
 */
export function detectStructure(candles: Candle[]): StructureCandidate | null {
  if (candles.length < 36) return null
  const recent = candles.slice(-12)
  const prior = candles.slice(-36, -12)
  const last = recent[recent.length - 1]
  const priorHigh = Math.max(...prior.map((c) => c.high))
  const priorLow = Math.min(...prior.map((c) => c.low))
  if (last.close > priorHigh) return { label: 'Breakout candidate', detail: `Close cleared the prior 24-bar high. It is not confirmed until follow-through holds above ${priorHigh.toLocaleString()}.`, authority: 'descriptive candidate' }
  if (last.close < priorLow) return { label: 'Breakdown candidate', detail: `Close lost the prior 24-bar low. It is not confirmed until follow-through stays below ${priorLow.toLocaleString()}.`, authority: 'descriptive candidate' }
  const width = (rows: Candle[]) => Math.max(...rows.map((c) => c.high)) - Math.min(...rows.map((c) => c.low))
  const recentWidth = width(recent)
  const priorWidth = width(prior)
  if (priorWidth > 0 && recentWidth / priorWidth <= 0.65) {
    return { label: 'Range compression candidate', detail: `The latest 12-bar range is ${Math.round((recentWidth / priorWidth) * 100)}% of the preceding 24-bar range. Direction is unresolved until a boundary breaks.`, authority: 'descriptive candidate' }
  }
  const move = ((last.close / recent[0].open) - 1) * 100
  return { label: move >= 0 ? 'Rising range structure' : 'Falling range structure', detail: `The latest 12 bars moved ${move >= 0 ? '+' : ''}${move.toFixed(2)}%, but remain inside the preceding 24-bar range.`, authority: 'descriptive candidate' }
}
