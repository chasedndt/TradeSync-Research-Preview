import type { ReconciliationView } from '../../../api/reconciliationTypes'
import { findingLabel, viewStatus, viewTitle, windowText } from './reconciliationFormat'
import styles from './ReconciliationViewCard.module.css'

const LISTED = 20

/** One comparison: what it compared, over what window, how many records, and every finding it made. */
export function ReconciliationViewCard({ view }: { view: ReconciliationView }) {
  const status = viewStatus(view)
  const listed = view.findings.slice(0, LISTED)
  const titleId = `reconciliation-view-${view.name}`
  return (
    <article className={styles.card} aria-labelledby={titleId}>
      <header className={styles.head}>
        <h4 id={titleId}>{viewTitle(view.name)}</h4>
        <span className={`${styles.status} tone-${status.tone}`}>{status.text}</span>
      </header>
      <p className={styles.meta}>Compared {view.compared}</p>
      <p className={styles.meta}>Window {windowText(view.window)} · {view.considered} record{view.considered === 1 ? '' : 's'}</p>
      <p>{view.summary}</p>
      {listed.length > 0 && (
        <ul className={styles.findings}>
          {listed.map((finding, index) => (
            <li key={`${finding.kind}-${finding.subject_id ?? 'none'}-${index}`}>
              <span className={styles.kind}>{findingLabel(finding.kind)}</span> {finding.detail}
              {finding.subject_id && <code className={styles.subject}>{finding.subject_id.slice(0, 12)}</code>}
            </li>
          ))}
        </ul>
      )}
      {view.findings.length > LISTED && (
        <p className={styles.more}>{view.findings.length - LISTED} more findings are in the full API reading.</p>
      )}
      {view.outside_window.length > 0 && (
        <p className={styles.more}>
          {view.outside_window.length} counterpart{view.outside_window.length === 1 ? '' : 's'} fall before this window and are not counted as findings.
        </p>
      )}
    </article>
  )
}
