import { Link } from 'react-router-dom'
import { useExecutionStatus } from '../../api/hooks'
import { usePaperRiskState } from '../../api/hooks/usePaperRisk'
import { modeLine } from '../layout/operatorProfile'
import { codeLabel } from '../ledger/paperRisk/paperRiskFormat'
import { ReadingStamp } from '../ReadingStamp'
import { executorLine, killLine } from './settingsText'
import { StandingRow } from './StandingRow'
import styles from './SettingsPanels.module.css'

/**
 * What the execution gates allow right now: paper or live, whether new paper
 * entries are admitted and what blocks them, the kill switch, and the executor.
 * Read-only by design: every change to these is made where it is audited.
 */
export function ExecutionMode() {
  const status = useExecutionStatus()
  const risk = usePaperRiskState()
  const riskData = risk.isError ? undefined : risk.data
  const hyperliquid = status.data?.venues?.find((venue) => venue.venue === 'hyperliquid')
  const readAt = Math.max(status.dataUpdatedAt || 0, riskData ? riskData.as_of * 1000 : 0) || null

  return (
    <section className="panel" aria-labelledby="execution-mode-title">
      <div className="panel-heading">
        <div>
          <h3 id="execution-mode-title">Execution mode</h3>
          <p>What the gates allow right now. Nothing on this page changes them.</p>
        </div>
        <ReadingStamp
          at={readAt}
          onRefresh={() => { void status.refetch(); void risk.refetch() }}
          refreshing={status.isFetching || risk.isFetching}
        />
      </div>
      <div className={styles.body}>
        <dl className={styles.standings}>
          <StandingRow name="Mode" standing={modeLine(status.data?.execution_enabled, risk.isError ? null : riskData?.pause?.entries_paused)} />
          <StandingRow name="Kill switch" standing={killLine(riskData?.kill_switch, risk.isError)} />
          <StandingRow name="Hyperliquid executor" standing={executorLine(hyperliquid)} />
        </dl>

        {riskData && (riskData.entries_allowed ? (
          <p className={styles.text}>The standing checks admit a new paper entry. {riskData.entries_note}</p>
        ) : (
          <div>
            <p className={styles.text}>New paper entries are refused by:</p>
            <ul className={styles.list}>
              {riskData.blocking.map((refusal) => (
                <li key={refusal.code} className={styles.note}><strong>{codeLabel(refusal.code)}</strong>: {refusal.message}</li>
              ))}
            </ul>
          </div>
        ))}
        {risk.isError && <p className={styles.warn}>Paper risk state unavailable: {(risk.error as Error).message}</p>}

        <p className={styles.note}>
          Pausing, resuming and the kill switch are on the <Link to="/signal-ledger">signal ledger</Link>, where each change
          records the operator and the reason. EXECUTION_ENABLED is an environment setting of the services, not something
          this page can change.
        </p>
      </div>
    </section>
  )
}
