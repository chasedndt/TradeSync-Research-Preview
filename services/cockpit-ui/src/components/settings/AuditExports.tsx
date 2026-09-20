import { Link } from 'react-router-dom'
import { getApiBaseUrl } from '../../api/credentials'
import { AUDIT_TRAILS } from '../layout/operatorProfile'
import styles from './SettingsPanels.module.css'

/**
 * Audited records and their exports. Each export is the record itself, served
 * read-only by state-api as JSON: no file is generated, nothing is summarised on
 * the way out, and reading one needs no operator token and changes nothing.
 */
export function AuditExports() {
  const base = getApiBaseUrl()

  return (
    <section className="panel" aria-labelledby="audit-exports-title">
      <div className="panel-heading">
        <div>
          <h3 id="audit-exports-title">Audit records and exports</h3>
          <p>Open a record in the Cockpit, or open the record itself as JSON to keep a copy.</p>
        </div>
      </div>
      <div className={styles.body}>
        <ul className={styles.list}>
          {AUDIT_TRAILS.map((trail) => (
            <li key={trail.json} className={styles.item}>
              <span>
                <strong>{trail.label}</strong>
                <span className={styles.sub}>{trail.detail}</span>
              </span>
              <span className={styles.links}>
                <Link to={trail.to}>Open</Link>
                <a href={`${base}${trail.json}`} target="_blank" rel="noopener noreferrer">JSON</a>
              </span>
            </li>
          ))}
        </ul>
        <p className={styles.note}>Reading a record needs no operator token and changes nothing on the server.</p>
      </div>
    </section>
  )
}
