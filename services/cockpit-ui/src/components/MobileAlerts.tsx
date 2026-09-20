import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost } from '../api/client'
import { getMobileControlKey } from '../api/credentials'
import type { MobileDevices, MobileStatus } from '../api/mobileAlertTypes'
import { MobilePreferences } from './MobilePreferences'
import { DeliveryLedger } from './mobile/DeliveryLedger'
import { PhoneSetupChecklist } from './mobile/PhoneSetupChecklist'
import { WebPushSetup } from './mobile/WebPushSetup'
import { WebPushSubscriptions } from './mobile/WebPushSubscriptions'

export function MobileAlerts() {
  const status = useQuery({ queryKey: ['mobile-alert-status'], queryFn: () => apiGet<MobileStatus>('/state/mobile-alerts/status'), refetchInterval: 15000 })
  const devices = useQuery({ queryKey: ['mobile-alert-devices'], queryFn: () => apiGet<MobileDevices>('/state/mobile-alerts/devices'), enabled: status.data?.configured === true, retry: false, refetchInterval: 15000 })
  const [keyEntered, setKeyEntered] = useState(() => getMobileControlKey() !== null)
  const [label, setLabel] = useState('My phone'), [platform, setPlatform] = useState('android'), [consent, setConsent] = useState(false)
  const [topic, setTopic] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false)
  const action = async (path: string, body: unknown = {}) => {
    setBusy(true); setMessage('')
    try { const result = await apiPost<{ topic?: string; note?: string; status?: string }>(path, body); if (result.topic) setTopic(result.topic); setMessage(result.note ?? result.status ?? 'Updated'); await devices.refetch() }
    catch (error) { setMessage((error as Error).message) }
    finally { setBusy(false) }
  }
  const keyChanged = () => { setKeyEntered(getMobileControlKey() !== null); if (status.data?.configured) void devices.refetch() }
  const refetchDevices = () => { void devices.refetch() }
  return <section className="card" aria-label="Mobile notifications">
    <h3 className="font-medium">Mobile notifications · Android and iPhone</h3>
    <p className="text-sm text-gray-400 mt-2">Delivers through the free ntfy phone app, or over Web Push to a browser subscribed below. No app store listing, Xcode project or wallet connection is needed. Generic notifications only; never approve or execute a trade from a notification.</p>
    {status.isLoading && <p>Checking delivery setup…</p>}
    {status.isError && <p role="alert">Notification status unavailable.</p>}
    {status.data && <>
      <p className="text-sm mt-3">{status.data.configured ? 'Control key configured' : 'Setup required — server-side mobile control authorization is not configured'} · worker {status.data.worker_running ? 'running' : 'not running'}</p>
      <p className="text-xs text-gray-400 mt-2">{status.data.note}</p>
    </>}
    <PhoneSetupChecklist configured={status.data?.configured} keyEntered={keyEntered} authorized={devices.isSuccess} refused={devices.isError}
      devices={devices.data?.devices ?? []} events={devices.data?.events ?? []} onKeyChange={keyChanged} />
    {devices.isError && <p role="alert" className="text-sm mt-3">Device controls need the mobile control key in this browser session (step 3). {devices.error?.message}</p>}
    {status.data?.configured && !devices.isError && <>
      <form className="mt-4 space-y-3" onSubmit={e => { e.preventDefault(); void action('/state/mobile-alerts/devices', { label, platform, public_topic_generic_only_consent: consent }) }}>
        <label className="block">Device label<input className="input w-full" aria-label="Device label" maxLength={60} value={label} onChange={e => setLabel(e.target.value)} /></label>
        <label className="block">Phone platform<select className="input w-full" aria-label="Phone platform" value={platform} onChange={e => setPlatform(e.target.value)}><option value="android">Android</option><option value="ios">iPhone / iOS</option></select></label>
        <label className="block text-sm"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> I accept generic messages through a public hosted topic. Anyone with the topic name can read or spoof messages.</label>
        <button className="chip" disabled={busy || !consent || !label.trim()}>Create subscription details — sends nothing</button>
      </form>
      {topic && <div className="mt-3 p-3 border border-gray-700 rounded" style={{ overflowWrap: 'anywhere' }}><p>In ntfy, subscribe using server https://ntfy.sh and topic:</p><code>{topic}</code><p className="text-xs mt-2">Save it privately on your phone. Test only after subscribing; enable notification permission.</p><button className="chip mt-2" onClick={() => { void navigator.clipboard.writeText(topic).then(() => setMessage('Topic copied'), () => setMessage('Clipboard unavailable; copy the topic manually')) }}>Copy topic</button></div>}
      {devices.data?.devices.map(device => <article key={device.id} className="mt-4 border-t border-gray-700 pt-3">
        <p>{device.label} · {device.platform === 'ios' ? 'iPhone' : 'Android'} · {device.enabled ? 'enabled' : 'disabled'}</p>
        <p className="text-xs text-gray-400">{device.operator_confirmed_at ? `Receipt attested by operator: ${new Date(device.operator_confirmed_at).toLocaleString()}` : 'Phone receipt not confirmed'}</p>
        <div className="flex flex-wrap gap-2 mt-2"><button className="chip" disabled={busy || !device.enabled} onClick={() => void action(`/state/mobile-alerts/devices/${device.id}/subscription`)}>Show subscription details</button><button className="chip" disabled={busy || !device.enabled} onClick={() => void action(`/state/mobile-alerts/devices/${device.id}/test`)}>Send generic test</button><button className="chip" disabled={busy || !device.enabled} onClick={() => void action(`/state/mobile-alerts/devices/${device.id}/disable`)}>Disable channel</button></div>
        <MobilePreferences key={JSON.stringify(device.notification_preferences)} initial={device.notification_preferences ?? {}} enabled={device.enabled} confirmed={!!device.operator_confirmed_at} busy={busy} save={value => action(`/state/mobile-alerts/devices/${device.id}/preferences`, value)} />
      </article>)}
      <WebPushSetup devices={devices.data?.devices ?? []} authorized={devices.isSuccess} onChanged={refetchDevices} />
      <WebPushSubscriptions authorized={devices.isSuccess} onChanged={refetchDevices} />
      <DeliveryLedger authorized={devices.isSuccess} onChanged={refetchDevices} />
    </>}
    {message && <p role="status" className="mt-3 text-sm" style={{ overflowWrap: 'anywhere' }}>{message}</p>}
  </section>
}
