import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { tokenAdvice } = await importTs('src/components/settings/operatorTokenText.ts')

test('off: not needed while only this PC can reach the dashboard, and needed before any remote access', () => {
  const advice = tokenAdvice('disabled')
  assert.equal(advice.headline, 'Off.')
  assert.match(advice.detail, /^You do not need it while the dashboard and state-api can be reached only from this PC/)
  assert.match(advice.detail, /Turn it on before any remote access/)
})

test('on, too short and unknown each say what state-api does', () => {
  assert.equal(tokenAdvice('required').headline, 'On.')
  assert.match(tokenAdvice('required').detail, /reading does not/)
  assert.equal(tokenAdvice('misconfigured').tone, 'tone-bad')
  assert.match(tokenAdvice('misconfigured').detail, /shorter than 32 characters, so state-api refuses every change/)
  assert.equal(tokenAdvice(undefined).headline, 'Not known yet.')
})
