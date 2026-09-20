import { staleText, unansweredText, type ReadingState } from './activityFormat'
import styles from './ReadingNotice.module.css'

interface ReadingNoticeProps {
  state: ReadingState
  message?: string
  /** When the reading still on screen was taken, for a refresh that failed. */
  readAt: string
}

const NO_REASON = 'no reason was given'

/** Says a reading is on its way, failed, or is an earlier one kept after a failed refresh. Silent when current. */
export function ReadingNotice({ state, message, readAt }: ReadingNoticeProps) {
  if (state === 'reading') return <p className={styles.reading}>Reading…</p>
  if (state === 'unanswered') {
    return <p role="alert" className={`${styles.notice} tone-bad`}>{unansweredText(message || NO_REASON)}</p>
  }
  if (state === 'stale') {
    return <p role="alert" className={`${styles.notice} tone-warn`}>{staleText(message || NO_REASON, readAt)}</p>
  }
  return null
}
