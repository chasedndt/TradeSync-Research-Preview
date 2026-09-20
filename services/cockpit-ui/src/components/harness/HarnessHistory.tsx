import type { HarnessControlEvent } from '../../api/harnessControlTypes'
import { eventLine, utcStamp } from './harnessControlText'
import styles from './HarnessHistory.module.css'

/** Every stop and start request, claim and result, newest first, as state-api's audit keeps them. */
export function HarnessHistory({ events }: { events: HarnessControlEvent[] }) {
  return (
    <div className={styles.history}>
      <h3>History</h3>
      {events.length === 0 ? (
        <p className={styles.empty}>No stop or start has been requested yet.</p>
      ) : (
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr><th>time</th><th>event</th><th>detail</th></tr>
            </thead>
            <tbody>
              {events.map((event) => {
                const line = eventLine(event)
                return (
                  <tr key={event.id}>
                    <td className={styles.time}>{utcStamp(event.created_at)}</td>
                    <td>{line.title}</td>
                    <td className={styles.detail}>{line.detail || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
