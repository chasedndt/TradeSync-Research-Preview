import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

/**
 * The service worker is run here the way a browser runs it: the file is evaluated against a stand-in `self`,
 * and the handlers it registers are then called with the events a browser would send. That tests what the
 * worker does, rather than what its source looks like.
 */
const SOURCE = fileURLToPath(new URL('../public/sw.js', import.meta.url))
const ORIGIN = 'http://127.0.0.1:3000'

async function load({ offline = 'OFFLINE PAGE', online = true, fetcher: network } = {}) {
  const code = await readFile(SOURCE, 'utf8')
  const handlers = new Map()
  const shown = []
  const opened = []
  const cache = { added: [], addAll: async (urls) => cache.added.push(...urls), match: async (url) => (url === '/offline.html' ? offline : undefined) }
  const clients = []
  const self = {
    addEventListener: (name, handler) => handlers.set(name, handler),
    skipWaiting: async () => {},
    location: { origin: ORIGIN },
    registration: { showNotification: async (title, options) => shown.push({ title, options }) },
    clients: {
      claim: async () => {},
      matchAll: async () => clients,
      openWindow: async (url) => opened.push(url),
    },
    caches: { open: async () => cache, keys: async () => ['tradesync-shell-v1', 'old'], delete: async () => true },
  }
  const fetcher = network ?? (async (request) => {
    if (!online) throw new Error('offline')
    return { fromNetwork: true, request }
  })
  // eslint-disable-next-line no-new-func
  new Function('self', 'fetch', code)(self, fetcher)
  return { handlers, shown, opened, cache, clients, self, code }
}

async function push(payload) {
  const { handlers, shown } = await load()
  const event = { data: payload === undefined ? null : { json: () => payload }, waitUntil: (work) => event.waited = work }
  await handlers.get('push')(event)
  await event.waited
  return shown[0]
}

test('a push with no payload still shows the generic message and goes home', async () => {
  const shown = await push(undefined)
  assert.equal(shown.title, 'TradeSync')
  assert.equal(shown.options.body, 'TradeSync needs attention. Open your dashboard.')
  assert.equal(shown.options.data.path, '/')
})

test('a malformed payload is not allowed to break the notification', async () => {
  const { handlers, shown } = await load()
  const event = { data: { json: () => { throw new Error('not json') } }, waitUntil: (work) => event.waited = work }
  await handlers.get('push')(event)
  await event.waited
  assert.equal(shown[0].title, 'TradeSync')
})

test('a payload can set the text and a path on this site, and both are clamped', async () => {
  const shown = await push({ title: 'T'.repeat(200), body: 'B'.repeat(500), path: '/positions', tag: 'paper' })
  assert.equal(shown.title.length, 80)
  assert.equal(shown.options.body.length, 240)
  assert.equal(shown.options.data.path, '/positions')
  assert.equal(shown.options.tag, 'paper')
})

test('a payload can never send the operator to another site', async () => {
  for (const path of ['https://evil.example/x', '//evil.example', 'javascript:alert(1)', '/ok/../..\\x', 42, null]) {
    const shown = await push({ path })
    assert.equal(shown.options.data.path, '/', String(path))
  }
  assert.equal((await push({ path: '/thesis' })).options.data.path, '/thesis')
})

test('tapping a notification focuses a window already on this site and moves it to the path', async () => {
  const { handlers, clients, opened } = await load()
  const focused = []
  const navigated = []
  clients.push({ url: 'https://elsewhere.example/', focus: async () => focused.push('elsewhere'), navigate: async () => {} })
  clients.push({ url: `${ORIGIN}/market`, focus: async () => focused.push('cockpit'), navigate: async (url) => navigated.push(url) })
  let closed = false
  const event = {
    notification: { close: () => { closed = true }, data: { path: '/positions' } },
    waitUntil: (work) => event.waited = work,
  }
  await handlers.get('notificationclick')(event)
  await event.waited
  assert.ok(closed)
  assert.deepEqual(focused, ['cockpit'])
  assert.deepEqual(navigated, ['/positions'])
  assert.deepEqual(opened, [])
})

test('with no window on this site, tapping opens one', async () => {
  const { handlers, opened } = await load()
  const event = { notification: { close: () => {}, data: { path: '/settings' } }, waitUntil: (work) => event.waited = work }
  await handlers.get('notificationclick')(event)
  await event.waited
  assert.deepEqual(opened, ['/settings'])
})

