import { useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '../../api/client'
import type { MobileDevice } from '../../api/mobileAlertTypes'
import type { WebPushStatus } from '../../api/webPushTypes'
import { CommandBlock } from '../onboarding/CommandBlock'
import { GENERATE_VAPID_KEYS, RECREATE_STATE_API, SET_WEB_PUSH_SUBJECT } from '../onboarding/hostCommands'
import { askPermission, currentSubscription, registerServiceWorker, subscribeHere, unsubscribeHere } from '../../pwa/browserPush'
import { readBrowser, readPermission, supportFrom, type PermissionState, type PushSupport } from '../../pwa/pushSupport'
import { CACHE_NOTE, INSTALL_NOTE, IOS_REQUIREMENT, advice, permissionWord, senderWord, supportWord } from './pwaText'
import styles from './WebPushSetup.module.css'

interface Props {
  devices: MobileDevice[]
  authorized: boolean
  onChanged: () => void
}

/** Notifications in this browser: what it can do, what it has been allowed, and subscribing it to a phone. */
export function WebPushSetup({ devices, authorized, onChanged }: Props) {
  const status = useQuery({
    queryKey: ['web-push-status'],
    queryFn: () => apiGet<WebPushStatus>('/state/mobile-alerts/web-push'),
    refetchInterval: 30000,
  })
  const [support, setSupport] = useState<PushSupport>('unsupported')
  const [permission, setPermission] = useState<PermissionState>('default')
  const [subscribed, setSubscribed] = useState(false)
  const [worker, setWorker] = useState<boolean | null>(null)
  const [device, setDevice] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const enrolled = devices.filter((phone) => phone.enabled)

  const readState = useCallback(async () => {
    setSupport(supportFrom(readBrowser()))
    setPermission(readPermission())
    setWorker((await registerServiceWorker()) !== null)
    setSubscribed((await currentSubscription()) !== null)
  }, [])

  useEffect(() => {
    void readState()
  }, [readState])

  const run = async (work: () => Promise<string>) => {
    setBusy(true)
    setMessage('')
    try {
      setMessage(await work())
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      await readState()
      setBusy(false)
    }
  }

  const allow = () =>
    run(async () => {
      const answer = await askPermission()
      return answer === 'granted'
        ? 'This browser allowed notifications. Subscribe it to an enrolled phone next.'
        : `This browser answered: ${permissionWord(answer)}.`
    })

  const subscribe = () =>
    run(async () => {
      const key = status.data?.public_key
      if (!key) throw new Error('No Web Push public key is configured, so this browser cannot subscribe.')
      if (!device) throw new Error('Choose which enrolled phone this browser belongs to.')
      const material = await subscribeHere(key)
      const saved = await apiPost<{ note?: string; endpoint_digest?: string }>(
        `/state/mobile-alerts/devices/${device}/web-push/subscriptions`,
        { endpoint: material.endpoint, keys: { p256dh: material.p256dh, auth: material.auth }, label: browserLabel() },
      )
      onChanged()
      return `Recorded as ${saved.endpoint_digest}. ${saved.note ?? ''}`.trim()
    })

  const forget = () =>
    run(async () => {
      const dropped = await unsubscribeHere()
      onChanged()
      return dropped
        ? 'This browser dropped its own subscription. Remove its recorded row below as well.'
        : 'This browser had no subscription to drop.'
    })

  const configured = status.data?.configured === true
  const senderReady = status.data?.sender_ready === true
  const next = advice(support, permission, configured, subscribed, senderReady)

  return (
    <section className={styles.setup} aria-label="Notifications in this browser">
      <h4 className={styles.title}>Notifications in this browser (Web Push)</h4>
      <ul className={styles.states}>
        <li>Browser: {supportWord(support)}</li>
        <li>Permission: {permissionWord(permission)}</li>
        <li>Background worker: {worker === null ? 'checking' : worker ? 'registered' : 'not registered here'}</li>
        <li>This browser: {subscribed ? 'subscribed' : 'not subscribed'}</li>
        <li>Key pair on this PC: {status.isLoading ? 'checking' : configured ? 'configured' : 'not configured'}</li>
        <li>Sending: {status.isLoading ? 'checking' : senderWord(configured, senderReady)}</li>
      </ul>

      <p className={styles.headline}>{next.headline}</p>
      <p className={styles.detail}>{next.detail}</p>

      {next.action === 'ask' && (
        <button type="button" className="chip" disabled={busy} onClick={() => void allow()}>
          Allow notifications
        </button>
      )}

      {next.action === 'subscribe' && (
        <div className={styles.row}>
          <label className={styles.field}>
            Phone this browser belongs to
            <select className="input" value={device} onChange={(event) => setDevice(event.target.value)}>
              <option value="">Choose an enrolled phone</option>
              {enrolled.map((phone) => (
                <option key={phone.id} value={phone.id}>
                  {phone.label} · {phone.platform === 'ios' ? 'iPhone' : 'Android'}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="chip" disabled={busy || !authorized || !device} onClick={() => void subscribe()}>
            Subscribe this browser
          </button>
        </div>
      )}

      {next.action === 'server_key' && (
        <>
          <CommandBlock label="Generate and store a Web Push key pair" text={GENERATE_VAPID_KEYS} wrap />
          <CommandBlock label="Recreate state-api" text={RECREATE_STATE_API} wrap />
          {status.data?.problem && <p className={styles.detail}>{status.data.problem}</p>}
        </>
      )}

      {next.action === 'server_contact' && (
        <>
          <CommandBlock label="Store the contact push services are given" text={SET_WEB_PUSH_SUBJECT} wrap />
          <CommandBlock label="Recreate state-api" text={RECREATE_STATE_API} wrap />
          {status.data?.sender_problem && <p className={styles.detail}>{status.data.sender_problem}</p>}
        </>
      )}

      {subscribed && (
        <button type="button" className="chip" disabled={busy} onClick={() => void forget()}>
          Unsubscribe this browser
        </button>
      )}

      <p className={styles.note}>{IOS_REQUIREMENT}</p>
      <p className={styles.note}>{INSTALL_NOTE}</p>
      <p className={styles.note}>{CACHE_NOTE}</p>
      {!authorized && <p className={styles.note}>Enter the mobile control key above before subscribing a browser.</p>}
      {message && (
        <p role="status" className={styles.message}>
          {message}
        </p>
      )}
    </section>
  )
}

/** A name for this browser that helps tell two rows apart, with nothing identifying in it. */
function browserLabel(): string {
  const agent = typeof navigator === 'undefined' ? '' : navigator.userAgent
  const name = /edg/i.test(agent) ? 'Edge'
    : /chrome/i.test(agent) ? 'Chrome'
      : /firefox/i.test(agent) ? 'Firefox'
        : /safari/i.test(agent) ? 'Safari' : 'Browser'
  const platform = /android/i.test(agent) ? 'Android' : /iphone|ipad/i.test(agent) ? 'iOS' : 'desktop'
  return `${name} on ${platform}`
}
