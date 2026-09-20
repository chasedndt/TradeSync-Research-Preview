import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../api/client'
import type { DeliveryLedger as Ledger, LedgerEvent } from '../../api/mobileAlertTypes'
import {
  acknowledgementLine,
  attemptLine,
  canAcknowledge,
  canConfirmReceipt,
  deadLetterLine,
  exactTime,
  providerLine,
  reference,
  retryLadder,
  statusWord,
  transportWord,
} from './deliveryLedgerText'
import styles from './DeliveryLedger.module.css'

const CONFIRM_PROMPT = 'Have you actually received this reference on the specified phone? '
  + 'This records your attestation, not automated device telemetry.'

/** Every notification and what happened to it: attempts, the last error, acknowledgement, dead letters, times. */
export function DeliveryLedger({ authorized, onChanged }: { authorized: boolean; onChanged: () => void }) {
  const ledger = useQuery({
    queryKey: ['mobile-delivery-ledger'],
    queryFn: () => apiGet<Ledger>('/state/mobile-alerts/ledger'),
    enabled: authorized,
    retry: false,
    refetchInterval: 15000,
  })
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')

  const act = async (event: LedgerEvent, path: string, body: unknown, prompt?: string) => {
    if (prompt && !window.confirm(prompt)) return
    setBusy(event.id)
    setMessage('')
    try {
      const answer = await apiPost<{ note?: string; outcome?: string; status?: string }>(path, body)
      setMessage(answer.note ?? answer.outcome ?? answer.status ?? 'Recorded')
      await ledger.refetch()
      onChanged()
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy('')
    }
  }

  if (!authorized) return null

  const events = ledger.data?.events ?? []
  const maxAttempts = ledger.data?.max_attempts ?? 0

  return (
    <section className={styles.ledger} aria-label="Delivery ledger">
      <div className={styles.head}>
        <h4 className={styles.title}>Delivery ledger</h4>
        <span className={styles.read}>
          Read at {exactTime(new Date(ledger.dataUpdatedAt || Date.now()).toISOString())}
          <button type="button" className="chip" disabled={ledger.isFetching} onClick={() => void ledger.refetch()}>
            Refresh
          </button>
        </span>
      </div>
      {ledger.isError && <p role="alert" className={styles.note}>{ledger.error?.message}</p>}
      {!events.length && !ledger.isError && <p className={styles.note}>No notification attempts recorded.</p>}

      {events.map((event) => (
        <article key={event.id} className={styles.row}>
          <p className={styles.headline}>
            Reference {reference(event)} · {event.kind === 'test' ? 'test' : 'attention'} · {statusWord(event.status)}
            {event.transport ? ` · ${transportWord(event.transport)}` : ''}
            {event.device_label ? ` · ${event.device_label}` : ''}
          </p>
          <p className={styles.detail}>
            Queued {exactTime(event.created_at)} · {attemptLine(event, maxAttempts)}
          </p>
          {providerLine(event) && <p className={styles.detail}>{providerLine(event)}</p>}
          {event.last_error && <p className={styles.problem}>Last error: {event.last_error}</p>}
          {deadLetterLine(event) && <p className={styles.problem}>{deadLetterLine(event)}</p>}
          {acknowledgementLine(event) && <p className={styles.good}>{acknowledgementLine(event)}</p>}
          <div className={styles.actions}>
            {canConfirmReceipt(event) && (
              <button
                type="button"
                className="chip"
                disabled={busy === event.id}
                onClick={() => void act(event, `/state/mobile-alerts/events/${event.id}/confirm`, {}, CONFIRM_PROMPT)}
              >
                I received this on my phone
              </button>
            )}
            {canAcknowledge(event) && (
              <button
                type="button"
                className="chip"
                disabled={busy === event.id}
                onClick={() => void act(event, `/state/mobile-alerts/events/${event.id}/acknowledge`, { by: 'operator' })}
              >
                Mark seen
              </button>
            )}
          </div>
        </article>
      ))}

      {ledger.data && (
        <p className={styles.note}>
          Retries wait {retryLadder(ledger.data.retry_seconds)} and stop after {ledger.data.max_attempts} attempts;
          anything still undelivered {ledger.data.expiry_seconds / 60} minutes after it was queued expires.
          {' '}
          {ledger.data.note}
        </p>
      )}
      {message && <p role="status" className={styles.note}>{message}</p>}
    </section>
  )
}
