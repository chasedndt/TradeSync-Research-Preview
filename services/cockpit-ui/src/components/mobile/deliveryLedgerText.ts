/**
 * The delivery ledger in words: one line per notification, saying exactly what happened to it and when.
 *
 * Every time is absolute and to the second. "2 minutes ago" hides whether an alert arrived before or after the
 * thing it was about, which is the only reason to read this table.
 */

import type { LedgerEvent } from '../../api/mobileAlertTypes'

const STATUS_WORDS: Record<string, string> = {
  queued: 'queued',
  sending: 'being sent',
  retry: 'waiting to be tried again',
  provider_accepted: 'accepted by the provider',
  operator_confirmed: 'confirmed received on the phone',
  failed: 'failed',
  expired: 'expired before it could be sent',
  dead_letter: 'given up on',
}

export const statusWord = (status: string): string => STATUS_WORDS[status] ?? status.replace(/_/g, ' ')

/** "device" is only ever a tap on the notification, proven by the single-use token that notification carried. */
const ACKNOWLEDGED_WORDS: Record<string, string> = {
  operator: 'the operator',
  device: 'a tap on the notification',
}

const TRANSPORT_WORDS: Record<string, string> = {
  ntfy: 'via ntfy',
  web_push: 'via Web Push',
}

/** "via Web Push" — which transport carried the latest attempt, or nothing before one was made. */
export const transportWord = (transport: string | null | undefined): string =>
  transport ? (TRANSPORT_WORDS[transport] ?? `via ${transport.replace(/_/g, ' ')}`) : ''

/** "16 Sep 2026, 21:04:07" — an absolute local time, to the second. */
export function exactTime(iso: string | null | undefined): string {
  if (!iso) return 'no time recorded'
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return 'no time recorded'
  return when.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

/** A short reference for one alert, as the phone shows it. */
export const reference = (event: Pick<LedgerEvent, 'id'>): string => event.id.slice(0, 8)

/** "3 of 5 attempts · last tried 16 Sep 2026, 21:04:07" — or that nothing has been tried yet. */
export function attemptLine(event: LedgerEvent, maxAttempts: number): string {
  if (!event.attempts) return 'not attempted yet'
  const tried = event.attempted_at ? ` · last tried ${exactTime(event.attempted_at)}` : ''
  return `${event.attempts} of ${maxAttempts} attempts${tried}`
}

/** What the provider said, if anything, and when. Over Web Push the provider is the browser's push service. */
export function providerLine(event: LedgerEvent): string | null {
  if (event.accepted_at) {
    const who = event.transport === 'web_push' ? 'Push service' : 'Provider'
    return `${who} accepted it at ${exactTime(event.accepted_at)} — not proof a phone showed it`
  }
  if (event.status === 'retry' && event.next_attempt_at) return `Next attempt at ${exactTime(event.next_attempt_at)}`
  return null
}

export function acknowledgementLine(event: LedgerEvent): string | null {
  if (!event.acknowledged_at) return null
  const who = ACKNOWLEDGED_WORDS[event.acknowledged_by ?? ''] ?? 'someone'
  return `Marked seen by ${who} at ${exactTime(event.acknowledged_at)}`
}

export function deadLetterLine(event: LedgerEvent): string | null {
  if (!event.dead_lettered_at) return null
  const reason = event.dead_letter_reason?.trim()
  return `Given up on at ${exactTime(event.dead_lettered_at)}${reason ? ` — ${reason}` : ''}`
}

/** Whether there is anything to mark seen: it was attempted, and nobody has said so yet. */
export const canAcknowledge = (event: LedgerEvent): boolean => event.attempts > 0 && !event.acknowledged_at

/** Whether this is the provider-accepted test an operator can attest to having received on the phone. */
export const canConfirmReceipt = (event: LedgerEvent): boolean => event.status === 'provider_accepted'

/** "15s, 30s, 60s, 120s" — the waits the server will actually apply, from the server. */
export const retryLadder = (seconds: number[]): string => seconds.map((value) => `${value}s`).join(', ')
