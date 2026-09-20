/**
 * How an opportunity brief reads on screen.
 *
 * Wording and units only. Every figure is read from the brief exactly as the
 * state API assembled it from stored records: nothing here scores, thresholds,
 * or derives a level, a ratio or a verdict. A share arrives as 0 to 1 and is
 * shown as it arrives; a time in seconds is shown as the moment it names.
 */

import type { BriefCondition, BriefPlan, BriefPlanFixed, BriefState, RegimeFit } from '../../../api/opportunityBriefTypes'
import { ageWords, exactUtc } from '../../market/readingTime'

export type Tone = 'good' | 'warn' | 'bad' | 'dim'

const FIT_WORDS: Record<RegimeFit, string> = {
  with: 'With the regime',
  against: 'Against the regime',
  flat: 'Regime flat',
  unlabelled: 'Regime not labelled',
}

const FIT_TONE: Record<RegimeFit, Tone> = { with: 'good', against: 'warn', flat: 'dim', unlabelled: 'dim' }

export const fitWords = (fit: RegimeFit): string => FIT_WORDS[fit] ?? 'Regime not labelled'
export const fitTone = (fit: RegimeFit): Tone => FIT_TONE[fit] ?? 'dim'

/** The exact moment a time in epoch seconds names, in UTC. */
export const atSeconds = (seconds: number | null | undefined): string =>
  seconds == null ? 'unknown' : exactUtc(seconds * 1000)

/** A price as stored, at a precision that suits its size. */
export function priceWords(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  if (value >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 1 })
  return value >= 1 ? value.toFixed(2) : value.toPrecision(4)
}

export const usdcWords = (value: number | null | undefined): string =>
  value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)} USDC`

/** The net reward-to-risk as stored: "1.73 to 1". */
export const ratioWords = (value: number | null | undefined): string =>
  value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)} to 1`

/** A condition's value in its own unit: a share and a score as stored, an age as a duration. */
export function conditionValue(value: number | null, unit: string): string {
  if (value == null || !Number.isFinite(value)) return 'not stored'
  if (unit === 'ms') return ageWords(value)
  return value.toFixed(2)
}

/** "Evidence coverage 0.55, needing at least 0.30". */
export function conditionLine(condition: BriefCondition): string {
  const needs = condition.comparator === '>=' ? 'at least' : 'at most'
  return `${condition.label} ${conditionValue(condition.measured, condition.unit)}, needing ${needs} `
    + `${conditionValue(condition.required, condition.unit)}`
}

export const conditionTone = (met: boolean | null): Tone => (met === true ? 'good' : met === false ? 'bad' : 'dim')

export const conditionMark = (met: boolean | null): string => (met === true ? 'met' : met === false ? 'not met' : 'not stored')

/** Whether a paper position was opened, so the plan has levels. */
export const isFixedPlan = (plan: BriefPlan): plan is BriefPlanFixed => plan.status !== 'none'

/** When the opportunity opened and how old it was when this brief was read. */
export function openedLine(openedAt: number | null, ageSeconds: number | null): string {
  if (openedAt == null) return 'Opening time not stored'
  return `Opened ${atSeconds(openedAt)} · ${ageSeconds == null ? 'age unknown' : `${ageWords(ageSeconds * 1000)} old`}`
}

/** When the brief was read. */
export const readLine = (readAt: number): string => `Read ${atSeconds(readAt)}`

/** Paper-state tone: an open position or an admissible entry reads good, a pause or an unknown warns. */
export function stateTone(state: Pick<BriefState, 'position' | 'entries_paused' | 'execution_enabled' | 'label'>): Tone {
  if (state.execution_enabled) return 'bad'
  if (state.position === 'open') return 'good'
  if (state.entries_paused === true || state.entries_paused === null) return 'warn'
  return state.label === 'Paper research only' || state.position === 'closed' ? 'dim' : 'good'
}

export const sideTone = (side: string): Tone => (side === 'LONG' ? 'good' : side === 'SHORT' ? 'bad' : 'dim')

/** The first twelve characters of a digest, which is how it is quoted beside the full value. */
export const shortDigest = (digest: string | null | undefined): string => (digest ? digest.slice(0, 12) : 'not stored')

/** The conditions count as stored: "4 of 4 conditions met", or why there are none. */
export function conditionsCount(entry: { schema: string; conditions_met: number; conditions_checked: number }): string {
  if (entry.schema === 'legacy') return 'Conditions not stored'
  return `${entry.conditions_met} of ${entry.conditions_checked} conditions met`
}
