import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { applicationServerKey, readBrowser, readPermission, supportFrom } = await importTs('src/pwa/pushSupport.ts')
const { CONTACT_NOTE, IOS_REQUIREMENT, advice, permissionWord, senderWord, supportWord } = await importTs('src/components/mobile/pwaText.ts')

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15'
const CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0'
const KEY = Buffer.concat([Buffer.from([4]), Buffer.alloc(64, 7)]).toString('base64url')

const scope = ({ agent = CHROME, standalone = false, displayMode = false, push = true, worker = true, platform = 'Win32', touch = 0 }) => ({
  navigator: { userAgent: agent, platform, maxTouchPoints: touch, standalone, ...(worker ? { serviceWorker: {} } : {}) },
  matchMedia: () => ({ matches: displayMode }),
  ...(push ? { PushManager: function PushManager() {} } : {}),
  Notification: function Notification() {},
})

test('an iPhone in a browser tab is told to add the app to the Home Screen, not that it is unsupported', () => {
  const tab = readBrowser(scope({ agent: IPHONE, push: false }))
  assert.equal(tab.ios, true)
  assert.equal(tab.standalone, false)
  assert.equal(supportFrom(tab), 'needs_home_screen')

  const installed = readBrowser(scope({ agent: IPHONE, standalone: true }))
  assert.equal(supportFrom(installed), 'supported')
})

test('an iPad reports itself as a Mac and is recognised by its touch points', () => {
  const ipad = readBrowser(scope({ agent: CHROME, platform: 'MacIntel', touch: 5 }))
  assert.equal(ipad.ios, true)
  assert.equal(supportFrom(ipad), 'needs_home_screen')
})

test('a browser missing any piece of the push stack is unsupported, and a complete one is supported', () => {
  assert.equal(supportFrom(readBrowser(scope({ push: false }))), 'unsupported')
  assert.equal(supportFrom(readBrowser(scope({ worker: false }))), 'unsupported')
  assert.equal(supportFrom(readBrowser(scope({}))), 'supported')
  assert.equal(supportFrom(readBrowser(scope({ displayMode: true }))), 'supported')
})

test('missing pieces are read without throwing, however broken the browser is', () => {
  assert.deepEqual(readBrowser({}), { serviceWorker: false, pushManager: false, notification: false, standalone: false, ios: false })
  const throws = { navigator: {}, matchMedia: () => { throw new Error('blocked') } }
  assert.equal(readBrowser(throws).standalone, false)
  assert.equal(readPermission({}), 'default')
  assert.equal(readPermission({ Notification: { permission: 'granted' } }), 'granted')
  assert.equal(readPermission({ Notification: { permission: 'nonsense' } }), 'default')
})

test('the application server key becomes the 65 bytes a browser expects, or is refused', () => {
  const bytes = applicationServerKey(KEY)
  assert.equal(bytes.length, 65)
  assert.equal(bytes[0], 4)
  assert.equal(Buffer.from(bytes).toString('base64url'), KEY)
  for (const bad of ['', 'not base64!', Buffer.alloc(32, 1).toString('base64url'), Buffer.concat([Buffer.from([2]), Buffer.alloc(64, 7)]).toString('base64url')]) {
    assert.throws(() => applicationServerKey(bad), /application server key/)
  }
})

test('each real state names the one thing to do next, in order', () => {
  assert.equal(advice('needs_home_screen', 'default', true, false, true).action, 'install')
  // Even with everything else in place, an iPhone tab hears about the Home Screen first.
  assert.equal(advice('needs_home_screen', 'granted', false, false, false).action, 'install')
  assert.equal(advice('unsupported', 'default', true, false, true).action, 'none')
  assert.equal(advice('supported', 'granted', false, false, false).action, 'server_key')
  assert.equal(advice('supported', 'denied', true, false, true).action, 'browser_settings')
  assert.equal(advice('supported', 'default', true, false, true).action, 'ask')
  assert.equal(advice('supported', 'granted', true, false, false).action, 'subscribe')
  assert.equal(advice('supported', 'granted', true, true, false).action, 'server_contact')
  assert.equal(advice('supported', 'granted', true, true, true).action, 'none')
})

test('the iPhone requirement says Add to Home Screen and rules out Xcode and a developer membership', () => {
  assert.match(IOS_REQUIREMENT, /Add to Home Screen/)
  assert.match(IOS_REQUIREMENT, /no Xcode project/)
  assert.match(IOS_REQUIREMENT, /Apple Developer\s+membership/)
  assert.match(advice('needs_home_screen', 'default', true, false, true).detail, /Add to Home Screen/)
})

test('a subscribed browser is told where alerts go and what a tap does, or exactly what delivery still waits for', () => {
  const ready = advice('supported', 'granted', true, true, true)
  assert.match(ready.detail, /arrive here instead of the ntfy app/)
  assert.match(ready.detail, /marks it seen in the delivery ledger/)
  const waiting = advice('supported', 'granted', true, true, false)
  assert.equal(waiting.headline, 'This browser is subscribed, but nothing is sent to it yet')
  assert.equal(waiting.detail, CONTACT_NOTE)
  assert.match(CONTACT_NOTE, /MOBILE_WEB_PUSH_SUBJECT/)
  assert.match(CONTACT_NOTE, /keep going through ntfy/)
  assert.equal(senderWord(false, false), 'needs the key pair')
  assert.equal(senderWord(true, false), 'waiting for a contact address')
  assert.equal(senderWord(true, true), 'ready')
  assert.equal(permissionWord('denied'), 'blocked in this browser')
  assert.equal(supportWord('needs_home_screen'), 'add to the Home Screen first')
})
