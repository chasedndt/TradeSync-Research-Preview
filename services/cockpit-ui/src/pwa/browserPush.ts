/**
 * The browser side of notifications: register the service worker, ask for permission, subscribe, unsubscribe.
 *
 * Every call is guarded. A browser that has no service worker, no Push API, or has had site data blocked will
 * throw or return undefined from any of these, and the Settings page has to be able to say what is true rather
 * than break. So each function returns a plain answer and never throws at the caller.
 *
 * Registration happens once at start-up (`src/main.tsx`). It is deliberately quiet: a Cockpit that cannot
 * register a worker still works, because the worker only shows notifications and one offline page.
 */

import { applicationServerKey, type PermissionState } from './pushSupport'

export const SERVICE_WORKER_URL = '/sw.js'

export interface SubscriptionMaterial {
  endpoint: string
  p256dh: string
  auth: string
}

function serviceWorkerContainer(): ServiceWorkerContainer | null {
  const supported = typeof navigator !== 'undefined' && 'serviceWorker' in navigator
  return supported && globalThis.isSecureContext ? navigator.serviceWorker : null
}

/** Register the worker, or null when this browser cannot (no support, not a secure context, refused). */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  const container = serviceWorkerContainer()
  if (!container) return null
  try {
    return await container.register(SERVICE_WORKER_URL, { scope: '/' })
  } catch {
    return null
  }
}

/** The registration this page is under, waiting for it to be ready, or null. */
export async function currentRegistration(): Promise<ServiceWorkerRegistration | null> {
  const container = serviceWorkerContainer()
  if (!container) return null
  try {
    return (await container.getRegistration('/')) ?? (await container.ready)
  } catch {
    return null
  }
}

/** Ask the browser for notification permission. Must be called from a click; the answer is the new state. */
export async function askPermission(): Promise<PermissionState> {
  const notification = globalThis.Notification
  if (typeof notification === 'undefined') return 'denied'
  try {
    const answer = await notification.requestPermission()
    return answer === 'granted' || answer === 'denied' ? answer : 'default'
  } catch {
    return 'default'
  }
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await currentRegistration()
  if (!registration?.pushManager) return null
  try {
    return await registration.pushManager.getSubscription()
  } catch {
    return null
  }
}

function material(subscription: PushSubscription): SubscriptionMaterial {
  const json = subscription.toJSON()
  const keys = json.keys ?? {}
  return { endpoint: json.endpoint ?? subscription.endpoint, p256dh: keys.p256dh ?? '', auth: keys.auth ?? '' }
}

/**
 * Subscribe this browser to push with the operator's VAPID public key, reusing the subscription it already has.
 * Returns what state-api needs to record. Throws only with a sentence worth showing.
 */
export async function subscribeHere(publicKey: string): Promise<SubscriptionMaterial> {
  const registration = await currentRegistration()
  if (!registration?.pushManager) throw new Error('This browser has no push service worker registered.')
  const existing = await registration.pushManager.getSubscription()
  if (existing) return material(existing)
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: applicationServerKey(publicKey),
  })
  return material(subscription)
}

/** Drop this browser's own subscription. The server's record is removed separately. */
export async function unsubscribeHere(): Promise<boolean> {
  const subscription = await currentSubscription()
  if (!subscription) return false
  try {
    return await subscription.unsubscribe()
  } catch {
    return false
  }
}
