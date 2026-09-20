import { useSearchParams } from 'react-router-dom'
import { useMarketAlerts } from '../api/hooks'
import { useAuditExport } from '../api/hooks/useAuditExport'
import { ActivityTabs } from '../components/activity/ActivityTabs'
import { AlertsPanel } from '../components/activity/AlertsPanel'
import { ApprovalsPanel } from '../components/activity/ApprovalsPanel'
import { DecisionsPanel } from '../components/activity/DecisionsPanel'
import { OrdersPanel } from '../components/activity/OrdersPanel'
import { OutcomesPanel } from '../components/activity/OutcomesPanel'
import {
  ALERT_LIMIT,
  PAGE_ROWS,
  alertCount,
  readingState,
  sectionCount,
  tabFromParam,
  windowDaysFromParam,
  type TabId,
} from '../components/activity/activityFormat'
import styles from './Logs.module.css'

/**
 * Activity & Evidence, served at /logs: decisions, approvals, orders and outcomes from one bounded
 * audit export reading, and the newest market alerts. The tab and window live in the address, so a
 * reading can be linked. Read-only: nothing on this page writes anything.
 */
export function Logs() {
  const [params, setParams] = useSearchParams()
  const tab = tabFromParam(params.get('tab'))
  const days = windowDaysFromParam(params.get('days'))
  const audit = useAuditExport(days, PAGE_ROWS)
  const alerts = useMarketAlerts(ALERT_LIMIT)

  const choose = (key: 'tab' | 'days', value: string) =>
    setParams((current) => {
      const next = new URLSearchParams(current)
      next.set(key, value)
      return next
    }, { replace: true })

  // Counts only from a current reading: a failed refresh leaves the earlier one on screen, not on the tabs.
  const sections = readingState(audit) === 'ready' ? audit.data?.sections : undefined
  const counts: Record<TabId, string | null> = {
    decisions: sectionCount(sections?.decisions),
    approvals: sectionCount(sections?.approvals),
    orders: sectionCount(sections?.orders),
    alerts: readingState(alerts) === 'ready' ? alertCount(alerts.data, ALERT_LIMIT) : null,
    outcomes: sectionCount(sections?.outcomes),
  }
  const auditProps = { query: audit, days, onDays: (value: number) => choose('days', String(value)) }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Activity & Evidence</h2>
        <p className={styles.lead}>
          Decisions, approvals and orders as this system stored them, the market alerts it raised, and what the market did after
          each recorded call. Every tab states when its data was read. Nothing on this page can place, approve, cancel or change anything.
        </p>
      </header>
      <ActivityTabs active={tab} counts={counts} onSelect={(id) => choose('tab', id)} />
      <section id="activity-panel" role="tabpanel" aria-labelledby={`activity-tab-${tab}`} className={`panel ${styles.panel}`}>
        {tab === 'decisions' && <DecisionsPanel {...auditProps} />}
        {tab === 'approvals' && <ApprovalsPanel {...auditProps} />}
        {tab === 'orders' && <OrdersPanel {...auditProps} />}
        {tab === 'alerts' && <AlertsPanel query={alerts} />}
        {tab === 'outcomes' && <OutcomesPanel {...auditProps} />}
      </section>
    </div>
  )
}
