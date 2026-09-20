/**
 * How the Settings sections read. Wording only: each standing restates a value an
 * endpoint returned, and nothing here decides, scores or derives anything.
 */

import type { RetentionWindow, SignerStatus } from '../../api/operatorSettingsTypes'
import type { RiskState } from '../../api/paperRiskTypes'
import type { VenueStatus } from '../../api/types'
import { exactUtc } from '../market/readingTime'

export type Tone = 'good' | 'warn' | 'bad' | 'dim'

export interface Standing {
  label: string
  detail: string
  tone: Tone
}

const CHECKING: Standing = { label: 'Checking', detail: 'Reading…', tone: 'dim' }

const isoUtc = (iso: string | null | undefined): string => (iso ? exactUtc(Date.parse(iso)) : 'an unrecorded time')

/** Whether the paper kill switch is engaged, and who last changed it. */
export function killLine(kill: RiskState['kill_switch'] | undefined, unreadable = false): Standing {
  if (unreadable) {
    return { label: 'Unknown', detail: 'The paper risk state could not be read, so the kill switch state is unknown.', tone: 'bad' }
  }
  if (kill === undefined) return CHECKING
  if (kill === null) {
    return { label: 'Not recorded', detail: 'The kill switch record is missing, so new paper entries are refused.', tone: 'bad' }
  }
  if (kill.active) {
    return {
      label: 'Engaged',
      detail: `Engaged by ${kill.operator} at ${isoUtc(kill.changed_at)}: ${kill.reason}. No new paper entries.`,
      tone: 'bad',
    }
  }
  return { label: 'Clear', detail: `Last changed by ${kill.operator} at ${isoUtc(kill.changed_at)}: ${kill.reason}.`, tone: 'good' }
}

/** The Hyperliquid executor as the execution status reports it. */
export function executorLine(venue: VenueStatus | undefined): Standing {
  if (!venue) {
    return { label: 'Not reported', detail: 'The execution status carries no Hyperliquid executor.', tone: 'dim' }
  }
  if (venue.circuit_open === true) {
    return { label: 'Circuit open', detail: venue.error || 'The executor has tripped its circuit breaker.', tone: 'bad' }
  }
  if (venue.circuit_open === false) {
    return {
      label: 'Responding',
      detail: 'The Hyperliquid executor answers. Whether an order may be placed is still decided by EXECUTION_ENABLED.',
      tone: 'warn',
    }
  }
  return { label: 'Not running', detail: 'The Hyperliquid executor is not running in this runtime.', tone: 'dim' }
}

/** The isolated signer. Unreachable is the expected state, so it reads as good rather than as a failure. */
export function signerLine(signer: SignerStatus | undefined, unreadable = false): Standing {
  if (unreadable) return { label: 'Unknown', detail: 'The signer status could not be read.', tone: 'bad' }
  if (!signer) return CHECKING
  if (!signer.reachable) {
    return {
      label: 'Not running',
      detail: 'No signer is reachable, so no order can be signed through it. Running one is a deliberate operator act.',
      tone: 'good',
    }
  }
  const status = signer.status ? `reports "${signer.status}"` : 'answers'
  return {
    label: 'Running',
    detail: `The isolated signer ${status}${signer.available ? ' and says it is available' : ''}. It is a separate process, and the approval and execution gates still apply.`,
    tone: 'warn',
  }
}

/** How long a record is kept, and in what detail. */
export function retentionLine(window: RetentionWindow): string {
  const kept = `${window.kept_days} days`
  if (window.full_detail_days == null || window.downsampled_to_minutes == null) return kept
  return `${kept}: every minute for ${window.full_detail_days} days, then one per ${window.downsampled_to_minutes} minutes`
}

/** The Cockpit's own readings, counted from its query cache. */
export function fetchCensus(total: number, failing: number): Standing {
  if (total === 0) return { label: 'Nothing read yet', detail: 'This page has not read anything yet.', tone: 'dim' }
  if (failing === 0) return { label: 'All answering', detail: `All ${total} readings answered their last request.`, tone: 'good' }
  return { label: `${failing} failing`, detail: `${failing} of ${total} readings failed their last request.`, tone: 'bad' }
}

export const timezoneLine = (zone: string | undefined): string =>
  zone ? `This browser reports its timezone as ${zone}.` : 'This browser did not report a timezone.'

/** What "Clear cached previews" removes: results this browser cached, nothing held on the server. */
export const CACHED_STATE_KEYS = ['tradesync_preview_cache', 'tradesync_execution_cache'] as const
