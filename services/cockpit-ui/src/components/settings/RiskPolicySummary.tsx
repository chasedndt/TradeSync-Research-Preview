import { Link } from 'react-router-dom'
import { usePaperLimits, usePaperRules } from '../../api/hooks/useOperatorSettings'
import { duration } from '../ledger/paper/paperFormat'
import { LIMIT_FIELDS, ageText, limitText, utcStamp } from '../ledger/paperRisk/paperRiskFormat'
import { ReadingStamp } from '../ReadingStamp'
import styles from './SettingsPanels.module.css'

/**
 * The paper risk policy in force: the limits every new paper entry is checked
 * against, with who last changed them and why, and the versioned rules each
 * paper plan is fixed under. A summary to read; limits change on the signal ledger.
 */
export function RiskPolicySummary() {
  const limits = usePaperLimits()
  const rules = usePaperRules()

  return (
    <section className="panel" aria-labelledby="risk-policy-title">
      <div className="panel-heading">
        <div>
          <h3 id="risk-policy-title">Paper risk policy</h3>
          <p>The limits every new paper entry is checked against, and the rules each paper plan is fixed under.</p>
        </div>
        <ReadingStamp
          at={limits.dataUpdatedAt || null}
          onRefresh={() => { void limits.refetch(); void rules.refetch() }}
          refreshing={limits.isFetching || rules.isFetching}
        />
      </div>
      <div className={styles.body}>
        {limits.isError && <p className={styles.warn}>Paper limits unavailable: {(limits.error as Error).message}</p>}
        {limits.data && (
          <>
            <div className="table-scroll">
              <table className={styles.table}>
                <thead><tr><th scope="col">Limit</th><th scope="col">In force</th></tr></thead>
                <tbody>
                  {LIMIT_FIELDS.map((field) => (
                    <tr key={field.key}>
                      <th scope="row">{field.label}</th>
                      <td className={styles.mono}>{limitText(field, limits.data.limits[field.key])}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={styles.note}>
              Last changed by {limits.data.operator} at {utcStamp(limits.data.updated_at)}: {limits.data.reason}. {limits.data.note}
            </p>
          </>
        )}

        {rules.data && (
          <>
            <div className="table-scroll">
              <table className={styles.table}>
                <thead>
                  <tr><th scope="col">Holding style</th><th scope="col">Stop</th><th scope="col">Target</th><th scope="col">Longest hold</th></tr>
                </thead>
                <tbody>
                  {Object.entries(rules.data.styles).map(([style, rule]) => (
                    <tr key={style}>
                      <th scope="row">{style}</th>
                      <td className={styles.mono}>{rule.stop_atr} × ATR on {rule.atr_interval}</td>
                      <td className={styles.mono}>{rule.reward_risk} × the stop distance, at least {rule.min_target_pct}%</td>
                      <td className={styles.mono}>{duration(rule.max_hold_s)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={styles.note}>
              Every entry: notional at most {rules.data.common.max_notional_usdc} USDC, planned risk at most{' '}
              {rules.data.common.max_planned_risk_usdc} USDC, from an opportunity no older than{' '}
              {ageText(rules.data.common.max_opportunity_age_s)}. Rules {rules.data.version}.
            </p>
          </>
        )}
        {rules.isError && <p className={styles.warn}>Paper lifecycle rules unavailable: {(rules.error as Error).message}</p>}

        <p className={styles.note}>
          Limits change on the <Link to="/signal-ledger">signal ledger</Link>, where each change records the operator and the reason.
        </p>
      </div>
    </section>
  )
}
