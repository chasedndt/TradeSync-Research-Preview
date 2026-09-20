import type { StoredPayload } from '../../api/activityTypes'
import { codeLabel } from '../ledger/paperRisk/paperRiskFormat'

/**
 * One stored row's fields in words: verdicts, statuses and modes exactly as the row carries them,
 * payload fields read without guessing, and figures state-api measured, formatted and never recomputed.
 */

export type Tone = 'good' | 'warn' | 'bad' | 'dim' | 'plain'
export interface Labelled { text: string; tone: Tone }

/** A payload's text or number field as text; absent, blank or any other shape is null. */
export function payloadText(payload: StoredPayload | null | undefined, key: string): string | null {
  const value = payload?.[key]
  if (typeof value === 'string') return value.trim() || null
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

export function payloadNumber(payload: StoredPayload | null | undefined, key: string): number | null {
  const value = payload?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** The verdict the risk check stored with a decision; a row without one says so. */
export function decisionVerdict(risk: StoredPayload | null | undefined): Labelled {
  if (risk?.allowed === true) return { text: 'Allowed', tone: 'good' }
  if (risk?.allowed === false) return { text: 'Blocked', tone: 'bad' }
  return { text: 'No verdict stored', tone: 'dim' }
}

export function decisionReason(risk: StoredPayload | null | undefined): string {
  const code = payloadText(risk, 'reason_code')
  const reason = payloadText(risk, 'reason')
  if (code && reason) return `${code}: ${reason}`
  return code ?? reason ?? '—'
}

const ORDER_TONES: Record<string, Tone> = { placed: 'good', rejected: 'bad', error: 'bad' }

/** An order's status as stored, in words. */
export function orderStatus(status: string | null | undefined): Labelled {
  if (!status) return { text: 'No status stored', tone: 'dim' }
  return { text: codeLabel(status), tone: ORDER_TONES[status.toLowerCase()] ?? 'plain' }
}

/** The paper flag stored on the order. */
export function orderMode(paper: boolean | null | undefined): string {
  if (paper === true) return 'Paper'
  if (paper === false) return 'Live'
  return '—'
}

/** The error the execution boundary returned with an order, as code and message, or as the text stored. */
export function orderError(response: StoredPayload | null | undefined): string | null {
  const error = response?.error
  if (typeof error === 'string') return error.trim() || null
  if (!error || typeof error !== 'object' || Array.isArray(error)) return null
  const code = payloadText(error as StoredPayload, 'code')
  const message = payloadText(error as StoredPayload, 'message')
  if (code && message) return `${code}: ${message}`
  return code ?? message
}

/** Every stored envelope was approved; what differs is whether a paper evaluation consumed it. */
export function approvalState(consumedAt: string | null | undefined): string {
  return consumedAt ? 'Consumed' : 'Not consumed'
}

const OUTCOME_TONES: Record<string, Tone> = { pending: 'warn', insufficient_candles: 'dim' }

export function outcomeStatus(status: string | null | undefined): Labelled {
  if (!status) return { text: 'No status stored', tone: 'dim' }
  return { text: codeLabel(status), tone: OUTCOME_TONES[status] ?? 'plain' }
}

/** Each distinct value once, in the order first seen; blanks are skipped. */
export function distinct(values: readonly (string | null | undefined)[]): string[] {
  const seen: string[] = []
  for (const value of values) {
    if (value && !seen.includes(value)) seen.push(value)
  }
  return seen
}

const finite = (value: number | null | undefined): value is number => value != null && Number.isFinite(value)

/** A percentage state-api measured, signed, to three decimals. A missing one is a dash, never 0. */
export function percentText(value: number | null | undefined): string {
  if (!finite(value)) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(3)}%`
}

export function priceText(value: number | null | undefined): string {
  return finite(value) ? value.toLocaleString('en-GB', { maximumSignificantDigits: 7 }) : '—'
}

/** Entry and exit prices of a measurement; an unmeasured row, which has neither, is one dash. */
export function priceRangeText(entry: number | null | undefined, exit: number | null | undefined): string {
  return finite(entry) || finite(exit) ? `${priceText(entry)} → ${priceText(exit)}` : '—'
}

export function usdText(value: number | null | undefined): string {
  return finite(value) ? `${value.toLocaleString('en-GB', { maximumFractionDigits: 2 })} USD` : '—'
}

export function horizonText(minutes: number | null | undefined): string {
  return finite(minutes) ? `${minutes} min` : '—'
}

/** The start of an identifier or digest, for a table cell; the whole value belongs in its title. */
export function shortId(value: string | null | undefined, length = 8): string {
  if (!value) return '—'
  return value.length > length ? `${value.slice(0, length)}…` : value
}

const METRICS: Record<string, string> = { funding: 'Funding', oi: 'Open interest', volume: 'Volume', trend: 'Trend' }

export function alertMetric(metric: string): string {
  return METRICS[metric] ?? codeLabel(metric)
}

export function alertType(type: string): string {
  return codeLabel(type)
}

/** A regime value in words: extreme_positive reads extreme positive. */
export function regimeWords(value: string | null | undefined): string {
  return value ? value.split('_').join(' ') : '—'
}

export function alertChange(previous: string | null | undefined, next: string | null | undefined): string {
  return previous ? `${regimeWords(previous)} → ${regimeWords(next)}` : regimeWords(next)
}
