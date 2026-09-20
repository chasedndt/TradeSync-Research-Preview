import type { ExecutionReconciliation, ReconciliationView, RegimeFitVerdict } from '../../../api/reconciliationTypes'
import { codeLabel, utcStamp } from '../paperRisk/paperRiskFormat'

/** Pure formatting for the reconciliation and audit panel; no React, so the node tests can import it. */

export { utcStamp }

export type Tone = 'good' | 'warn' | 'dim'

const TITLES: Record<string, string> = {
  decisions_against_orders: 'Decisions against orders',
  orphaned_events: 'Orphaned events',
  duplicate_candidates: 'Duplicate candidates',
  stale_approvals: 'Stale approvals',
  partial_orders: 'Partial orders',
  missing_outcomes: 'Missing outcomes',
}

export function viewTitle(name: string): string {
  return TITLES[name] ?? codeLabel(name)
}

export function findingLabel(kind: string): string {
  return codeLabel(kind)
}

/** A view that compared nothing is not a clean view, and the status says which one it is. */
export function viewStatus(view: Pick<ReconciliationView, 'considered' | 'findings'>): { text: string; tone: Tone } {
  if (view.considered === 0) return { text: 'Nothing compared', tone: 'dim' }
  const count = view.findings.length
  if (count === 0) return { text: 'Clean', tone: 'good' }
  return { text: `${count} finding${count === 1 ? '' : 's'}`, tone: 'warn' }
}

const ISO_WINDOW = /^(\S+) to (\S+) \((\d+)h\)$/

/** A view's window with both ends as exact UTC times; any other form is shown as it came. */
export function windowText(window: string): string {
  const match = ISO_WINDOW.exec(window.trim())
  if (!match) return window
  const [, from, to, hours] = match
  const start = utcStamp(from)
  const end = utcStamp(to)
  return start === '—' || end === '—' ? window : `${start} to ${end} (${hours}h)`
}

/**
 * The execution reconciliation in the shape of a view, so it sits beside the other five.
 * That route reports no time of its own, so its window is stated from when the Cockpit received it.
 */
export function executionAsView(result: ExecutionReconciliation, receivedAtMs: number): ReconciliationView {
  const received = Number.isFinite(receivedAtMs) && receivedAtMs > 0 ? utcStamp(receivedAtMs / 1000) : '—'
  return {
    name: 'decisions_against_orders',
    compared: 'recorded decisions against recorded orders: symbol, side, size and venue',
    window: `the ${result.window_hours}h before the reading received ${received}`,
    considered: result.decisions + result.orders,
    clean: result.clean,
    findings: result.divergences.map((divergence) => ({
      kind: divergence.kind,
      subject_id: divergence.decision_id ?? divergence.order_id,
      detail: divergence.field ? `${divergence.detail} (${divergence.field})` : divergence.detail,
      observed: {},
    })),
    outside_window: result.orders_outside_window,
    summary: result.summary,
  }
}

export const WINDOW_CHOICES = [1, 6, 24, 72, 168, 720] as const

export function windowChoiceLabel(hours: number): string {
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'}`
  const days = hours / 24
  return `${days} day${days === 1 ? '' : 's'}`
}

// A departure is a check that failed, so it reads as what went wrong rather than as the check's name:
// "stop respected" listed under departures would say the opposite of what happened.
const DEPARTURES: Record<string, string> = {
  entry_in_zone: 'entry outside its zone',
  stop_respected: 'stop passed without the stop firing',
  target_respected: 'target claimed but not reached',
  time_respected: 'held past its expiry',
  exit_rule_declared: 'exit by an undeclared rule',
}

export function departureText(names: string[]): string {
  return names.map((name) => DEPARTURES[name] ?? codeLabel(name)).join('; ')
}

/** A measured ratio as a percentage. No measurement is a dash, never 0%: a real zero still reads as 0.0%. */
export function ratioText(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '—' : `${(value * 100).toFixed(1)}%`
}

const ABSTENTION_WORDS: Record<RegimeFitVerdict, string> = {
  fit: 'fit',
  misfit: 'misfit',
  undeclared: 'no expectation declared by the rulebook',
  unlabelled: 'no entry regime labelled',
  digest_mismatch: 'scored under a different rulebook',
  rulebook_altered: 'rulebook no longer matches its digest',
  undirected: 'no expectation for that side',
  no_rulebook: 'rulebook not held',
}

/** Why calls were not judged, each reason counted, because each has a different remedy. */
export function abstentionText(byReason: Partial<Record<RegimeFitVerdict, number>>): string {
  const parts = Object.entries(byReason)
    .filter(([, count]) => typeof count === 'number' && count > 0)
    .map(([reason, count]) => `${count} ${ABSTENTION_WORDS[reason as RegimeFitVerdict] ?? codeLabel(reason)}`)
  return parts.length ? `abstained: ${parts.join(', ')}` : 'none abstained'
}

// The export's bounds mirror state-api (tradesync_core.audit_export); the API refuses anything wider.
export const EXPORT_SECTIONS = ['decisions', 'approvals', 'orders', 'outcomes'] as const
export type ExportSection = (typeof EXPORT_SECTIONS)[number]
export const EXPORT_MAX_DAYS = 31
export const EXPORT_MAX_ROWS = 5000

export function exportDays(value: number): number {
  if (!Number.isFinite(value)) return 7
  return Math.min(EXPORT_MAX_DAYS, Math.max(1, Math.round(value)))
}

/** The export's address on this API: JSON for every section, or one section as CSV. */
export function exportUrl(base: string, format: 'json' | 'csv', days: number, section?: ExportSection): string | null {
  const window = exportDays(days)
  if (format === 'json') return `${base}/state/audit/export?days=${window}`
  if (!section || !(EXPORT_SECTIONS as readonly string[]).includes(section)) return null
  return `${base}/state/audit/export.csv?section=${section}&days=${window}`
}
