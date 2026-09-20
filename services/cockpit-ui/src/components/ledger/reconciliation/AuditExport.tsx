import { useState } from 'react'
import { getApiBaseUrl } from '../../../api/client'
import { EXPORT_MAX_DAYS, EXPORT_MAX_ROWS, EXPORT_SECTIONS, exportDays, exportUrl } from './reconciliationFormat'
import styles from './AuditExport.module.css'

/** The bounded audit export: every section as JSON, or one section as CSV, over a window the operator chooses. */
export function AuditExport() {
  const [days, setDays] = useState(7)
  const base = getApiBaseUrl()
  const window = exportDays(days)
  const json = exportUrl(base, 'json', window)

  return (
    <div className={styles.export}>
      <h4>Audit export</h4>
      <p className={styles.explain}>
        Decisions, approvals, orders and outcomes over the window you choose, each row with the digests it already stores so it can be checked against the record it came from.
        At most {EXPORT_MAX_ROWS.toLocaleString('en-GB')} rows a section over at most {EXPORT_MAX_DAYS} days; a section that reached its cap says so.
        A field under a secret-looking key is replaced by a marker and counted, never exported.
      </p>
      <label className={styles.days}>
        Window in days
        <input type="number" min={1} max={EXPORT_MAX_DAYS} step={1} value={days} onChange={(event) => setDays(Number(event.target.value))} />
      </label>
      <ul className={styles.links}>
        {json && (
          <li><a href={json} target="_blank" rel="noreferrer">Open every section as JSON ({window} days)</a></li>
        )}
        {EXPORT_SECTIONS.map((section) => {
          const href = exportUrl(base, 'csv', window, section)
          return href ? <li key={section}><a href={href}>Download {section} as CSV ({window} days)</a></li> : null
        })}
      </ul>
      <p className={styles.explain}>
        No order has ever been placed, so the orders section is expected to be empty. A CSV carries its bounds, row count, truncation and content digest in its response headers.
      </p>
    </div>
  )
}
