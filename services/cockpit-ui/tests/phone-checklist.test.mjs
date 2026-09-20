import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { NTFY_APPS, checklist, phoneProgress, stepsRemaining } = await importTs('src/components/mobile/phoneChecklist.ts')

const base = { configured: false, keyEntered: false, authorized: false, refused: false, devices: [], events: [] }
const marks = (steps) => Object.fromEntries(steps.map((step) => [step.id, step.marks.map((mark) => `${mark.label}:${mark.state}`).join(' ')]))

test('with nothing configured, only the key on this PC is to do and nothing on a phone is claimed', () => {
  assert.deepEqual(marks(checklist(base)), {
    app: 'Android:unseen iPhone:unseen',
    server_key: 'This PC:todo',
    session_key: 'This browser:waiting',
    enroll: 'Android:waiting iPhone:waiting',
    subscribe: 'Android:waiting iPhone:waiting',
    test: 'Android:waiting iPhone:waiting',
    confirm: 'Android:waiting iPhone:waiting',
  })
  assert.equal(marks(checklist({ ...base, configured: undefined })).server_key, 'This PC:waiting')
})

test('once the key is on this PC, the browser key is to do, and a key that does not match needs attention', () => {
  assert.equal(marks(checklist({ ...base, configured: true })).session_key, 'This browser:todo')
  assert.equal(marks(checklist({ ...base, configured: true, keyEntered: true, refused: true })).session_key, 'This browser:problem')
  const authorized = marks(checklist({ ...base, configured: true, keyEntered: true, authorized: true }))
  assert.equal(authorized.session_key, 'This browser:done')
  assert.equal(authorized.enroll, 'Android:todo iPhone:todo')
})

test('each phone moves through enrolment, a test and a confirmed receipt on its own', () => {
  const input = {
    ...base, configured: true, keyEntered: true, authorized: true,
    devices: [
      { id: 'a', platform: 'android', enabled: true, operator_confirmed_at: null },
      { id: 'i', platform: 'ios', enabled: true, operator_confirmed_at: null },
      { id: 'old', platform: 'ios', enabled: false, operator_confirmed_at: '2026-09-14T10:00:00Z' },
    ],
    events: [
      { device_id: 'a', kind: 'test', status: 'provider_accepted' },
      { device_id: 'i', kind: 'test', status: 'queued' },
      { device_id: 'old', kind: 'test', status: 'operator_confirmed' },
    ],
  }
  assert.deepEqual(marks(checklist(input)), {
    app: 'Android:unseen iPhone:unseen',
    server_key: 'This PC:done',
    session_key: 'This browser:done',
    enroll: 'Android:done iPhone:done',
    subscribe: 'Android:unseen iPhone:unseen',
    test: 'Android:done iPhone:waiting',
    confirm: 'Android:todo iPhone:waiting',
  })
  assert.deepEqual(phoneProgress(input, 'ios'), { enrolled: true, test: 'pending', confirmed: false })
})

test('a confirmed receipt proves the app and the subscription, and a failed test needs attention', () => {
  const input = {
    ...base, configured: true, keyEntered: true, authorized: true,
    devices: [{ id: 'a', platform: 'android', enabled: true, operator_confirmed_at: '2026-09-15T20:00:00Z' }, { id: 'i', platform: 'ios', enabled: true, operator_confirmed_at: null }],
    events: [{ device_id: 'i', kind: 'test', status: 'failed' }, { device_id: 'a', kind: 'attention', status: 'failed' }],
  }
  const result = marks(checklist(input))
  assert.equal(result.app, 'Android:done iPhone:unseen')
  assert.equal(result.subscribe, 'Android:done iPhone:unseen')
  assert.equal(result.test, 'Android:done iPhone:problem')
  assert.equal(result.confirm, 'Android:done iPhone:waiting')
  // app, subscribe, test and confirm still wait on the iPhone; the keys and both enrolments are done.
  assert.equal(stepsRemaining(checklist(input)), 4)
})

test('the app links are the official ntfy store pages', () => {
  assert.deepEqual(NTFY_APPS.map((app) => app.url), [
    'https://play.google.com/store/apps/details?id=io.heckel.ntfy',
    'https://f-droid.org/en/packages/io.heckel.ntfy/',
    'https://apps.apple.com/us/app/ntfy/id1625396347',
  ])
})
