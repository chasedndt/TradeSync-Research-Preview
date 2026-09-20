/**
 * What this browser can actually do about notifications, decided from facts rather than assumption.
 *
 * The awkward case is iPhone and iPad. Safari in an ordinary tab has a service worker but no Push API, so a
 * plain capability check reports "not supported" when the truth is "not yet": iOS only offers Web Push to a web
 * app that was added to the Home Screen. That difference is the whole of the operator's next step, so it is a
 * state of its own here.
 *
 * Nothing in this file touches the network or asks for anything; it reads and decides.
 */

export type PushSupport = 'unsupported' | 'needs_home_screen' | 'supported'
export type PermissionState = 'default' | 'granted' | 'denied'

export interface BrowserFacts {
  serviceWorker: boolean
  pushManager: boolean
  notification: boolean
  /** Running as an installed app rather than in a browser tab. */
  standalone: boolean
  ios: boolean
}

interface BrowserLike {
  navigator?: {
    serviceWorker?: unknown
    userAgent?: string
    platform?: string
    maxTouchPoints?: number
    standalone?: boolean
  }
  matchMedia?: (query: string) => { matches: boolean }
  PushManager?: unknown
  Notification?: unknown
}

const IOS_AGENT = /iphone|ipad|ipod/i

/** The facts, read defensively: every one of these can be missing in a private window or an old browser. */
export function readBrowser(scope: BrowserLike = globalThis as unknown as BrowserLike): BrowserFacts {
  const nav = scope?.navigator ?? {}
  let displayMode = false
  try {
    displayMode = Boolean(scope?.matchMedia?.('(display-mode: standalone)')?.matches)
  } catch {
    displayMode = false
  }
  return {
    serviceWorker: Boolean(nav.serviceWorker),
    pushManager: typeof scope?.PushManager !== 'undefined',
    notification: typeof scope?.Notification !== 'undefined',
    standalone: displayMode || nav.standalone === true,
    // iPadOS reports itself as a Mac, and is told apart by the touch points.
    ios: IOS_AGENT.test(nav.userAgent ?? '') || (nav.platform === 'MacIntel' && (nav.maxTouchPoints ?? 0) > 1),
  }
}

export function supportFrom(facts: BrowserFacts): PushSupport {
  // Asked before the capability check: on iOS the missing Push API is the symptom, not the reason.
  if (facts.ios && !facts.standalone) return 'needs_home_screen'
  if (!facts.serviceWorker || !facts.pushManager || !facts.notification) return 'unsupported'
  return 'supported'
}

export function readPermission(scope: BrowserLike = globalThis as unknown as BrowserLike): PermissionState {
  const notification = scope?.Notification as { permission?: string } | undefined
  const value = notification?.permission
  return value === 'granted' || value === 'denied' ? value : 'default'
}

/**
 * The VAPID public key as a browser wants it: base64url text in, the raw 65 bytes out.
 * Throws rather than handing `pushManager.subscribe` something it will reject with an opaque error.
 */
export function applicationServerKey(publicKey: string): Uint8Array<ArrayBuffer> {
  const text = (publicKey ?? '').trim()
  if (!/^[A-Za-z0-9_-]+$/.test(text)) throw new Error('The application server key is not base64url text.')
  const padded = text.padEnd(text.length + ((4 - (text.length % 4)) % 4), '=')
  const binary = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  // Backed by its own ArrayBuffer, which is what pushManager.subscribe accepts as a BufferSource.
  const bytes = new Uint8Array(new ArrayBuffer(binary.length))
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  if (bytes.length !== 65 || bytes[0] !== 4) throw new Error('The application server key is not a VAPID public key.')
  return bytes
}
