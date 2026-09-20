import { useState } from 'react'
import { ReadingStamp } from '../ReadingStamp'
import { timezoneLine } from './settingsText'
import styles from './SettingsPanels.module.css'

/**
 * Where each kind of time on the Cockpit comes from. There is no display
 * preference to set, so none is offered: the rules below are fixed, and the one
 * time setting that exists, quiet hours, belongs to each phone.
 */
export function DisplayAndTime() {
  const [now, setNow] = useState(() => Date.now())
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone

  return (
    <section className="panel" aria-labelledby="display-time-title">
      <div className="panel-heading">
        <div>
          <h3 id="display-time-title">Display and time</h3>
          <p>How times are shown. There is no display preference to change.</p>
        </div>
        <ReadingStamp at={now} onRefresh={() => setNow(Date.now())} refreshing={false} />
      </div>
      <div className={styles.body}>
        <dl className={styles.standings}>
          <div>
            <dt>Header clock and reading times</dt>
            <dd className={styles.value}>UTC, to the second</dd>
            <dd>The header clock, and the reading times on the regime summary, liquidations, opportunity briefs and this page, are UTC.</dd>
          </div>
          <div>
            <dt>This browser</dt>
            <dd className={styles.value}>{zone ?? 'not reported'}</dd>
            <dd>{timezoneLine(zone)} Some older panels still show local time, which here reads {new Date(now).toLocaleString()}.</dd>
          </div>
          <div>
            <dt>Notification quiet hours</dt>
            <dd className={styles.value}>Per phone</dd>
            <dd>Each enrolled phone keeps its own quiet hours and timezone, set under Notifications, and state-api applies them before sending.</dd>
          </div>
        </dl>
      </div>
    </section>
  )
}
