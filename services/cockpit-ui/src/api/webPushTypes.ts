/** The Web Push routes (/state/mobile-alerts/web-push*) as Settings reads them. */

export type KeyState = 'missing' | 'malformed' | 'ok'

export type WebPushStatus = {
  /** A usable key pair: a browser may subscribe. */
  configured: boolean
  /** Public by design: a browser sends it to its push service. The private key is never in this answer. */
  public_key: string | null
  public_key_state: KeyState
  private_key_state: KeyState
  /** Whether the sender's contact is set. The address itself is never returned. */
  subject_state: KeyState
  sender_implemented: boolean
  /** The pair and the contact are both in place, so alerts for a subscribed phone go out over Web Push. */
  sender_ready: boolean
  public_key_env: string
  private_key_env: string
  subject_env: string
  problem: string | null
  sender_problem: string | null
  note: string
  delivery: string
}

export type WebPushSubscription = {
  id: string
  device_id: string
  device_label: string | null
  platform: string | null
  device_enabled: boolean | null
  /** The push service the browser gave us, for example fcm.googleapis.com. The endpoint itself never arrives. */
  push_service: string | null
  endpoint_digest: string
  label: string
  created_at: string | null
  last_seen_at: string | null
  /** False once its push service reported it gone; nothing is sent to it after that. */
  active: boolean
  last_attempt_at: string | null
  last_status: number | null
  last_error: string | null
  accepted_at: string | null
  expired_at: string | null
  expired_reason: string | null
}

export type WebPushSubscriptions = {
  subscriptions: WebPushSubscription[]
  configured: boolean
  sender_implemented: boolean
  sender_ready: boolean
  note: string
}
