/**
 * How the regime summary reads on screen.
 *
 * Wording only. Every number these functions render is already calculated by
 * the state API (`tradesync_core.regime_summary`); nothing here derives a
 * regime, a share or a confidence level of its own.
 */

import type { ConfidenceLevel, RegimeComponent, RegimeSummary } from '../../../api/regimeSummaryTypes'
import { ageWords, exactUtc } from '../readingTime'

export type Tone = 'good' | 'warn' | 'bad' | 'dim'

// Every market panel states the exact moment behind a reading the same way.
export { ageWords, exactUtc }

/** "strong_trend" reads as "strong trend". */
export const regimeWords = (value: string | null | undefined): string =>
  value ? value.split('_').join(' ') : 'unknown'

export const confidenceTone = (level: ConfidenceLevel | string): Tone =>
  level === 'high' ? 'good' : level === 'medium' ? 'warn' : 'bad'

/** A component reads good only when the classifier could actually use it. */
export function componentTone(component: RegimeComponent): Tone {
  if (component.usable) return 'good'
  if (component.present) return 'warn'
  return 'bad'
}

/** The status word as it should appear: a proxy says so, an unread input says so. */
export function statusWords(component: RegimeComponent): string {
  if (component.status === 'NOT_READ') return 'not read'
  if (component.status === 'REAL') return 'read from the venue'
  if (component.status === 'DERIVED') return 'derived from venue readings'
  if (component.status === 'PROXY') return 'proxy'
  return component.status.toLowerCase()
}

/** The one line under the heading: what the regime is, and how much evidence stands behind it. */
export function headline(summary: RegimeSummary | undefined): string {
  if (!summary) return 'Reading the regime and the evidence behind it…'
  const { confidence, current } = summary
  const counted = `${confidence.usable_inputs} of ${confidence.required_inputs} required inputs usable`
  return current.known
    ? `${current.label} · ${confidence.level} confidence · ${counted}`
    : `Not classified · ${counted} · every missing input is named below`
}

/** When this reading was taken, and when the market behind it was last read. */
export function readingLine(summary: RegimeSummary | undefined): string {
  if (!summary) return ''
  const market = summary.source_read
    ? `market read ${exactUtc(summary.observed_at_ms)} (${summary.snapshot_age_ms == null ? 'age unknown' : `${ageWords(summary.snapshot_age_ms)} old`})`
    : 'market-data did not answer'
  return `Read ${exactUtc(summary.read_at_ms)} · ${market}`
}

/** How long the stored label has stood, in words, or why there is none. */
export function heldLine(summary: RegimeSummary): string {
  const held = summary.history.held
  if (!held) return 'No regime has been recorded against an opportunity for this market yet.'
  const readings = held.readings === 1 ? '1 reading' : `${held.readings} readings`
  return `${regimeWords(held.regime)} across the last ${readings}, since ${exactUtc(held.since_ms)}.`
}
