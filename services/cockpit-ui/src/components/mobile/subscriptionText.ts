/**
 * One subscribed browser in words: whether pushes still go to it, and what its push service did with the last one.
 *
 * A push service accepting a push is not proof the phone showed it, and the wording keeps saying so. Every time is
 * absolute and to the second, as in the delivery ledger.
 */

import type { WebPushSubscription } from '../../api/webPushTypes'
import { exactTime } from './deliveryLedgerText'

type Health = Pick<WebPushSubscription, 'active' | 'last_attempt_at' | 'last_status' | 'last_error' | 'expired_at' | 'expired_reason'>

export type Tone = 'good' | 'problem' | 'neutral'

const accepted = (status: number | null): boolean => status !== null && status >= 200 && status < 300

export function healthLine(row: Health): string {
  if (!row.active) {
    const reason = row.expired_reason?.trim()
    return `Expired ${exactTime(row.expired_at)}${reason ? ` — ${reason}` : ''} Nothing is sent to it now.`
  }
  if (!row.last_attempt_at) return 'Nothing has been sent to this browser yet.'
  const when = exactTime(row.last_attempt_at)
  if (accepted(row.last_status)) return `Last push accepted by its push service at ${when} — not proof the phone showed it.`
  const answer = row.last_status !== null ? `HTTP ${row.last_status}` : (row.last_error ?? 'no answer')
  return `Last push not accepted at ${when}: ${answer}.`
}

export function healthTone(row: Health): Tone {
  if (!row.active || (row.last_attempt_at && !accepted(row.last_status))) return 'problem'
  return row.last_attempt_at ? 'good' : 'neutral'
}
