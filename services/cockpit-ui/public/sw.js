/*
 * TradeSync Cockpit service worker.
 *
 * It does three things: it shows a notification when a push arrives, it opens the dashboard when one is tapped
 * and records that the notification was seen, and it keeps one static page for when the network is gone.
 *
 * What it deliberately does not do is cache anything the dashboard reads. Market prices, paper positions and
 * every other API answer go straight to the network, every time: a cached price is a wrong price, and an
 * operator acting on a stale number is worse than one seeing nothing. The only thing in the cache is the
 * offline page and the icons, written once at install and never from a response. No request to /api is
 * touched here at all.
 *
 * A notification's payload is not trusted. The text is clamped, and the place a tap goes is only ever a path
 * on this origin, so a payload cannot send the operator somewhere else.
 *
 * The worker holds no key. Tapping a notification posts the single-use token that one notification carried, and
 * only that, to this site's own API. The token names nothing, works once and expires within the hour; the mobile
 * control key and the operator token never reach this file.
 *
 * Nothing in this file can approve, change or execute a trade.
 */

const SHELL_CACHE = 'tradesync-shell-v1'
const SHELL = [
  '/offline.html',
  '/manifest.webmanifest',
  '/brand/tradesync-icon-192.png',
  '/brand/tradesync-icon-512.png',
]

const HOME = '/'
const DEFAULT_TITLE = 'TradeSync'
const DEFAULT_BODY = 'TradeSync needs attention. Open your dashboard.'
const MAX_TITLE = 80
const MAX_BODY = 240
const ACK_PATH = '/api/state/mobile-alerts/acknowledgements'
const ACK_TOKEN = /^[A-Za-z0-9_-]{43}$/

/** Only a path on this origin. Anything else — another site, a protocol-relative URL, nothing at all — is home. */
function safePath(value) {
  if (typeof value !== 'string') return HOME
  const path = value.trim()
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return HOME
  return path
}

function text(value, fallback, limit) {
  return typeof value === 'string' && value.trim() ? value.trim().slice(0, limit) : fallback
}

/** A tap token exactly as the server issues it, or nothing. */
function ackToken(value) {
  return typeof value === 'string' && ACK_TOKEN.test(value) ? value : ''
}

/** What to show for one push. A payload that is missing, malformed or empty still shows the generic message. */
function notificationFor(event) {
  let payload = {}
  try {
    payload = (event.data && event.data.json()) || {}
  } catch (error) {
    payload = {}
  }
  if (!payload || typeof payload !== 'object') payload = {}
  return {
    title: text(payload.title, DEFAULT_TITLE, MAX_TITLE),
    options: {
      body: text(payload.body, DEFAULT_BODY, MAX_BODY),
      icon: '/brand/tradesync-icon-192.png',
      badge: '/brand/tradesync-icon-192.png',
      tag: text(payload.tag, 'tradesync', 60),
      data: { path: safePath(payload.path), reference: text(payload.reference, '', 40), ack: ackToken(payload.ack) },
      requireInteraction: false,
    },
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    self.caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const names = await self.caches.keys()
      await Promise.all(names.filter((name) => name !== SHELL_CACHE).map((name) => self.caches.delete(name)))
      await self.clients.claim()
    })(),
  )
})

self.addEventListener('fetch', (event) => {
  // Page navigations only, and always from the network first. Everything else, API reads included, is left to
  // the browser untouched: nothing is read from or written to a cache here.
  if (event.request.mode !== 'navigate') return
  event.respondWith(
    (async () => {
      try {
        return await fetch(event.request)
      } catch (error) {
        const cache = await self.caches.open(SHELL_CACHE)
        const offline = await cache.match('/offline.html')
        return offline || Response.error()
      }
    })(),
  )
})

self.addEventListener('push', (event) => {
  const { title, options } = notificationFor(event)
  event.waitUntil(self.registration.showNotification(title, options))
})

/**
 * Tell the dashboard this notification was opened: this site only, no cookies, no redirects, and a body holding
 * the token and nothing else. Whether it works or not, opening the dashboard does not wait on it.
 */
async function acknowledge(token) {
  if (!ackToken(token)) return false
  try {
    const response = await fetch(ACK_PATH, {
      method: 'POST',
      mode: 'same-origin',
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
    return Boolean(response && response.ok)
  } catch (error) {
    return false
  }
}

async function openDashboard(path) {
  const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
  for (const client of windows) {
    if (new URL(client.url).origin !== self.location.origin) continue
    await client.focus()
    if (typeof client.navigate === 'function' && new URL(client.url).pathname !== path) await client.navigate(path)
    return
  }
  await self.clients.openWindow(path)
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const data = event.notification.data || {}
  event.waitUntil(Promise.all([acknowledge(data.ack), openDashboard(safePath(data.path))]))
})

self.addEventListener('pushsubscriptionchange', (event) => {
  // The browser rotated this subscription. Re-subscribing needs the application server key, which only the
  // page has, so say so rather than failing silently.
  event.waitUntil(
    self.registration.showNotification(DEFAULT_TITLE, {
      body: 'This browser changed its notification subscription. Open Settings in TradeSync to subscribe again.',
      icon: '/brand/tradesync-icon-192.png',
      tag: 'tradesync-subscription',
      data: { path: '/settings', reference: '' },
    }),
  )
})
