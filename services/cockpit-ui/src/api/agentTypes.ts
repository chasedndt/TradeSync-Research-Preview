// The advisory harness, agent posts and source cards. Moved unchanged from types.ts, which re-exports this file.

import type { SkillGateCell, SkillGateResponse } from './outcomeEvidenceTypes'

// === Agents (Discord reader + advisory harness) ===

export interface HarnessStatus {
  status: 'not_configured' | 'offline' | 'live'
  url: string | null
  models: string[]
  detail?: string
  boundary: { may_explain: boolean; may_compare: boolean; may_draft_proposals: boolean; may_score: boolean; may_approve: boolean; may_execute: boolean }
  note: string
}

/** The payload the discord-reader files for one message (discord_message_v1). */
export interface DiscordMessagePayload {
  schema_version: 'discord_message_v1'
  kind: 'discord_message'
  agent: string
  channel_kind: 'agent' | 'alerts' | 'operator'
  channel_id: string
  message_id: string
  author: { id: string; name: string; bot: boolean }
  content: string
  content_truncated: boolean
  embeds: { title: string; description: string; url: string; fields: { name: string; value: string }[] }[]
  attachments: { filename: string; content_type: string; size: number | null; url: string }[]
  posted_at: string | null
  edited_at: string | null
}

/** The payload the host bridge files for one Hermes cron job run (hermes_job_output_v1). */
export interface HermesJobOutputPayload {
  schema_version: 'hermes_job_output_v1'
  kind: 'hermes_job_output'
  agent: string
  job_id: string
  job_enabled: boolean
  schedule: string
  delivery: { kind: string; channel_id: string | null; channel_label: string | null }
  ran_at_stamp: string
  content: string
  content_truncated: boolean
  filename: string
}

export type AgentPostPayload = DiscordMessagePayload | HermesJobOutputPayload

/** One horizon × polarity cell of a source card; same fields as a skill-gate cell. */
export interface SourceCardCell extends Omit<SkillGateCell, 'regime'> {
  polarity: 'as_stated' | 'inverted'
  earned: boolean
}

export interface SourceCard {
  source: 'tradingview' | 'discord' | 'chaseos' | string
  source_id: string
  claims: number
  claims_measured: number
  latest_claim_at: string | null
  cells: SourceCardCell[]
  earned: boolean
  earned_by: string[]
  next_step: string
}

export interface SourceCardsResponse {
  schema_version: 'source_cards_v1'
  symbol: string | null
  horizons: number[]
  polarities: ['as_stated', 'inverted']
  cards: SourceCard[]
  cells_assessed_together: number
  extraction: { rows_with_claims: number; rows_without_claims: number; rows_pending: number }
  costs: SkillGateResponse['costs']
  note: string
}
