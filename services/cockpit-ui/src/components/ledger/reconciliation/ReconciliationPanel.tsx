import { useState } from 'react'
import { useExecutionReconciliation, useReconciliationViews } from '../../../api/hooks/useReconciliation'
import { AuditExport } from './AuditExport'
import { OutcomeMetrics } from './OutcomeMetrics'
import { ReconciliationViewCard } from './ReconciliationViewCard'
import { WINDOW_CHOICES, executionAsView, utcStamp, windowChoiceLabel } from './reconciliationFormat'
import styles from './ReconciliationPanel.module.css'

/**
 * Where this system's own records disagree: the execution reconciliation beside the five other views,
 * then the two outcome measures and the audit export. Every reading shows its exact time. Read-only.
 */
export function ReconciliationPanel() {
  const [hours, setHours] = useState<number>(24)
  const views = useReconciliationViews(hours)
  const execution = useExecutionReconciliation(hours)
  const refreshing = views.isFetching || execution.isFetching
  const data = views.data

  const refresh = () => {
    void views.refetch()
    void execution.refetch()
  }

  return (
    <section className={`panel ${styles.panel}`} aria-labelledby="reconciliation-title">
      <header className={styles.header}>
        <div>
          <h3 id="reconciliation-title">Reconciliation and audit</h3>
          <p>
            Where this system's own records disagree with each other. Each comparison says what it compared and over what window, and one that compared nothing says so rather than reading as clean.
            Nothing here can place, amend, cancel or consume anything.
          </p>
        </div>
        <div className={styles.controls}>
          <label>
            Window
            <select value={hours} onChange={(event) => setHours(Number(event.target.value))}>
              {WINDOW_CHOICES.map((choice) => (
                <option key={choice} value={choice}>{windowChoiceLabel(choice)}</option>
              ))}
            </select>
          </label>
          <span>Reading {data ? utcStamp(data.generated_at) : '—'}</span>
          <button type="button" className="chip" disabled={refreshing} onClick={refresh}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {data && (
        <p className={styles.window}>
          Window {utcStamp(data.window.from)} to {utcStamp(data.window.to)} · {data.summary}
        </p>
      )}
      {views.isLoading && <p>Reading the reconciliation views…</p>}
      {views.isError && <p role="alert" className="tone-bad">Reconciliation views unavailable: {views.error.message}</p>}
      {execution.isError && <p role="alert" className="tone-warn">Execution reconciliation unavailable: {execution.error.message}</p>}

      <div className={styles.grid}>
        {execution.data && <ReconciliationViewCard view={executionAsView(execution.data, execution.dataUpdatedAt)} />}
        {data?.views.map((view) => <ReconciliationViewCard key={view.name} view={view} />)}
      </div>

      {data && (
        <p className={styles.note}>
          {data.note} Each read is limited to {data.row_cap_per_read.toLocaleString('en-GB')} rows.
        </p>
      )}
      <OutcomeMetrics />
      <AuditExport />
    </section>
  )
}
