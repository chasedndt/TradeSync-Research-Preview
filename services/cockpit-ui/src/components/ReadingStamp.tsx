import { exactUtc } from './market/readingTime'
import styles from './ReadingStamp.module.css'

/**
 * When a reading was taken, to the second in UTC, beside the control that takes
 * it again. `at` is in milliseconds; a reading not yet taken says so.
 */
export function ReadingStamp({
  at,
  onRefresh,
  refreshing,
}: {
  at: number | null | undefined
  onRefresh: () => void
  refreshing: boolean
}) {
  return (
    <span className={styles.stamp}>
      <span className={styles.time}>{at ? `Read ${exactUtc(at)}` : 'Not read yet'}</span>
      <button type="button" className="chip" onClick={onRefresh} disabled={refreshing}>
        {refreshing ? 'Refreshing…' : 'Refresh'}
      </button>
    </span>
  )
}
