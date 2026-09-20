import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

const {
  AUDIT_TRAILS,
  IDENTITY_STATEMENT,
  changeAuthority,
  deviceLine,
  forgetAction,
  identityLine,
  inboxLine,
  modeLine,
  sessionLine,
} = await importTs('src/components/layout/operatorProfile.ts')

/** Wording that would claim an authentication this system does not have. */
const IMPLIES_LOGIN = /signed in|logged in|sign out|log out|your account|authenticated as/i

test('the menu states plainly that there is no sign-in and no session', () => {
  assert.match(IDENTITY_STATEMENT, /no sign-in and no session/i)
  assert.match(IDENTITY_STATEMENT, /nobody is authenticated/i)
  assert.match(IDENTITY_STATEMENT, /not a credential/i)
})

test('the operator name is attribution, never an identity', () => {
  const named = identityLine('Chase')
  assert.equal(named, 'Changes you make are attributed to "Chase".')
  assert.ok(!IMPLIES_LOGIN.test(named))
  assert.match(identityLine(''), /No name is set/)
  assert.match(identityLine(null), /recorded without one/)
  assert.ok(!IMPLIES_LOGIN.test(identityLine(null)))
})

test('change authority reports what state-api actually enforces, in each of its three states', () => {
  const required = changeAuthority({ operator_token: 'required', origin_check: 'enforced' })
  assert.equal(required.tone, 'good')
  assert.match(required.detail, /must carry the operator token/)
  assert.match(required.detail, /another web page is refused/)

  const off = changeAuthority({ operator_token: 'disabled', origin_check: 'enforced' })
  assert.equal(off.tone, 'warn')
  assert.match(off.detail, /any tool on this machine can change state/)

  const broken = changeAuthority({ operator_token: 'misconfigured', origin_check: 'disabled' })
  assert.equal(broken.tone, 'bad')
  assert.match(broken.detail, /refuses every change/)
  assert.match(broken.detail, /origin check is switched off/)

  assert.equal(changeAuthority(undefined).tone, 'dim')
  assert.equal(changeAuthority(undefined, true).label, 'Unknown')
})

test('no trust level is invented: it is only ever what the policy reports', () => {
  const labels = ['required', 'disabled', 'misconfigured'].map(
    (state) => changeAuthority({ operator_token: state, origin_check: 'enforced' }).label,
  )
  for (const label of labels) {
    assert.ok(!/trusted|verified|admin|owner|level \d/i.test(label), `invented a trust level: ${label}`)
  }
})

test('the mode names the gate, and says whether paper entries are being admitted', () => {
  const paused = modeLine('false', true)
  assert.equal(paused.label, 'Paper only')
  assert.equal(paused.tone, 'good')
  assert.match(paused.detail, /EXECUTION_ENABLED is false/)
  assert.match(paused.detail, /New paper entries are paused/)

  assert.match(modeLine('false', false).detail, /being admitted/)
  assert.match(modeLine('false', null).detail, /could not be read/)
  assert.equal(modeLine('true', false).tone, 'bad')
  assert.equal(modeLine(undefined, null).label, 'Checking')
})

test('the inbox counts held submissions and never calls them approvals', () => {
  assert.equal(inboxLine(0), 'Nothing is held for review.')
  assert.equal(inboxLine(1), '1 submission is held for review.')
  assert.equal(inboxLine(4), '4 submissions are held for review.')
  assert.equal(inboxLine(null), 'Held submissions could not be read.')
  // A listing cut at its limit is a floor, not a count.
  assert.equal(inboxLine(200, true), 'At least 200 submissions are held for review.')
  for (const value of [0, 1, 4, null]) {
    assert.ok(!/approval/i.test(inboxLine(value)))
  }
})

test('devices are phones, not sessions, and a refusal names the key it needs', () => {
  assert.equal(deviceLine({ total: 2, enabled: 1 }), '2 phones enrolled, 1 receiving notifications.')
  assert.equal(deviceLine({ total: 1, enabled: 1 }), '1 phone enrolled, 1 receiving notifications.')
  assert.equal(deviceLine({ total: 0, enabled: 0 }), 'No phone is enrolled for notifications.')
  assert.equal(deviceLine(undefined), 'Notification devices could not be read.')
  assert.match(deviceLine(undefined, true), /mobile control key/)
  assert.ok(!IMPLIES_LOGIN.test(deviceLine({ total: 2, enabled: 1 })))
})

test('what the browser holds is described without calling it a login', () => {
  assert.match(sessionLine(false, false), /holds no credential/)
  assert.match(sessionLine(true, false), /the operator token/)
  assert.match(sessionLine(true, true), /the operator token and the mobile control key/)
  assert.ok(!IMPLIES_LOGIN.test(sessionLine(true, true)))
})

test('forgetting credentials is offered only when something is actually held', () => {
  const nothing = forgetAction(false, false)
  assert.equal(nothing.enabled, false)
  assert.match(nothing.detail, /Nothing is held/)

  const held = forgetAction(true, false)
  assert.equal(held.enabled, true)
  assert.match(held.detail, /Clears the operator token/)
  assert.match(held.detail, /Nothing on the server changes/)

  // It is not a sign-out, because there is no session to end.
  assert.ok(!IMPLIES_LOGIN.test(held.label))
  assert.match(held.label, /Forget credentials held in this browser/)
})

test('every audit export is a read-only state-api record beside the page that shows it', () => {
  assert.ok(AUDIT_TRAILS.length >= 5)
  for (const trail of AUDIT_TRAILS) {
    assert.ok(trail.label && trail.detail)
    assert.match(trail.to, /^\/[a-z-]+$/)
    assert.match(trail.json, /^\/state\//)
  }
  // The paper risk panel and its audit live on the signal ledger, not on a positions page.
  assert.equal(AUDIT_TRAILS.find((trail) => trail.json === '/state/paper-risk')?.to, '/signal-ledger')
})
