import type { ReactNode } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'
import { getApiBaseUrl } from '../../api/client'
import type { AuditExportReading, AuditSectionName } from '../../api/activityTypes'
import { EXPORT_MAX_ROWS, exportUrl } from '../ledger/reconciliation/reconciliationFormat'
import { ReadingBar } from './ReadingBar'
import { ReadingNotice } from './ReadingNotice'
import { emptySectionText, heldText, noun, readingState, redactedText, utcStamp, windowDaysLabel } from './activityFormat'
import styles from './AuditSectionPanel.module.css'

/** What every audit tab is given: the one export reading the four tabs share, and its window. */
export interface AuditPanelProps {
  query: UseQueryResult<AuditExportReading, Error>
  days: number
  onDays: (days: number) => void
}

type Sections = AuditExportReading['sections']

interface AuditSectionPanelProps<K extends AuditSectionName> extends AuditPanelProps {
  tab: K
  description: ReactNode
  /** The section's rows, rendered only when the reading holds at least one. */
  children: (section: Sections[K]) => ReactNode
}

/**
 * One section of the audit export: when it was read and over what window, then its rows, or a statement
 * that the window holds none, or that the request failed. Those three never read as each other.
 */
export function AuditSectionPanel<K extends AuditSectionName>({ tab, description, query, days, onDays, children }: AuditSectionPanelProps<K>) {
  const reading = query.data
  const section = reading?.sections[tab]
  const readAt = reading ? utcStamp(reading.generated_at) : '—'
  const redacted = section ? redactedText(section.redacted_fields) : null
  const csv = section && section.row_count > 0 ? exportUrl(getApiBaseUrl(), 'csv', days, tab) : null

  return (
    <div className={styles.panel}>
      <p className={styles.description}>{description}</p>
      <ReadingBar
        label="Read"
        stamp={readAt}
        detail={reading ? `window ${utcStamp(reading.window.from)} to ${utcStamp(reading.window.to)}` : undefined}
        days={days}
        onDays={onDays}
        refreshing={query.isFetching}
        onRefresh={() => void query.refetch()}
      />
      <ReadingNotice state={readingState(query)} message={query.error?.message} readAt={readAt} />
      {reading && section && section.row_count === 0 && (
        <p className={styles.empty}>{emptySectionText(tab, reading.window)}</p>
      )}
      {section && section.row_count > 0 && (
        <>
          <p className={styles.held}>{heldText(tab, section)}</p>
          {children(section)}
        </>
      )}
      {(redacted || csv) && (
        <footer className={styles.footer}>
          {redacted && <p>{redacted}</p>}
          {csv && (
            <a href={csv}>
              Download the {noun(tab, 2)} of the last {windowDaysLabel(days)} as CSV, up to {EXPORT_MAX_ROWS.toLocaleString('en-GB')} rows
            </a>
          )}
        </footer>
      )}
    </div>
  )
}
