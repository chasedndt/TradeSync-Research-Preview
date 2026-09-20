import { Fragment } from 'react'
import type { BriefCondition, OpportunityBrief } from '../../../api/opportunityBriefTypes'
import { atSeconds, conditionMark, conditionTone, conditionValue, fitTone, fitWords } from './briefText'
import styles from './Brief.module.css'

/**
 * How the side sat against the regime recorded before entry, and each entry
 * condition with the value stored, the value it needed, and whether it was met.
 * The comparisons are the gate's own, restated by the state API on the stored
 * values; nothing is recalculated here.
 */
export function BriefEntryConditions({ brief }: { brief: OpportunityBrief }) {
  const { entry, regime_fit: fit } = brief

  return (
    <section className="panel" aria-labelledby="brief-entry-title">
      <div className="panel-heading">
        <div>
          <h3 id="brief-entry-title">Regime fit and entry conditions</h3>
          <p>{entry.detail}</p>
        </div>
      </div>
      <div className={styles.body}>
        <div className={styles.block}>
          <h4 className={styles.blockTitle}>
            Regime fit: <span className={`tone-${fitTone(fit.fit)}`}>{fitWords(fit.fit)}</span>
          </h4>
          <p className={styles.text}>{fit.detail}</p>
          {fit.trailing_return_pct != null && (
            <p className={styles.note}>
              Trailing move {fit.trailing_return_pct.toFixed(2)}% over {fit.lookback_minutes ?? '—'} minutes, labelled{' '}
              {atSeconds(fit.computed_at_s)}.
            </p>
          )}
          <p className={styles.note}>Basis: {fit.basis}.</p>
        </div>

        {entry.schema === 'legacy' ? null : (
          <div className="table-scroll">
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Condition</th>
                  <th scope="col">Stored value</th>
                  <th scope="col">Needed</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {entry.conditions.map((condition) => <ConditionRows key={condition.code} condition={condition} />)}
              </tbody>
            </table>
          </div>
        )}

        {entry.rejection_reasons.length > 0 && (
          <div className={styles.block}>
            <h4 className={styles.blockTitle}>Reasons the gate recorded against it</h4>
            <ul className={styles.reasons}>
              {entry.rejection_reasons.map((reason) => (
                <li key={reason.code}>{reason.detail ?? reason.code}</li>
              ))}
            </ul>
          </div>
        )}
        {entry.policy_note && <p className={styles.note}>{entry.policy_note}</p>}
      </div>
    </section>
  )
}

function ConditionRows({ condition }: { condition: BriefCondition }) {
  const needs = condition.comparator === '>=' ? 'at least' : 'at most'
  return (
    <Fragment>
      <tr>
        <th scope="row">{condition.label}</th>
        <td className={styles.mono}>{conditionValue(condition.measured, condition.unit)}</td>
        <td className={styles.mono}>{needs} {conditionValue(condition.required, condition.unit)}</td>
        <td className={`tone-${conditionTone(condition.met)}`}>{conditionMark(condition.met)}</td>
      </tr>
      <tr className={styles.basisRow}>
        <td colSpan={4}>{condition.basis}</td>
      </tr>
    </Fragment>
  )
}
