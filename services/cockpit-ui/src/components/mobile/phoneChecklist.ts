/**
 * Phone notification setup as a checklist, each step marked from live state where TradeSync can see it.
 *
 * TradeSync cannot see a phone. Installing ntfy and subscribing are proved only by a test the operator received
 * and confirmed, so until then those steps read "check on the phone" rather than done or not.
 */

export type Platform = 'android' | 'ios'
export type StepState = 'done' | 'todo' | 'waiting' | 'unseen' | 'problem'
export type StepId = 'app' | 'server_key' | 'session_key' | 'enroll' | 'subscribe' | 'test' | 'confirm'

export interface ChecklistDevice { id: string; platform: string; enabled: boolean; operator_confirmed_at: string | null }
export interface ChecklistEvent { device_id: string; kind: string; status: string }

export interface ChecklistInput {
  /** Whether MOBILE_ALERTS_CONTROL_KEY is configured; undefined while the status is read. */
  configured: boolean | undefined
  /** Whether a key is kept in this browser session. */
  keyEntered: boolean
  /** The device list answered: the key kept here matches the server's. */
  authorized: boolean
  /** The device list refused the request. */
  refused: boolean
  devices: ChecklistDevice[]
  events: ChecklistEvent[]
}

export interface PhoneProgress { enrolled: boolean; test: 'none' | 'pending' | 'accepted' | 'failed'; confirmed: boolean }
export interface ChecklistStep { id: StepId; title: string; marks: { label: string; state: StepState }[] }

export const PLATFORMS: { id: Platform; label: string }[] = [
  { id: 'android', label: 'Android' },
  { id: 'ios', label: 'iPhone' },
]

/** The official ntfy phone apps, as linked from https://docs.ntfy.sh/subscribe/phone/ (checked 15 September 2026). */
export const NTFY_APPS = [
  { label: 'Android: Google Play', url: 'https://play.google.com/store/apps/details?id=io.heckel.ntfy' },
  { label: 'Android: F-Droid', url: 'https://f-droid.org/en/packages/io.heckel.ntfy/' },
  { label: 'iPhone: App Store', url: 'https://apps.apple.com/us/app/ntfy/id1625396347' },
]

export const STATE_WORDS: Record<StepState, string> = {
  done: 'done',
  todo: 'to do',
  waiting: 'not yet',
  unseen: 'check on the phone',
  problem: 'needs attention',
}

const ACCEPTED = new Set(['provider_accepted', 'operator_confirmed'])
const PENDING = new Set(['queued', 'sending', 'retry'])

/** One platform's enabled phones: enrolled, the best test outcome so far, and whether receipt was confirmed. */
export function phoneProgress(input: Pick<ChecklistInput, 'devices' | 'events'>, platform: Platform): PhoneProgress {
  const phones = input.devices.filter((device) => device.enabled && device.platform === platform)
  const ids = new Set(phones.map((device) => device.id))
  const tests = input.events.filter((event) => event.kind === 'test' && ids.has(event.device_id)).map((event) => event.status)
  const test = tests.some((status) => ACCEPTED.has(status)) ? 'accepted'
    : tests.some((status) => PENDING.has(status)) ? 'pending'
      : tests.length > 0 ? 'failed' : 'none'
  return { enrolled: phones.length > 0, test, confirmed: phones.some((device) => Boolean(device.operator_confirmed_at)) }
}

export function checklist(input: ChecklistInput): ChecklistStep[] {
  const ready = input.configured === true && input.authorized
  const perPhone = (decide: (phone: PhoneProgress) => StepState) =>
    PLATFORMS.map(({ id, label }) => ({ label, state: decide(phoneProgress(input, id)) }))
  const serverKey: StepState = input.configured === undefined ? 'waiting' : input.configured ? 'done' : 'todo'
  const sessionKey: StepState = input.configured !== true ? 'waiting'
    : input.authorized ? 'done'
      : input.keyEntered && input.refused ? 'problem' : 'todo'

  return [
    { id: 'app', title: 'Install the free ntfy app on each phone', marks: perPhone((phone) => (phone.confirmed ? 'done' : 'unseen')) },
    { id: 'server_key', title: 'Set the mobile control key on this PC', marks: [{ label: 'This PC', state: serverKey }] },
    { id: 'session_key', title: 'Enter the key in this browser session', marks: [{ label: 'This browser', state: sessionKey }] },
    { id: 'enroll', title: 'Create subscription details for each phone', marks: perPhone((phone) => (phone.enrolled ? 'done' : ready ? 'todo' : 'waiting')) },
    { id: 'subscribe', title: 'Subscribe to the topic in ntfy', marks: perPhone((phone) => (phone.confirmed ? 'done' : phone.enrolled ? 'unseen' : 'waiting')) },
    {
      id: 'test',
      title: 'Send the generic test',
      marks: perPhone((phone) => (phone.confirmed || phone.test === 'accepted' ? 'done'
        : phone.test === 'pending' ? 'waiting'
          : phone.test === 'failed' ? 'problem'
            : phone.enrolled && ready ? 'todo' : 'waiting')),
    },
    {
      id: 'confirm',
      title: 'Confirm it arrived on the phone',
      marks: perPhone((phone) => (phone.confirmed ? 'done' : phone.test === 'accepted' ? 'todo' : 'waiting')),
    },
  ]
}

/** How many steps still have something not done. */
export const stepsRemaining = (steps: ChecklistStep[]): number =>
  steps.filter((step) => step.marks.some((mark) => mark.state !== 'done')).length
