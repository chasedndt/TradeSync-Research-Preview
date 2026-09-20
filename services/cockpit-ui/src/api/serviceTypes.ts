// Service health and the ingest snapshot. Moved unchanged from types.ts, which re-exports this file.

export interface HealthResponse {
  status: string
  postgres: boolean
  last_event_ts: string | null
  last_signal_ts: string | null
  latency_ms: number
}

export interface SnapshotResponse {
  latest_event_ts: string | null
  latest_signal_ts: string | null
  latest_opportunity_ts: string | null
  execution_gate: string
  hl_status: string
  hl_circuit: CircuitStatus | null
  stream_lengths: Record<string, number>
  ingest_sources: IngestSource[]
}

export interface CircuitStatus {
  venue: string
  circuit_open: boolean
  fail_count: number
  last_fail_reason?: string
  last_fail_ts?: string
}

export interface IngestSource {
  source: string
  symbols: string[]
  interval_sec: number
  last_poll_ts?: string
}
