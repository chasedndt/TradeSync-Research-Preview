import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const text = await importTs('src/components/intake/tradingViewText.ts')

test('intervals: a bare number is minutes, any other form is shown as TradingView sent it', () => {
  const cases = { '15': '15m', '240': '240m', '1D': '1D', '1h': '1h', '15m': '15m', ' 60 ': '60m', '': '' }
  for (const [input, expected] of Object.entries(cases)) assert.equal(text.intervalLabel(input), expected, input)
  assert.equal(text.intervalLabel(undefined), '')
  assert.equal(text.intervalLabel(5), '5m')
})

test('the template is pasted as indented JSON in its own order, and the hand-edited placeholders exclude the secret', () => {
  const template = { secret: '<paste your webhook secret>', indicator: '<indicator name>', ticker: '{{ticker}}', direction: '<long|short|none>', note: '<what fired>' }
  const pasted = text.templateText(template)
  assert.deepEqual(Object.entries(JSON.parse(pasted)), Object.entries(template))
  assert.match(pasted, /^\{\n {2}"secret": "<paste your webhook secret>",\n/)
  assert.deepEqual(text.manualPlaceholders(template, template.secret), ['<indicator name>', '<long|short|none>', '<what fired>'])
})

test('a receipt reads as what fired and where, and the verdict carries every recorded reason', () => {
  assert.equal(text.receiptTitle({ indicator: 'EMA cross', ticker: 'BTCUSD', interval: '15' }), 'EMA cross · BTCUSD · 15m')
  assert.equal(text.receiptTitle({ indicator: '', ticker: '', interval: '' }), 'Indicator not named · no ticker')
  assert.deepEqual(text.receiptVerdict({ accepted: true, reasons: [], review: 'awaiting review' }),
    { text: 'Accepted into quarantine, awaiting review', tone: 'tone-good' })
  assert.deepEqual(text.receiptVerdict({ accepted: false, reasons: [{ code: 'payload_claims_authority', detail: 'tier' }, { code: 'other', detail: '' }], review: 'reviewed' }),
    { text: 'Refused: payload_claims_authority: tier; other', tone: 'tone-bad' })
  assert.equal(text.receiptVerdict({ accepted: false, reasons: [], review: 'reviewed' }).text, 'Refused; no reason was recorded')
})

test('the secret is only ever described as configured or not, and times are exact', () => {
  assert.match(text.secretLine(true), /^Webhook secret: configured\./)
  assert.match(text.secretLine(false), /^Webhook secret: not configured\./)
  assert.equal(text.lastReceiptLine([]), 'No TradingView alert stored yet.')
  assert.match(text.lastReceiptLine([{ accepted: false, received_at: '2026-09-13T21:24:15+00:00' }]), /^Latest alert stored .*15.*, refused$/)
  assert.match(text.exactTime('2026-09-13T21:24:15+00:00'), /2026/)
  assert.equal(text.exactTime(null), 'an unknown time')
  assert.equal(text.checkedLine(0), 'checking…')
  assert.match(text.checkedLine(Date.UTC(2026, 8, 15, 20, 4, 5)), /^checked .+ · refreshes every 30 s$/)
})
