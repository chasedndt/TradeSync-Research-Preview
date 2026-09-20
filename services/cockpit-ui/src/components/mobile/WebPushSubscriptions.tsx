import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiDelete, apiGet } from '../../api/client'
import type { WebPushSubscriptions as Subscriptions } from '../../api/webPushTypes'
import { exactTime } from './deliveryLedgerText'
import { healthLine, healthTone } from './subscriptionText'
import styles from './WebPushSubscriptions.module.css'

/** The browsers recorded for Web Push: one row per browser, by push service and digest, never by URL. */
export function WebPushSubscriptions({ authorized, onChanged }: { authorized: boolean; onChanged: () => void }) {
  const subscriptions = useQuery({
    queryKey: ['web-push-subscriptions'],
    queryFn: () => apiGet<Subscriptions>('/state/mobile-alerts/web-push/subscriptions'),
    enabled: authorized,
    retry: false,
    refetchInterval: 30000,
  })
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')

  const remove = async (id: string) => {
    setBusy(id)
    setMessage('')
    try {
      await apiDelete(`/state/mobile-alerts/web-push/subscriptions/${id}`)
      await subscriptions.refetch()
      onChanged()
      setMessage('Removed. That browser keeps its own subscription until it is turned off there too.')
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy('')
    }
  }

  if (!authorized) return null

  const rows = subscriptions.data?.subscriptions ?? []
  const toneClass = { good: styles.good, problem: styles.problem, neutral: styles.detail }

  return (
    <section className={styles.list} aria-label="Subscribed browsers">
      <h4 className={styles.title}>Subscribed browsers</h4>
      {subscriptions.isError && <p role="alert" className={styles.note}>{subscriptions.error?.message}</p>}
      {!rows.length && !subscriptions.isError && (
        <p className={styles.note}>No browser has been subscribed. The ntfy app on a phone does not appear here.</p>
      )}
      {rows.map((row) => (
        <article key={row.id} className={styles.row}>
          <div>
            <p className={styles.head}>
              {row.label || 'A browser'} · {row.device_label ?? 'unknown phone'}
              {row.device_enabled === false && ' · phone disabled'}
              {!row.active && ' · expired'}
            </p>
            <p className={styles.detail}>
              {row.push_service ?? 'unknown push service'} · {row.endpoint_digest} · recorded {exactTime(row.created_at)}
            </p>
            <p className={toneClass[healthTone(row)]}>{healthLine(row)}</p>
          </div>
          <button type="button" className="chip" disabled={busy === row.id} onClick={() => void remove(row.id)}>
            Remove
          </button>
        </article>
      ))}
      {rows.length > 0 && <p className={styles.note}>{subscriptions.data?.note}</p>}
      {message && <p role="status" className={styles.note}>{message}</p>}
    </section>
  )
}
