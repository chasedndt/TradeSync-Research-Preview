// The Hermes fleet read model and its directives. Moved unchanged from types.ts, which re-exports this file.

// === Hermes fleet (read model fed by the host bridge) ===

export interface FleetSchedule { kind?: 'interval' | 'cron'; minutes?: number; expr?: string; display?: string }

export interface FleetJob {
  state_source?: 'gateway' | 'bridge'
  gateway_missing?: boolean
  failure_streak?: number
  job_id: string
  name: string
  enabled: boolean
  schedule: FleetSchedule
  schedule_display: string
  deliver: string
  workdir: string | null
  script: string | null
  no_agent: boolean
  model: string | null
  description: string
  last_run_at: string | null
  last_status: string | null
  next_run_at: string | null
  state: string | null
  last_error?: string | null
  last_delivery_error?: string | null
  snapshot_at: string
  runs_24h: number
  failed_24h: number
  tokens_24h: number
  tokens_7d: number
  fires_7d: number
  pending_directives: { kind: string; payload: Record<string, unknown>; requested_at: string }[]
  /** The Discord target this job had before it was switched to TradeSync only. */
  restorable_deliver?: string | null
}

export interface FleetJobsResponse {
  live_state?: { source: 'gateway' | 'bridge'; status: string; observed_at: string | null; cache_seconds: number }
  schema_version: 'fleet_jobs_v1'
  jobs: FleetJob[]
  snapshot_at: string | null
  presets: Record<string, FleetSchedule>
  note: string
  control?: { gateway_api: boolean; gateway_status: string; note: string }
}

export interface FleetUsageResponse {
  schema_version: 'fleet_usage_v1'
  days: number
  daily: { day: string; fires: number; prompt_tokens: number; completion_tokens: number; total_tokens: number }[]
  by_job: { job_id: string; name: string; fires: number; total_tokens: number; avg_tokens: number; avg_duration_ms: number }[]
  runs: { runs?: number; failed?: number; completed?: number }
  note: string
}

export interface FleetDirective {
  id: string
  job_id: string
  name?: string | null
  kind: FleetDirectiveKind
  payload: Record<string, unknown>
  requested_by: string
  requested_at: string
  status: 'pending' | 'applied' | 'failed'
  applied_at: string | null
  previous: Record<string, unknown> | null
  detail: string
  /** "api": applied at once by the Hermes gateway's jobs API; "bridge": the host bridge edits jobs.json. */
  channel?: 'api' | 'bridge'
}

export type FleetDirectiveKind = 'set_schedule' | 'set_enabled' | 'set_workdir' | 'set_deliver' | 'pause' | 'resume' | 'run_now'
