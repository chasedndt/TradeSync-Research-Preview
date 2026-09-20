import type { RegimeSummary } from '../../../api/regimeSummaryTypes'
import { confidenceTone, regimeWords } from './regimeSummaryText'
import styles from './Regime.module.css'

const FILL: Record<string, string> = { good: styles.barFill, warn: styles.barFillWarn, bad: styles.barFillBad }

/**
 * The regime as it stands, how much evidence is behind it, and every reason
 * that confidence is not higher. When the condition is not classified, the
 * inputs that are missing are named here rather than left to the reader.
 */
export function RegimeConfidence({ summary }: { summary: RegimeSummary }) {
  const { confidence, current } = summary
  const tone = confidenceTone(confidence.level)

  return (
    <div className={styles.section}>
      <div className={styles.condition}>
        <span className={styles.conditionLabel}>{current.label}</span>
        <span className={`${styles.level} tone-${tone}`}>{confidence.level} confidence</span>
        <span className={styles.conditionMeta}>
          Trend {regimeWords(current.trend)} · {current.trend_basis}
        </span>
      </div>

      <div className={styles.bar} role="img" aria-label={`${confidence.usable_inputs} of ${confidence.required_inputs} required inputs usable`}>
        <span className={FILL[tone]} style={{ width: `${Math.round(confidence.share_usable * 100)}%` }} />
      </div>
      <p className={styles.note}>
        {confidence.usable_inputs} of {confidence.required_inputs} required inputs were usable. Confidence is {confidence.basis}
        {confidence.reported_by_market_data ? ` · market-data reported "${confidence.reported_by_market_data}"` : ''}.
      </p>

      {summary.missing_inputs.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>
            {current.known ? 'Inputs the classifier could not use' : 'Why the regime is not classified'}
          </h4>
          <ul className={styles.missing}>
            {summary.missing_inputs.map((item) => (
              <li key={item.input} className={styles.missingItem}>
                <span className={styles.missingName}>{item.label}</span>
                <span className={styles.missingReason}>{item.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.conflicts.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>Readings that disagree</h4>
          <ul className={styles.reasons}>
            {summary.conflicts.map((conflict) => (
              <li key={conflict.inputs.join('-')}>{conflict.detail}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={styles.section}>
        <h4 className={styles.sectionTitle}>Why not higher confidence</h4>
        {summary.why_not_higher.length > 0 ? (
          <ul className={styles.reasons}>
            {summary.why_not_higher.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        ) : (
          <p className={styles.empty}>
            Nothing is holding it back: every required input was read, fresh and in agreement. This is the highest
            confidence the classifier reports.
          </p>
        )}
      </div>
    </div>
  )
}
