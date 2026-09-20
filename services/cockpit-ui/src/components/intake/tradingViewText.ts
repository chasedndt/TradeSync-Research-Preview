import type { TradingViewReceipt } from '../../api/tradingViewSetupTypes'

/** TradingView sends {{interval}} in minutes when it is a bare number ("15", "240"); "1D", "1h" or "15m" are shown as sent. */
export function intervalLabel(interval: unknown): string {
  const text = interval == null ? '' : String(interval).trim()
  return /^\d+$/.test(text) ? `${text}m` : text
}

/** "13 Sep 2026, 22:24:15": the exact local time. */
export const exactTime = (iso: string | null | undefined): string =>
  iso
    ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : 'an unknown time'

/** "checked 21:04:05 · refreshes every 30 s": when this page last read the setup. */
export const checkedLine = (updatedAt: number): string =>
  updatedAt
    ? `checked ${new Date(updatedAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })} · refreshes every 30 s`
    : 'checking…'

/** The message template as it is pasted into TradingView: indented JSON, in template order. */
export const templateText = (template: Record<string, string>): string => JSON.stringify(template, null, 2)

/** The <...> values an operator replaces by hand, apart from the secret. */
export const manualPlaceholders = (template: Record<string, string>, secretPlaceholder: string): string[] =>
  Object.values(template).filter((value) => /^<[^<>]+>$/.test(value) && value !== secretPlaceholder)

export function receiptTitle(receipt: Pick<TradingViewReceipt, 'indicator' | 'ticker' | 'interval'>): string {
  return [receipt.indicator || 'Indicator not named', receipt.ticker || 'no ticker', intervalLabel(receipt.interval)].filter(Boolean).join(' · ')
}

export function receiptVerdict(receipt: Pick<TradingViewReceipt, 'accepted' | 'reasons' | 'review'>): { text: string; tone: 'tone-good' | 'tone-bad' } {
  if (receipt.accepted) return { text: `Accepted into quarantine, ${receipt.review}`, tone: 'tone-good' }
  const reasons = receipt.reasons.map((reason) => (reason.detail ? `${reason.code}: ${reason.detail}` : reason.code)).join('; ')
  return { text: reasons ? `Refused: ${reasons}` : 'Refused; no reason was recorded', tone: 'tone-bad' }
}

/** Only ever whether the secret is configured: the dashboard never receives its value. */
export function secretLine(configured: boolean): string {
  return configured
    ? 'Webhook secret: configured. TradeSync accepts only alerts that carry it.'
    : 'Webhook secret: not configured. TradeSync refuses every TradingView alert until it is set.'
}

export function lastReceiptLine(receipts: Pick<TradingViewReceipt, 'accepted' | 'received_at'>[]): string {
  const latest = receipts[0]
  return latest ? `Latest alert stored ${exactTime(latest.received_at)}, ${latest.accepted ? 'accepted' : 'refused'}` : 'No TradingView alert stored yet.'
}
