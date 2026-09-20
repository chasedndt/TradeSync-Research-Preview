import { useEffect, type ReactNode } from 'react'
import { MobileAlerts } from '../components/MobileAlerts'
import { AuditExports } from '../components/settings/AuditExports'
import { ConnectorHealth } from '../components/settings/ConnectorHealth'
import { DataConnections } from '../components/settings/DataConnections'
import { Diagnostics } from '../components/settings/Diagnostics'
import { DisplayAndTime } from '../components/settings/DisplayAndTime'
import { ExecutionMode } from '../components/settings/ExecutionMode'
import { OperatorAccess } from '../components/settings/OperatorAccess'
import { RetentionPolicy } from '../components/settings/RetentionPolicy'
import { RiskPolicySummary } from '../components/settings/RiskPolicySummary'
import { TradingViewPointer } from '../components/settings/TradingViewPointer'
import { WalletConnectSettings } from '../components/settings/WalletConnectSettings'
import { WalletConnections } from '../components/settings/WalletConnections'
import { WalletStatus } from '../components/settings/WalletStatus'
import styles from './Settings.module.css'

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className={styles.section} aria-labelledby={`settings-${id}`}>
      <h3 id={`settings-${id}`} className={styles.sectionTitle}>{title}</h3>
      {children}
    </section>
  )
}

/**
 * Operator settings, grouped by what they govern: access, data connections and
 * connector health, notification devices and quiet hours, execution mode and the
 * wallet, the risk policy, display and time, and retention, exports and
 * diagnostics. Every reading states when it was taken and can be taken again.
 */
export function Settings() {
  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (id) window.requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: 'start' }))
  }, [])

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Settings</h2>
        <p className={styles.lead}>
          Secrets (the webhook secret, API keys, and the values of the operator token and the mobile control key) are set on
          the server in runtime.env and are never configured here. A browser may hold the operator token or the mobile
          control key for its own session, to present them; neither is written to disk or sent anywhere but this
          Cockpit&apos;s state API.
        </p>
      </header>

      <Section id="access" title="Operator and access">
        <OperatorAccess />
      </Section>

      <Section id="connections" title="Data connections and connector health">
        <DataConnections />
        <ConnectorHealth />
        <TradingViewPointer />
      </Section>

      <Section id="notifications" title="Notification devices and quiet hours">
        <MobileAlerts />
      </Section>

      <Section id="wallets" title="Wallets and mobile pairing">
        <WalletConnections />
        <WalletConnectSettings />
      </Section>

      <Section id="execution" title="Execution mode">
        <ExecutionMode />
        <WalletStatus />
      </Section>

      <Section id="risk" title="Risk policy">
        <RiskPolicySummary />
      </Section>

      <Section id="display" title="Display and time">
        <DisplayAndTime />
      </Section>

      <Section id="records" title="Retention, exports and diagnostics">
        <RetentionPolicy />
        <AuditExports />
        <Diagnostics />
      </Section>
    </div>
  )
}
