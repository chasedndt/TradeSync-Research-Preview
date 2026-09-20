import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const { PROJECT_ID_PATTERN, REOWN_DASHBOARD, changeLine, checkProjectId, pairingIdleMessage, savedLine, shortId } =
  await importTs('src/components/settings/walletConnectText.ts')
const ID = '0123456789abcdef0123456789abcdef'

test('a project ID is 32 digits and letters a to f, trimmed before it is saved', () => {
  assert.deepEqual(checkProjectId(`  ${ID}\n`), { ok: true, value: ID })
  assert.equal(checkProjectId(ID.toUpperCase()).ok, true)
  for (const bad of [ID.slice(1), `${ID}0`, `${ID.slice(1)}g`, 'not a project id']) {
    const result = checkProjectId(bad)
    assert.equal(result.ok, false)
    assert.equal(result.kind, 'shape', bad)
  }
  assert.equal(checkProjectId('   ').kind, 'empty')
  assert.ok(PROJECT_ID_PATTERN.test(ID))
  assert.equal(REOWN_DASHBOARD, 'https://dashboard.reown.com')
})

test('text shaped like a recovery phrase or a private key is treated as a secret, never as an ID to save', () => {
  const phrase = Array.from('abcdefghijkl', (letter) => `word${letter}`).join(' ')
  for (const secret of [phrase, `${phrase} ${phrase}`, `0x${'ab'.repeat(32)}`, 'cd'.repeat(32)]) {
    const result = checkProjectId(secret)
    assert.equal(result.ok, false)
    assert.equal(result.kind, 'looks_secret')
    assert.match(result.message, /not sent anywhere/)
    assert.ok(!result.message.includes(secret))
  }
  // Eleven words is ordinary text, refused only for its shape.
  assert.equal(checkProjectId(phrase.split(' ').slice(0, 11).join(' ')).kind, 'shape')
})

test('the saved state and each change say who changed it, when, and what it replaced', () => {
  assert.equal(shortId(ID), '012345…cdef')
  assert.equal(shortId(null), 'not set')
  assert.match(savedLine(ID, 'chase', '2026-09-15T20:00:00Z'), /^Saved by chase on .+\d/)
  assert.match(savedLine(null, null, null), /^Not saved yet/)
  assert.match(changeLine({ changed_by: 'chase', changed_at: '2026-09-15T20:00:00Z', previous: null, next: ID }),
    /^Set to 012345…cdef by chase on .+; was not set$/)
  assert.match(changeLine({ changed_by: 'ops', changed_at: '2026-09-15T21:00:00Z', previous: ID, next: null }),
    /^Cleared by ops on .+; was 012345…cdef$/)
})

test('pairing says whether it uses the saved project ID or one typed for this pairing only', () => {
  assert.match(pairingIdleMessage('', ''), /^Setup required: save your public WalletConnect project ID in Settings/)
  assert.match(pairingIdleMessage(ID, ` ${ID} `), /^Using the project ID saved in Settings\./)
  assert.match(pairingIdleMessage(ID, 'f'.repeat(32)), /for this pairing only\. The one saved in Settings is unchanged\.$/)
})
