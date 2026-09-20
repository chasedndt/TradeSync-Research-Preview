import type { AuditSection, AuditSectionName } from '../../api/activityTypes'
import { utcStamp } from '../ledger/paperRisk/paperRiskFormat'

/**
 * Selection and wording for the Activity & Evidence page: which tab and window the address names,
 * where a reading stands, and what to say about it. No React, so the node tests can import it,
 * and no arithmetic on the evidence: every figure shown is one state-api computed.
 */

export { utcStamp }

export type TabId = AuditSectionName | 'alerts'

export const TABS: readonly { id: TabId; label: string }[] = [
  { id: 'decisions', label: 'Decisions' },
  { id: 'approvals', label: 'Approvals' },
  { id: 'orders', label: 'Orders' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'outcomes', label: 'Outcomes' },
]

export function tabFromParam(value: string | null | undefined): TabId {
  return TABS.find((tab) => tab.id === value)?.id ?? 'decisions'
}

/** Windows the export can serve; state-api refuses more than 31 days (tradesync_core.audit_export). */
export const WINDOW_DAYS: readonly number[] = [1, 7, 14, 31]
export const DEFAULT_WINDOW_DAYS = 7

export function windowDaysFromParam(value: string | null | undefined): number {
  const days = Number(value)
  return WINDOW_DAYS.includes(days) ? days : DEFAULT_WINDOW_DAYS
}

export function windowDaysLabel(days: number): string {
  return `${days} day${days === 1 ? '' : 's'}`
}

/** Rows each section shows here. The CSV export of the same window carries up to 5,000. */
export const PAGE_ROWS = 200
/** The newest alerts read from the market alert stream, which has no window of its own. */
export const ALERT_LIMIT = 100

export type ReadingState = 'reading' | 'unanswered' | 'stale' | 'ready'

/**
 * Where a reading stands. No data with an error is a request that failed, never an empty result.
 * Data with an error is the earlier reading, still shown, with the failed refresh stated beside it.
 */
export function readingState(query: { data?: unknown; isError: boolean }): ReadingState {
  if (query.data === undefined) return query.isError ? 'unanswered' : 'reading'
  return query.isError ? 'stale' : 'ready'
}

/** A section's count for its tab: the rows held, with a plus when the section reached its cap. */
export function sectionCount(section: Pick<AuditSection<unknown>, 'row_count' | 'truncated'> | undefined): string | null {
  if (!section) return null
  return section.truncated ? `${section.row_count}+` : String(section.row_count)
}

/** The alert count for its tab. A read that came back full may have left older alerts unread. */
export function alertCount(alerts: readonly unknown[] | undefined, limit: number): string | null {
  if (!alerts) return null
  return alerts.length >= limit ? `${alerts.length}+` : String(alerts.length)
}

const NOUNS: Record<TabId, [one: string, many: string]> = {
  decisions: ['decision', 'decisions'],
  approvals: ['approval', 'approvals'],
  orders: ['order', 'orders'],
  alerts: ['alert', 'alerts'],
  outcomes: ['outcome', 'outcomes'],
}

export function noun(tab: TabId, count: number): string {
  return NOUNS[tab][count === 1 ? 0 : 1]
}

/** An epoch-milliseconds time as an exact UTC stamp; nothing known is a dash. */
export function msStamp(ms: number | null | undefined): string {
  return ms != null && Number.isFinite(ms) && ms > 0 ? utcStamp(new Date(ms).toISOString()) : '—'
}

export function unansweredText(message: string): string {
  return `No reading. The request to the state API failed, so this is not an empty result: ${message}`
}

export function staleText(message: string, readAt: string): string {
  return `The latest refresh failed (${message}). What is shown is the earlier reading, taken ${readAt}.`
}

export function emptySectionText(tab: AuditSectionName, window: { from: string; to: string }): string {
  return `Nothing in this window: no ${noun(tab, 1)} was recorded between ${utcStamp(window.from)} and ${utcStamp(window.to)}.`
}

export function heldText(tab: AuditSectionName, section: Pick<AuditSection<unknown>, 'row_count' | 'truncated' | 'row_cap'>): string {
  const rows = `${section.row_count} ${noun(tab, section.row_count)}`
  return section.truncated
    ? `The newest ${rows}. This window holds more than the ${section.row_cap} shown here.`
    : `${rows} in this window.`
}

export function redactedText(count: number): string | null {
  if (!count) return null
  return `${count} field${count === 1 ? '' : 's'} under a secret-looking key ${count === 1 ? 'was' : 'were'} replaced by a marker before leaving state-api.`
}

export const EMPTY_ALERTS_TEXT = 'The market alert stream holds no alert.'

export function alertsHeldText(count: number, limit: number): string {
  return count >= limit
    ? `The newest ${count} alerts. Any older alert the stream still holds is not read here.`
    : `${count} ${noun('alerts', count)}: every alert the stream holds.`
}
