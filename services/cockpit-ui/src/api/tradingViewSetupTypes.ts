/** GET /state/tradingview/setup: what an operator needs to point a TradingView alert at TradeSync, and what arrived. */

export interface TradingViewReceipt {
  id: string
  received_at: string
  /** Stored alerts only: an alert refused for authentication is never stored. */
  accepted: boolean
  indicator: string
  ticker: string
  interval: string
  reasons: { code: string; detail: string }[]
  review: 'awaiting review' | 'reviewed' | 'promoted'
}

export interface TradingViewSetup {
  schema_version: string
  webhook_url: string
  /** Whether TRADINGVIEW_WEBHOOK_SECRET is set. The value itself never reaches the dashboard. */
  secret_configured: boolean
  contract: string
  required_fields: string[]
  secret_placeholder: string
  /** In the order it is pasted. */
  message_template: Record<string, string>
  /** Newest first. */
  receipts: TradingViewReceipt[]
  receipts_error: string | null
  /** The text on the receiver's log line for an alert refused before storage. */
  refusal_log_marker: string
  authority: string
  note: string
}
