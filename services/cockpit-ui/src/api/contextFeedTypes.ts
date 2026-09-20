// Macro headlines, context providers and the economic calendar. Moved unchanged from types.ts, which re-exports this file.

// === Phase 3C: Macro Feed Types ===

export interface MacroHeadline {
  title: string
  source: string
  category: string
  url: string
  published_at?: string
  summary?: string
  sentiment?: 'bullish' | 'bearish' | 'neutral'
}

export interface MacroFeedStatus {
  sources_configured: number
  headlines_cached: number
  cache_age_seconds?: number
  cache_ttl_seconds: number
  sources: string[]
  error?: string
}

export interface MacroFeedResponse {
  headlines: MacroHeadline[]
  status: MacroFeedStatus
  cached: boolean
  ts: string
}

export interface ContextProvider {
  provider: string
  status: 'healthy' | 'stale' | 'degraded' | 'unavailable' | 'disabled'
  source_type: 'context_only'
  execution_authority: false
  cached?: boolean
  stale?: boolean
  age_seconds?: number | null
  fetched_at?: string | null
  ttl_seconds?: number
  reason?: string
  error?: string
  data: {
    metric_family?: string
    assets?: Record<string, {
      price_usd: number
      change_24h_pct?: number | null
      observed_at?: number
    }>
    protocol?: string
    tvl_usd?: number
    series?: Record<string, { value: string; date: string }>
  }
}

/** One scheduled economic event, already validated and converted to UTC. */
export interface CalendarEvent {
  title: string
  country: string
  impact: 'High' | 'Medium' | 'Low' | 'Holiday'
  /** ISO 8601, UTC. FRED rows are date-only: midnight UTC of that date. */
  scheduled_at: string
  minutes_until: number
  source: 'forexfactory' | 'fred'
  forecast: string
  previous: string
  /** By title (FOMC, CPI, NFP…), not by the feed's own impact rating. */
  market_moving: boolean
  /** Where to read more: that day's ForexFactory calendar, or FRED's release calendar. */
  url?: string
}

export interface CalendarProviderData {
  metric_family?: 'economic_calendar'
  events?: CalendarEvent[]
  next_market_moving?: CalendarEvent | null
  counts?: { total: number; high: number; market_moving: number; rejected: number }
  rejections?: string[]
  sources?: string[]
  fred_configured?: boolean
}

export interface ContextOverviewResponse {
  role: 'context_only'
  authoritative_market_source: 'hyperliquid'
  execution_venue: 'hyperliquid'
  execution_authority: false
  providers: Record<'coingecko' | 'defillama' | 'fred', ContextProvider> & {
    calendar?: Omit<ContextProvider, 'data'> & { data: CalendarProviderData }
  }
  generated_at: string
}
