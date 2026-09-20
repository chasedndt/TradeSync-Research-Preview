import type { RegimeSummary } from '../../../api/regimeSummaryTypes'
import { exactUtc, heldLine, regimeWords } from './regimeSummaryText'
import styles from './Regime.module.css'

/**
 * How the recorded regime has changed. These labels come from
 * `opportunity_entry_regimes`: each was computed from candles that had closed
 * before its own opportunity's entry, so none of them contains a price from
 * after the decision it describes.
 */
export function RegimeHistory({ summary }: { summary: RegimeSummary }) {
  const { transitions, held, readings } = summary.history

  return (
    <div className={styles.section}>
      <h4 className={styles.sectionTitle}>Recorded regime and how it changed</h4>
      <p className={styles.note}>{heldLine(summary)}</p>
      {transitions.length > 0 ? (
        <ul className={styles.transitions}>
          {transitions.map((transition) => (
            <li key={`${transition.at_ms}-${transition.to}`}>
              <span>{regimeWords(transition.from)} → {regimeWords(transition.to)}</span>
              <span className={styles.transitionAt}>{exactUtc(transition.at_ms)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.empty}>
          {readings > 0
            ? 'The recorded regime has not changed across the readings held.'
            : 'No change to show yet: a regime is recorded when an opportunity is scored for this market.'}
        </p>
      )}
      {held && <p className={styles.note}>Basis: {held.basis}.</p>}
    </div>
  )
}
