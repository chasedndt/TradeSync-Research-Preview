import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useHarnessControl } from '../../api/hooks/useHarnessControl'
import { HarnessChangeDialog } from './HarnessChangeDialog'
import { HarnessHistory } from './HarnessHistory'
import { SCOPE_NOTE, agreementTone, gatewayLine, hostLine, requestLine, switchView, type Change } from './harnessControlText'
import styles from './HarnessControlPanel.module.css'

/**
 * The agent harness kill switch on the Agents page: what was asked for and by whom, what the host control process did,
 * whether the gateway still answers, whether TradeSync calls Hermes, one sentence on whether these agree, and the history.
 */
export function HarnessControlPanel() {
  const control = useHarnessControl()
  const location = useLocation()
  const sectionRef = useRef<HTMLElement | null>(null)
  const [change, setChange] = useState<Change | null>(null)
  const data = control.data
  const view = switchView(data, control.isError)
  const disagree = data?.agreement.state === 'disagree'

  useEffect(() => {
    if (location.hash === '#agent-harness') sectionRef.current?.scrollIntoView({ block: 'start' })
  }, [location.hash])

  return (
    <section id="agent-harness" ref={sectionRef} className={`panel ${styles.panel}`} aria-labelledby="agent-harness-title">
      <div className={styles.head}>
        <div>
          <h2 id="agent-harness-title">Agent harness kill switch</h2>
          <p>Stops and starts the Hermes gateway on this PC. Paper trading and market data never depend on it.</p>
        </div>
        <span className={`${styles.state} tone-${view.tone}`}>{view.label.toUpperCase()}</span>
      </div>
      {control.isError && <p className={styles.error}>{control.error?.message}</p>}
      {data && (
        <>
          <dl className={styles.grid}>
            <div className={styles.cell}>
              <dt>Requested</dt>
              <dd>{requestLine(data.desired)}</dd>
              <dd className={styles.muted}>{data.desired.reason}</dd>
            </div>
            <div className={styles.cell}>
              <dt>Host control process</dt>
              <dd>{hostLine(data.host)}</dd>
              {data.host.result?.detail && <dd className={styles.muted}>{data.host.result.detail}</dd>}
            </div>
            <div className={styles.cell}>
              <dt>Gateway health</dt>
              <dd>{gatewayLine(data.gateway)}</dd>
              {data.gateway.status === 'offline' && data.gateway.last_error && <dd className={styles.muted}>{data.gateway.last_error}</dd>}
            </div>
            <div className={styles.cell}>
              <dt>TradeSync calls to Hermes</dt>
              <dd className={data.gate.open ? 'tone-good' : 'tone-bad'}>{data.gate.open ? 'Allowed' : 'Refused while stopped'}</dd>
            </div>
          </dl>
          <p className={`${styles.agreement} tone-${agreementTone(data.agreement.state)}`} role={disagree ? 'alert' : 'status'}>
            {data.agreement.message}
          </p>
          <div className={styles.actions}>
            {data.desired.state === 'running' ? (
              <>
                <button type="button" className={`chip ${styles.stop}`} onClick={() => setChange('stop')}>Stop agent harness</button>
                {disagree && <button type="button" className={`chip ${styles.start}`} onClick={() => setChange('start')}>Start again</button>}
              </>
            ) : (
              <>
                <button type="button" className={`chip ${styles.start}`} onClick={() => setChange('start')}>Start agent harness</button>
                {disagree && <button type="button" className={`chip ${styles.stop}`} onClick={() => setChange('stop')}>Stop again</button>}
              </>
            )}
          </div>
          <p className={styles.note}>{SCOPE_NOTE}</p>
          <HarnessHistory events={data.history} />
        </>
      )}
      {change && <HarnessChangeDialog change={change} onClose={() => setChange(null)} />}
    </section>
  )
}
