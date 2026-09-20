import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, X } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../api/client'
import { clearMobileControlKey, clearOperatorToken, getApiBaseUrl, getMobileControlKey, getOperatorToken } from '../../api/credentials'
import { useExecutionStatus, useHealth } from '../../api/hooks'
import { useAccessPolicy, useEnrolledPhones } from '../../api/hooks/useOperatorSettings'
import { usePaperRiskState } from '../../api/hooks/usePaperRisk'
import { useQuarantine } from '../../api/hooks/useQuarantine'
import { ReadingStamp } from '../ReadingStamp'
import {
  AUDIT_TRAILS,
  IDENTITY_STATEMENT,
  changeAuthority,
  deviceLine,
  forgetAction,
  identityLine,
  inboxLine,
  modeLine,
  sessionLine,
} from './operatorProfile'
import styles from './OperatorMenu.module.css'

const INBOX_LIMIT = 200

/** The menu's readings, each from a real endpoint, worded by operatorProfile. Opened only on request. */
export function OperatorMenuPanel({ name, onClose }: { name: string; onClose: () => void }) {
  const client = useQueryClient()
  const policy = useAccessPolicy()
  const status = useExecutionStatus()
  const risk = usePaperRiskState()
  const inbox = useQuarantine(true, INBOX_LIMIT)
  const phones = useEnrolledPhones()
  const health = useHealth()
  const [held, setHeld] = useState(() => ({ token: getOperatorToken() !== null, key: getMobileControlKey() !== null }))

  const readings = [policy, status, risk, inbox, phones, health]
  const readAt = Math.max(0, ...readings.map((query) => query.dataUpdatedAt || 0)) || null
  const authority = changeAuthority(policy.data, policy.isError)
  const mode = modeLine(status.data?.execution_enabled, risk.isError ? null : risk.data?.pause?.entries_paused)
  const pending = inbox.data ? inbox.data.items.length : null
  const refused = phones.error instanceof ApiError && phones.error.status === 403
  const devices = phones.data
    ? { total: phones.data.devices.length, enabled: phones.data.devices.filter((device) => device.enabled).length }
    : undefined
  const forget = forgetAction(held.token, held.key)
  const base = getApiBaseUrl()

  const forgetCredentials = () => {
    clearOperatorToken()
    clearMobileControlKey()
    setHeld({ token: false, key: false })
    void client.invalidateQueries()
  }

  return (
    <div id="operator-menu-panel" className={styles.panel} role="dialog" aria-label="Operator">
      <div className={styles.panelHead}>
        <span className={styles.panelIcon}><ShieldCheck size={19} /></span>
        <div><h3>Local workstation</h3><p>Runtime, safety and operator controls</p></div>
        <button type="button" className={styles.close} onClick={onClose} aria-label="Close local controls"><X size={16} /></button>
      </div>
      <p className={styles.statement}>{IDENTITY_STATEMENT}</p>
      <ReadingStamp
        at={readAt}
        onRefresh={() => readings.forEach((query) => { void query.refetch() })}
        refreshing={readings.some((query) => query.isFetching)}
      />

      <dl className={styles.rows}>
        <div>
          <dt>Operator</dt>
          <dd>{identityLine(name)} <Link to="/settings" onClick={onClose}>Settings</Link></dd>
        </div>
        <div>
          <dt>Runtime</dt>
          <dd>
            State API at <code>{base}</code> ·{' '}
            {health.data
              ? `${health.data.status}, database ${health.data.postgres ? 'answering' : 'not answering'}`
              : health.isError ? 'not answering' : 'checking…'}
          </dd>
        </div>
        <div>
          <dt>Change authority</dt>
          <dd><strong className={`tone-${authority.tone}`}>{authority.label}.</strong> {authority.detail}</dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd><strong className={`tone-${mode.tone}`}>{mode.label}.</strong> {mode.detail}</dd>
        </div>
        <div>
          <dt>Held for review</dt>
          <dd>
            {inbox.isLoading ? 'Checking what is held for review…' : inboxLine(pending, pending === INBOX_LIMIT)}{' '}
            <Link to="/intake" onClick={onClose}>Knowledge intake</Link>
          </dd>
        </div>
        <div>
          <dt>Devices and this browser</dt>
          <dd>
            {phones.isLoading ? 'Checking enrolled phones…' : deviceLine(devices, refused)} {sessionLine(held.token, held.key)}
          </dd>
        </div>
      </dl>

      <div className={styles.section}>
        <h4>Control &amp; audit pages</h4>
        <ul className={styles.trails}>
          {AUDIT_TRAILS.map((trail) => (
            <li key={trail.json}>
              <Link to={trail.to} onClick={onClose}><strong>{trail.label}</strong><span>{trail.detail}</span></Link>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.section}>
        <h4>Lock</h4>
        {forget.enabled && <button type="button" className="chip" onClick={forgetCredentials}>{forget.label}</button>}
        <p className={styles.note}>{forget.detail} This local profile is attribution, not an online account.</p>
      </div>
    </div>
  )
}