test('no API request is ever answered by the worker, so no market or paper number can be stale', async () => {
  const { handlers } = await load()
  for (const mode of ['cors', 'no-cors', 'same-origin']) {
    let answered = false
    handlers.get('fetch')({ request: { mode, url: `${ORIGIN}/api/state/paper/positions` }, respondWith: () => { answered = true } })
    assert.equal(answered, false, mode)
  }
})

test('a page navigation goes to the network, and falls back to the offline page only when it fails', async () => {
  const online = await load()
  let answer
  online.handlers.get('fetch')({ request: { mode: 'navigate', url: `${ORIGIN}/` }, respondWith: (work) => { answer = work } })
  assert.equal((await answer).fromNetwork, true)

  const offline = await load({ online: false })
  offline.handlers.get('fetch')({ request: { mode: 'navigate', url: `${ORIGIN}/` }, respondWith: (work) => { answer = work } })
  assert.equal(await answer, 'OFFLINE PAGE')
})

test('install caches static files only, and nothing is ever written to a cache from a response', async () => {
  const { handlers, cache, code } = await load()
  const event = { waitUntil: (work) => event.waited = work }
  await handlers.get('install')(event)
  await event.waited
  assert.ok(cache.added.includes('/offline.html'))
  assert.ok(cache.added.every((url) => !url.includes('/api')), cache.added.join(' '))
  assert.ok(!/cache\.put|caches\.match\(\s*event\.request/.test(code), 'the worker must never store a response')
})

const TOKEN = 'Ab3_-'.repeat(8) + 'xyz'

async function tap(data, network) {
  const requests = []
  const recording = network ?? (async (url, options) => {
    requests.push({ url, options })
    return { ok: true }
  })
  const worker = await load({ fetcher: recording })
  const event = { notification: { close: () => {}, data }, waitUntil: (work) => event.waited = work }
  await worker.handlers.get('notificationclick')(event)
  await event.waited
  return { requests, opened: worker.opened }
}

test('a push carries its tap token into the notification only in the exact shape the server issues', async () => {
  assert.equal(TOKEN.length, 43)
  assert.equal((await push({ ack: TOKEN })).options.data.ack, TOKEN)
  for (const ack of [TOKEN + 'a', TOKEN.slice(1), `${TOKEN.slice(0, 42)}=`, 'x', 43, null, undefined]) {
    assert.equal((await push({ ack })).options.data.ack, '', String(ack))
  }
})

test('tapping posts that notification\'s token once, to this site only, with no credentials and nothing else', async () => {
  const { requests, opened } = await tap({ path: '/', ack: TOKEN })
  assert.equal(requests.length, 1)
  const [{ url, options }] = requests
  assert.equal(url, '/api/state/mobile-alerts/acknowledgements')
  assert.deepEqual(
    { method: options.method, mode: options.mode, credentials: options.credentials, redirect: options.redirect },
    { method: 'POST', mode: 'same-origin', credentials: 'omit', redirect: 'error' },
  )
  assert.deepEqual(JSON.parse(options.body), { token: TOKEN })
  assert.deepEqual(Object.keys(options.headers), ['Content-Type'])
  assert.deepEqual(opened, ['/'])
})

test('a notification with no token, or a malformed one, sends nothing when tapped', async () => {
  for (const data of [{ path: '/' }, { path: '/', ack: 'forged' }, {}, { ack: `${TOKEN}!` }]) {
    const { requests, opened } = await tap(data)
    assert.deepEqual(requests, [], JSON.stringify(data))
    assert.equal(opened.length, 1)
  }
})

test('the dashboard still opens when recording the tap fails', async () => {
  const { opened } = await tap({ path: '/settings', ack: TOKEN }, async () => { throw new Error('offline') })
  assert.deepEqual(opened, ['/settings'])
})

test('the worker holds no key: neither header is named and no stored credential is read', async () => {
  const { code } = await load()
  for (const forbidden of ['X-API-Key', 'X-Operator-Token', 'localStorage', 'indexedDB', 'sessionStorage']) {
    assert.ok(!code.includes(forbidden), forbidden)
  }
})
