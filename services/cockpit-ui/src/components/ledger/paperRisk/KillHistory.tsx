import type { KillEvent, RiskState } from '../../../api/paperRiskTypes'
import { price, words } from '../paper/paperFormat'
import { utcStamp } from './paperRiskFormat'
import styles from './KillHistory.module.css'

const ACTION: Record<KillEvent['action'], string> = {
  kill: 'Engaged',
  resume: 'Cleared',
  close: 'Closed a position',
}

/** One close under the kill switch: where it filled, whether the book held it first, and what filled it. */
function closeLine(event: KillEvent): string {
  const detail = event.detail ?? {}
  const held = detail.held
    ? `owed from ${utcStamp(detail.fired_at)} and filled ${utcStamp(detail.filled_at)} by the ${words(detail.filled_by)}`
    : 'filled at the quote that engaged it'
  const coincided = detail.coincided_rule ? `; the ${words(detail.coincided_rule)} fired at the same observation` : ''
  return `${detail.symbol ?? 'Paper position'} at ${price(detail.exit_price)}, ${held}${coincided}`
}

/** Every recent kill, resume and close, including an exit the book held owed and a later observation filled. */
export function KillHistory({ risk }: { risk: RiskState }) {
  const events = risk.kill_switch?.recent ?? []
  if (events.length === 0) return null
  return (
    <section className={styles.history} aria-label="Kill switch history">
      <h4>Recent kill switch activity</h4>
      <ul>
        {events.map((event) => (
          <li key={`${event.created_at}-${event.action}-${event.position_id ?? ''}`}>
            <span className={styles.when}>{utcStamp(event.created_at)}</span>
            <strong>{ACTION[event.action]}</strong>
            <span className={styles.what}>{event.action === 'close' ? closeLine(event) : event.reason}</span>
            <span className={styles.who}>by {event.operator}</span>
          </li>
        ))}
      </ul>
      <p>
        A close the displayed book cannot take at once stays owed and fills part by part at later observations. Each row names
        the operator and reason of the kill that owed it, and which loop filled it.
      </p>
    </section>
  )
}
