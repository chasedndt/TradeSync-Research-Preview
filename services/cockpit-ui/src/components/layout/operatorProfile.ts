/**
 * What the operator menu may honestly say.
 *
 * The menu occupies the place an account menu occupies in every other
 * application, and that is exactly the problem: TradeSync has no identity, no
 * session and no sign-in. Nobody is authenticated. The operator name is typed
 * into this browser and kept there, and it is recorded beside changes purely as
 * attribution — anyone who can reach this machine can set it to anything.
 *
 * So the menu states that plainly rather than implying a login it cannot back.
 * There is no "signed in as", no avatar standing for a verified person, and no
 * "sign out", because there is no session to end. What can be ended is the set
 * of credentials this browser session is holding, and that action is offered
 * only while there is actually something to forget: a control that does nothing
 * is not shipped.
 *
 * Every figure the menu shows comes from a real endpoint:
 *
 * - change authority from `GET /state/access-policy`, which reports what
 *   state-api actually enforces;
 * - the mode from the execution gate and the paper entry pause;
 * - the inbox from the held connector submissions awaiting a decision;
 * - devices from the enrolled notification phones.
 *
 * Wording only: nothing here decides anything, and no count is derived.
 */

import type { AccessPolicy } from '../../api/operatorSettingsTypes'

export type Tone = 'good' | 'warn' | 'bad' | 'dim'

export interface Standing {
  label: string
  detail: string
  tone: Tone
}

/** Said on the menu itself, because the menu sits where an account menu sits and is not one. */
export const IDENTITY_STATEMENT =
  'This is a local-only operator profile: there is no sign-in and no session, so nobody is authenticated. The label is not a credential; it is recorded beside changes for audit history and grants no wallet or execution authority.'

/** Who changes are attributed to, stated as attribution rather than as an identity. */
export function identityLine(name: string | null | undefined): string {
  const trimmed = (name ?? '').trim()
  return trimmed
    ? `Changes you make are attributed to "${trimmed}".`
    : 'No name is set, so changes you make are recorded without one. Set it in Settings.'
}

/** What state-api enforces on a change right now. This is the only trust boundary that exists. */
export function changeAuthority(policy: AccessPolicy | undefined, unreachable = false): Standing {
  if (unreachable) {
    return { label: 'Unknown', detail: 'The access policy could not be read, so what is enforced is unknown.', tone: 'bad' }
  }
  if (!policy) {
    return { label: 'Checking', detail: 'Reading what state-api enforces on a change…', tone: 'dim' }
  }
  const origin = policy.origin_check === 'enforced'
    ? 'A change sent from another web page is refused.'
    : 'The origin check is switched off, so a change from another web page is accepted.'
  if (policy.operator_token === 'required') {
    return {
      label: 'Operator token required',
      detail: `Every change must carry the operator token; reading does not. ${origin}`,
      tone: 'good',
    }
  }
  if (policy.operator_token === 'misconfigured') {
    return {
      label: 'Every change refused',
      detail: `STATE_API_OPERATOR_TOKEN is set but shorter than 32 characters, so state-api refuses every change. ${origin}`,
      tone: 'bad',
    }
  }
  return {
    label: 'No token required',
    detail: `state-api asks for no operator token, so any tool on this machine can change state. `
      + `The loopback-only ports are the control. ${origin}`,
    tone: 'warn',
  }
}

/** Paper or live, and whether new paper entries are being admitted. */
export function modeLine(executionEnabled: string | undefined, entriesPaused: boolean | null | undefined): Standing {
  if (executionEnabled === undefined) {
    return { label: 'Checking', detail: 'Reading the execution gate…', tone: 'dim' }
  }
  if (executionEnabled === 'true') {
    return {
      label: 'Live execution open',
      detail: 'EXECUTION_ENABLED is true. Orders can reach the venue.',
      tone: 'bad',
    }
  }
  const entries = entriesPaused === true
    ? 'New paper entries are paused; open positions keep their observations and exits.'
    : entriesPaused === false
      ? 'New paper entries are being admitted.'
      : 'Whether new paper entries are admitted could not be read.'
  return { label: 'Paper only', detail: `EXECUTION_ENABLED is false, so no order reaches the venue. ${entries}`, tone: 'good' }
}

