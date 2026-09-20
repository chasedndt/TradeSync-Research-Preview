import { WINDOW_DAYS, windowDaysLabel } from './activityFormat'
import styles from './ReadingBar.module.css'

interface ReadingBarProps {
  /** "Read" for a time the API reports, "Received" for the time the Cockpit got an answer. */
  label: string
  stamp: string
  detail?: string
  /** The window control appears only for a reading whose query it actually changes. */
  days?: number
  onDays?: (days: number) => void
  refreshing: boolean
  onRefresh: () => void
}

/** The exact time a tab's data was read, the window it covers, and the controls that change it. */
export function ReadingBar({ label, stamp, detail, days, onDays, refreshing, onRefresh }: ReadingBarProps) {
  return (
    <div className={styles.bar}>
      <p className={styles.time}>
        {label} <strong>{stamp}</strong>
        {detail && <span className={styles.detail}> · {detail}</span>}
      </p>
      <div className={styles.controls}>
        {days !== undefined && onDays && (
          <label>
            Window
            <select value={days} onChange={(event) => onDays(Number(event.target.value))}>
              {WINDOW_DAYS.map((choice) => (
                <option key={choice} value={choice}>{windowDaysLabel(choice)}</option>
              ))}
            </select>
          </label>
        )}
        <button type="button" className="chip" disabled={refreshing} onClick={onRefresh}>
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}
