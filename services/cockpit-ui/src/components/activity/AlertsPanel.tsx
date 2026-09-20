import type { UseQueryResult } from '@tanstack/react-query'
import type { MarketAlert } from '../../api/types'
import { ReadingBar } from './ReadingBar'
import { ReadingNotice } from './ReadingNotice'
import { EvidenceTable, type Column } from './EvidenceTable'
import { ALERT_LIMIT, EMPTY_ALERTS_TEXT, alertsHeldText, msStamp, readingState } from './activityFormat'
import { alertChange, alertMetric, alertType } from './rowFormat'
import styles from './AlertsPanel.module.css'

const COLUMNS: Column<MarketAlert>[] = [
  { id: 'raised', header: 'Raised', cell: (alert) => <span className={styles.mono}>{msStamp(alert.ts)}</span> },
  { id: 'market', header: 'Market', cell: (alert) => alert.symbol },
  { id: 'type', header: 'Type', cell: (alert) => alertType(alert.alert_type) },
  { id: 'metric', header: 'Metric', cell: (alert) => alertMetric(alert.metric) },
  { id: 'change', header: 'Change', cell: (alert) => alertChange(alert.previous_value, alert.new_value) },
]

/**
 * The newest market alerts. The stream has no window and reports no reading time, so this tab offers
 * no window control and states the time the Cockpit received the answer.
 */
export function AlertsPanel({ query }: { query: UseQueryResult<MarketAlert[], Error> }) {
  const alerts = query.data
  const received = msStamp(query.dataUpdatedAt)

  return (
    <div className={styles.panel}>
      <p className={styles.description}>
        Regime changes market-data raised for the configured markets: funding, open interest, volume and trend. They are read
        from a capped Redis stream that keeps recent alerts only and is not a durable record. A market alert carries no delivery
        status: it is not a notification sent to a phone.
      </p>
      <ReadingBar
        label="Received"
        stamp={received}
        detail={`the newest ${ALERT_LIMIT} alerts; the stream reports no reading time of its own`}
        refreshing={false}
        onRefresh={() => void query.refetch()}
      />
      <ReadingNotice state={readingState(query)} message={query.error?.message} readAt={received} />
      {alerts && alerts.length === 0 && <p className={styles.empty}>{EMPTY_ALERTS_TEXT}</p>}
      {alerts && alerts.length > 0 && (
        <>
          <p className={styles.held}>{alertsHeldText(alerts.length, ALERT_LIMIT)}</p>
          <EvidenceTable label="Market alerts" columns={COLUMNS} rows={alerts} rowKey={(alert) => alert.id} />
        </>
      )}
    </div>
  )
}
