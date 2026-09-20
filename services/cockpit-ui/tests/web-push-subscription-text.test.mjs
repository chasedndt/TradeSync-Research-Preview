import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { healthLine, healthTone } = await importTs('src/components/mobile/subscriptionText.ts')
const { exactTime } = await importTs('src/components/mobile/deliveryLedgerText.ts')

const WHEN = '2026-09-16T21:04:07Z'
const row = (extra) => ({
  active: true, last_attempt_at: null, last_status: null, last_error: null, expired_at: null, expired_reason: null, ...extra,
})

test('a browser nothing has been sent to says so, without inventing a result', () => {
  assert.equal(healthLine(row({})), 'Nothing has been sent to this browser yet.')
  assert.equal(healthTone(row({})), 'neutral')
})

test('an accepted push is acceptance by the push service, never proof the phone showed it', () => {
  const line = healthLine(row({ last_attempt_at: WHEN, last_status: 201 }))
  assert.equal(line, `Last push accepted by its push service at ${exactTime(WHEN)} — not proof the phone showed it.`)
  assert.equal(healthTone(row({ last_attempt_at: WHEN, last_status: 201 })), 'good')
})

test('a push that was not accepted names the HTTP status, or the failure when there was no answer', () => {
  assert.equal(healthLine(row({ last_attempt_at: WHEN, last_status: 503, last_error: 'PushServiceUnavailable' })),
    `Last push not accepted at ${exactTime(WHEN)}: HTTP 503.`)
  assert.equal(healthLine(row({ last_attempt_at: WHEN, last_error: 'ConnectTimeout' })),
    `Last push not accepted at ${exactTime(WHEN)}: ConnectTimeout.`)
  assert.equal(healthTone(row({ last_attempt_at: WHEN, last_status: 403 })), 'problem')
})

test('an expired browser keeps its reason and says nothing is sent to it any more', () => {
  const reason = 'The push service answered HTTP 410: this subscription no longer exists. Subscribe the browser again.'
  const expired = row({ active: false, expired_at: WHEN, expired_reason: reason, last_attempt_at: WHEN, last_status: 410 })
  assert.equal(healthLine(expired), `Expired ${exactTime(WHEN)} — ${reason} Nothing is sent to it now.`)
  assert.equal(healthTone(expired), 'problem')
  assert.match(healthLine(row({ active: false, expired_at: WHEN })), /^Expired [^—]+ Nothing is sent to it now\.$/)
})
