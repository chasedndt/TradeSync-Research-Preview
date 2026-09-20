/** The mobile notification routes (/state/mobile-alerts/*) as the Settings page reads them. */

export type NotificationPreferences = {
  paper_events?: boolean
  control_events?: boolean
  timezone?: string
  quiet_enabled?: boolean
  quiet_start?: number
  quiet_end?: number
  daily_budget?: number
}

export type MobileStatus = { configured: boolean; worker_running: boolean; note: string }

export type MobileDevice = {
  id: string
  label: string
  platform: string
  enabled: boolean
  operator_confirmed_at: string | null
  notification_preferences?: NotificationPreferences
}

export type MobileEvent = {
  id: string
  device_id: string
  kind: string
  status: string
  attempts: number
  created_at: string
  last_error: string | null
}

export type MobileDevices = { devices: MobileDevice[]; events: MobileEvent[] }

/** One row of the delivery ledger (/state/mobile-alerts/ledger): every delivery fact, with exact times. */
export type LedgerEvent = MobileEvent & {
  device_label: string | null
  platform: string | null
  /** Which transport carried the latest attempt: 'ntfy' or 'web_push'; null before any attempt. */
  transport: string | null
  next_attempt_at: string | null
  attempted_at: string | null
  accepted_at: string | null
  confirmed_at: string | null
  acknowledged_at: string | null
  acknowledged_by: string | null
  dead_lettered_at: string | null
  dead_letter_reason: string | null
  expires_at: string | null
}

export type DeliveryLedger = {
  events: LedgerEvent[]
  max_attempts: number
  /** The wait before each retry, in seconds, as the server applies it. */
  retry_seconds: number[]
  expiry_seconds: number
  note: string
}