/** Held connector submissions waiting for a decision. Named for what they are, never called approvals. */
export function inboxLine(pending: number | null | undefined, atLeast = false): string {
  if (pending == null) return 'Held submissions could not be read.'
  if (pending === 0) return 'Nothing is held for review.'
  if (atLeast) return `At least ${pending} submissions are held for review.`
  return pending === 1 ? '1 submission is held for review.' : `${pending} submissions are held for review.`
}

/**
 * Enrolled notification phones. These are devices, not sessions: they sign nothing in.
 *
 * state-api lists them only to a browser session holding the mobile control key,
 * so a refusal is stated as that rather than as a failure.
 */
export function deviceLine(devices: { total: number; enabled: number } | undefined, refused = false): string {
  if (refused) return 'Enrolled phones are listed only while this browser session holds the mobile control key.'
  if (!devices) return 'Notification devices could not be read.'
  if (devices.total === 0) return 'No phone is enrolled for notifications.'
  const phones = devices.total === 1 ? '1 phone enrolled' : `${devices.total} phones enrolled`
  return `${phones}, ${devices.enabled} receiving notifications.`
}

/** What this browser session is holding. The nearest thing to a session that exists. */
export function sessionLine(tokenKept: boolean, mobileKeyKept: boolean): string {
  const held = [tokenKept ? 'the operator token' : null, mobileKeyKept ? 'the mobile control key' : null]
    .filter(Boolean)
  return held.length === 0
    ? 'This browser session holds no credential. Nothing is kept on disk.'
    : `This browser session is holding ${held.join(' and ')}. Both are dropped when the browser closes.`
}

/**
 * Forgetting what this browser holds — offered only when there is something to
 * forget. It is deliberately not called signing out: there is no session to end.
 */
export function forgetAction(tokenKept: boolean, mobileKeyKept: boolean): { label: string; enabled: boolean; detail: string } {
  const enabled = tokenKept || mobileKeyKept
  return {
    label: 'Forget credentials held in this browser',
    enabled,
    detail: enabled
      ? 'Clears the operator token and mobile control key from this browser session. Nothing on the server changes.'
      : 'Nothing is held in this browser session to forget.',
  }
}

export interface AuditTrail {
  label: string
  detail: string
  /** The Cockpit page where the record is read. */
  to: string
  /** The read-only state-api route that serves the same record as JSON, relative to the API base. */
  json: string
}

/**
 * Where the audited records actually live. Each export is the record itself, as
 * state-api serves it: a read that needs no operator token and changes nothing.
 * No file is generated and nothing is summarised on the way out.
 */
export const AUDIT_TRAILS: AuditTrail[] = [
  {
    label: 'Paper risk, pauses and the kill switch',
    detail: 'Every pause, kill and resume, with the operator and reason given.',
    to: '/signal-ledger',
    json: '/state/paper-risk',
  },
  {
    label: 'Paper limit changes',
    detail: 'Who changed a paper limit, when, why, and the value it replaced.',
    to: '/signal-ledger',
    json: '/state/paper-limits',
  },
  {
    label: 'Agent harness control',
    detail: 'Every stop and start, who asked, and what the host did.',
    to: '/agents',
    json: '/state/agents/harness/control?limit=200',
  },
  {
    label: 'Held submissions',
    detail: 'What each connector sent, and how it was decided.',
    to: '/intake',
    json: '/state/quarantine?limit=200',
  },
  {
    label: 'WalletConnect project ID changes',
    detail: 'Who saved or cleared it, when, and what it replaced.',
    to: '/settings',
    json: '/state/settings/walletconnect',
  },
  {
    label: 'Pipeline state changes',
    detail: 'Each stage entering a new state, newest first.',
    to: '/pipeline',
    json: '/state/integration-pipeline/history?limit=200',
  },
]
