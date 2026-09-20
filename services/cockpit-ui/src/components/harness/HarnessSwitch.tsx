import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { WarningCircle } from '../icons'
import { useHarnessControl } from '../../api/hooks/useHarnessControl'
import { HarnessChangeDialog } from './HarnessChangeDialog'
import { gatewayLine, hostLine, requestLine, switchView, type Change } from './harnessControlText'
import styles from './HarnessSwitch.module.css'

/**
 * The agent harness kill switch, always in the header: its state, a warning when the gateway disagrees, and the one
 * action it offers (Stop while running, Start while stopped). Hover or focus shows the detail; the name opens the
 * full record on the Agents page.
 */
export function HarnessSwitch() {
  const control = useHarnessControl()
  const [change, setChange] = useState<Change | null>(null)
  const view = switchView(control.data, control.isError)
  const data = control.data

  return (
    <>
      <div className={styles.switch}>
        <NavLink
          to="/agents#agent-harness"
          className={styles.status}
          aria-label={`Agent harness ${view.label}${view.warning ? ', needs attention' : ''}. Open its record on the Agents page.`}
        >
          <i className={`status-dot status-dot--${view.tone}`} aria-hidden="true" />
          <span className={styles.name}>Agent harness</span>
          <strong className={`${styles.label} tone-${view.tone}`}>{view.label}</strong>
          {view.warning && <WarningCircle size={16} weight="fill" className={styles.alert} aria-hidden="true" />}
        </NavLink>
        <button
          type="button"
          className={`${styles.action} ${view.action === 'start' ? styles.start : styles.stop}`}
          disabled={!view.action}
          onClick={() => view.action && setChange(view.action)}
        >
          {view.action === 'start' ? 'Start' : 'Stop'}
        </button>
        <div className={styles.popover} role="tooltip">
          <strong>Agent harness kill switch</strong>
          {data ? (
            <>
              <span>Requested: {requestLine(data.desired)}</span>
              <span>Host: {hostLine(data.host)}</span>
              <span>Gateway: {gatewayLine(data.gateway)}</span>
              <span>TradeSync calls to Hermes: {data.gate.open ? 'allowed' : 'refused'}</span>
              <p className={view.warning ? 'tone-bad' : 'tone-dim'}>{data.agreement.message}</p>
            </>
          ) : (
            <span>{view.warning ?? 'Reading the switch…'}</span>
          )}
        </div>
      </div>
      {change && <HarnessChangeDialog change={change} onClose={() => setChange(null)} />}
    </>
  )
}
