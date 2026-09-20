// The integration pipeline inspector. Moved unchanged from types.ts, which re-exports this file.

// === Integration Pipeline ===

export type PipelineNodeStatus =
  | 'live'
  | 'healthy'
  | 'partial'
  | 'offline'
  | 'contract_only'
  | 'planned'
  | 'locked'

export interface PipelineRecovery {
  kind: string
  label: string
  target: string
  command?: string | null
}

export interface PipelineNode {
  id: string
  label: string
  owner: string
  tier: string
  stage: string
  status: PipelineNodeStatus
  required_for_tier_a: boolean
  authority: string
  summary: string
  evidence: string[]
  missing: string[]
  impact: string
  recovery: PipelineRecovery
  /** How long this stage has held its current state. Null when unrecorded. */
  state_since_epoch_s?: number | null
  state_duration_seconds?: number | null
  /** Coarse phrasing, e.g. "2h 15m" or "unknown". */
  state_age?: string
  /** State changes in the last 15 minutes. */
  recent_transitions?: number
  /** Oscillating rather than settled: read the current state with suspicion. */
  flapping?: boolean
  research_run?: {
    schema_version: 'strikezone_research_evidence_v1'
    run_slug: string
    run_date?: string | null
    status: string
    public_ready_evidence: boolean
    validation_ok: boolean
    validation_missing: string[]
    evidence_item_count: number
    source_counts: Record<string, number>
    required_source_classes: string[]
    missing_source_classes: string[]
    source_tolerance: {
      allowed_missing_count: number
      missing_count: number
      degraded: boolean
      over_limit: boolean
    }
    charts_captured: number
    charts_expected: number
    assets: string[]
    operator_approval_required: boolean
    external_delivery_performed: boolean
    trade_execution_allowed: boolean
    fresh: boolean
    age_seconds?: number | null
    source_updated_at?: string | null
    snapshot_at?: string | null
  }
}

export interface PipelineRecoveryItem {
  node_id: string
  label: string
  status: PipelineNodeStatus
  required_for_tier_a: boolean
  missing: string[]
  impact: string
  recovery: PipelineRecovery
}

export interface IntegrationPipelineStatus {
  schema_version: 'integration_pipeline_status_v1'
  generated_at: string
  mode: 'paper'
  execution_authority: false
  tier_a: {
    status: 'ready' | 'partial' | 'offline'
    ready_count: number
    total_count: number
    principle: string
  }
  federated: {
    status: 'connected' | 'not_connected'
    connected_count: number
    total_count: number
  }
  nodes: PipelineNode[]
  edges: Array<{
    from: string
    to: string
    label: string
    status: 'flowing' | 'partial' | 'not_connected' | 'locked'
  }>
  recovery_queue: PipelineRecoveryItem[]
  capability_gaps: Array<{
    id: string
    status: string
    blocking: string
    next_action: string
  }>
}
