/** The agent harness kill switch as state-api reports it: GET and POST /state/agents/harness/control. */

export type HarnessState = 'running' | 'stopped'
export type HarnessHostStatus = 'none' | 'pending' | 'applying' | 'applied' | 'failed'
export type HarnessAgreementState = 'agree' | 'pending' | 'disagree' | 'unknown'
export type HarnessEventKind = 'requested' | 'applying' | 'applied' | 'failed'

export interface HarnessHostResult {
  command_id: string
  status: 'applied' | 'failed'
  command: string | null
  exit_status: number | null
  is_active: string | null
  detail: string | null
  at: string | null
  for_current_command: boolean
}

export interface HarnessHost {
  status: HarnessHostStatus
  command_id: string | null
  claimed_at: string | null
  result: HarnessHostResult | null
  last_poll_at: string | null
  seconds_since_poll: number | null
  poll_interval_s: number
}

export interface HarnessGatewayHealth {
  status: 'live' | 'degraded' | 'offline' | 'checking' | 'not_configured'
  last_seen_at: string | null
  seconds_since_seen: number | null
  last_error: string | null
  consecutive_failures: number
}

export interface HarnessControlEvent {
  id: string
  created_at: string
  kind: HarnessEventKind
  command_id: string
  desired_state: HarnessState
  previous_state: HarnessState | null
  operator: string | null
  reason: string | null
  command: string | null
  exit_status: number | null
  is_active: string | null
  detail: string | null
}

export interface HarnessDesired {
  state: HarnessState
  operator: string
  reason: string
  requested_at: string
  command_id: string | null
}

export interface HarnessControl {
  schema_version: 'agent_harness_control_v1'
  generated_at: string
  desired: HarnessDesired
  host: HarnessHost
  gateway: HarnessGatewayHealth
  gate: { open: boolean; reason: string | null }
  agreement: { state: HarnessAgreementState; message: string }
  history: HarnessControlEvent[]
  note: string
}

export interface HarnessChangeBody {
  desired_state: HarnessState
  operator: string
  reason: string
  confirm: true
}
