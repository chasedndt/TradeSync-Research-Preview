import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const {
  acknowledgementLine, attemptLine, canAcknowledge, canConfirmReceipt, deadLetterLine, exactTime, providerLine,
  reference, retryLadder, statusWord, transportWord,
} = await importTs('src/components/mobile/deliveryLedgerText.ts')

const WHEN = '2026-09-16T21:04:07Z'
const event = (extra) => ({
  id: '3f2504e0-4f89-11d3-9a0c-0305e82c3301', device_id: 'd', kind: 'attention', status: 'queued', attempts: 0,
  created_at: WHEN, next_attempt_at: null, attempted_at: null, accepted_at: null, confirmed_at: null,
  acknowledged_at: null, acknowledged_by: null, dead_lettered_at: null, dead_letter_reason: null, last_error: null,
  expires_at: null, device_label: 'My phone', platform: 'ios', ...extra,
})

test('every status reads as a sentence, including one this build has not seen', () => {
  assert.equal(statusWord('provider_accepted'), 'accepted by the provider')
  assert.equal(statusWord('dead_letter'), 'given up on')
  assert.equal(statusWord('expired'), 'expired before it could be sent')
  assert.equal(statusWord('something_new'), 'something new')
})

test('a time is absolute and to the second, and an absent one says so rather than showing now', () => {
  const shown = exactTime(WHEN)
  assert.match(shown, /2026/)
  assert.match(shown, /:\d\d:\d\d/)
  assert.equal(exactTime(null), 'no time recorded')
  assert.equal(exactTime('not a time'), 'no time recorded')
})

test('attempts are counted against the limit, with the time of the last one', () => {
  assert.equal(attemptLine(event({}), 5), 'not attempted yet')
  const line = attemptLine(event({ attempts: 3, attempted_at: WHEN }), 5)
  assert.match(line, /^3 of 5 attempts · last tried /)
  assert.ok(line.endsWith(exactTime(WHEN)))
})

test('provider acceptance is shown as acceptance, never as receipt', () => {
  const accepted = providerLine(event({ status: 'provider_accepted', accepted_at: WHEN }))
  assert.match(accepted, /Provider accepted it at /)
  assert.match(accepted, /not proof a phone showed it/)
  assert.match(providerLine(event({ status: 'retry', next_attempt_at: WHEN })), /^Next attempt at /)
  const pushed = providerLine(event({ status: 'provider_accepted', accepted_at: WHEN, transport: 'web_push' }))
  assert.match(pushed, /^Push service accepted it at .* — not proof a phone showed it$/)
  assert.equal(providerLine(event({})), null)
})

test('an acknowledgement names who said so and when, and a dead letter keeps its reason', () => {
  assert.equal(acknowledgementLine(event({})), null)
  assert.match(acknowledgementLine(event({ acknowledged_at: WHEN, acknowledged_by: 'device' })), /^Marked seen by a tap on the notification at /)
  assert.match(acknowledgementLine(event({ acknowledged_at: WHEN, acknowledged_by: 'operator' })), /^Marked seen by the operator at /)
  assert.equal(deadLetterLine(event({})), null)
  const dead = deadLetterLine(event({ dead_lettered_at: WHEN, dead_letter_reason: 'No delivery after 5 attempts.' }))
  assert.match(dead, /^Given up on at /)
  assert.match(dead, /— No delivery after 5 attempts\.$/)
  assert.match(deadLetterLine(event({ dead_lettered_at: WHEN })), /^Given up on at [^—]+$/)
})

test('only something attempted and not yet acknowledged can be marked seen', () => {
  assert.equal(canAcknowledge(event({})), false)
  assert.equal(canAcknowledge(event({ attempts: 1 })), true)
  assert.equal(canAcknowledge(event({ attempts: 1, acknowledged_at: WHEN, acknowledged_by: 'operator' })), false)
  assert.equal(canConfirmReceipt(event({ status: 'provider_accepted' })), true)
  assert.equal(canConfirmReceipt(event({ status: 'dead_letter' })), false)
})

test('the retry ladder and the reference come from the server, not from a guess here', () => {
  assert.equal(retryLadder([15, 30, 60, 120]), '15s, 30s, 60s, 120s')
  assert.equal(reference(event({})), '3f2504e0')
})

test('the transport that carried the latest attempt is named, and nothing is claimed before one was made', () => {
  assert.equal(transportWord('web_push'), 'via Web Push')
  assert.equal(transportWord('ntfy'), 'via ntfy')
  assert.equal(transportWord('carrier_pigeon'), 'via carrier pigeon')
  assert.equal(transportWord(null), '')
  assert.equal(transportWord(undefined), '')
})
