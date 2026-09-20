import type { WalletConnectChange } from '../../api/walletConnectSettingsTypes'

export const PROJECT_ID_PATTERN = /^[0-9a-fA-F]{32}$/
export const REOWN_DASHBOARD = 'https://dashboard.reown.com'

// Twelve or more words is the shape of a recovery phrase; 64 hexadecimal characters is the shape of a private key.
const PHRASE_SHAPE = /^[a-z]+(\s+[a-z]+){11,}$/i
const KEY_SHAPE = /^(0x)?[0-9a-fA-F]{64}$/

export type ProjectIdCheck =
  | { ok: true; value: string }
  | { ok: false; kind: 'empty' | 'shape' | 'looks_secret'; message: string }

/** Whether typed text can be saved as a project ID. Text shaped like a recovery phrase or key is never sent. */
export function checkProjectId(input: string): ProjectIdCheck {
  const value = input.trim()
  if (!value) return { ok: false, kind: 'empty', message: 'Paste the Project ID from the Reown dashboard.' }
  if (PHRASE_SHAPE.test(value) || KEY_SHAPE.test(value)) {
    return {
      ok: false,
      kind: 'looks_secret',
      message: 'That looks like a recovery phrase or a private key. It was not sent anywhere and has been cleared from the box. '
        + 'TradeSync never needs one. A project ID is 32 characters, digits and the letters a to f.',
    }
  }
  if (!PROJECT_ID_PATTERN.test(value)) {
    return { ok: false, kind: 'shape', message: 'A project ID is 32 characters, digits and the letters a to f. Check that you copied the Project ID.' }
  }
  return { ok: true, value }
}

/** "15 Sep 2026, 21:04": an absolute local time. */
export const localTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'an unknown time'

/** "012345…cdef": enough to recognise a public ID in a history line. */
export const shortId = (id: string | null): string => (id ? `${id.slice(0, 6)}…${id.slice(-4)}` : 'not set')

export function savedLine(projectId: string | null, updatedBy: string | null, updatedAt: string | null): string {
  return projectId
    ? `Saved by ${updatedBy ?? 'an unknown operator'} on ${localTime(updatedAt)}`
    : 'Not saved yet. Pairing by QR asks for a project ID until one is saved.'
}

export function changeLine(change: WalletConnectChange): string {
  const what = change.next ? `Set to ${shortId(change.next)}` : 'Cleared'
  return `${what} by ${change.changed_by} on ${localTime(change.changed_at)}; was ${shortId(change.previous)}`
}

/** What the pairing panel says before a pairing starts. */
export function pairingIdleMessage(savedId: string, typed: string): string {
  if (!savedId) {
    return 'Setup required: save your public WalletConnect project ID in Settings, or paste it here for this pairing only. '
      + 'Address lookup below works without it.'
  }
  return typed.trim() === savedId
    ? 'Using the project ID saved in Settings. You can change it here for this pairing only.'
    : 'Using a project ID typed here for this pairing only. The one saved in Settings is unchanged.'
}
