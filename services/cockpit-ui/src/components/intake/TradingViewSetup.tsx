import { useTradingViewSetup } from '../../api/hooks/useTradingViewSetup'
import { TradingViewReceipts } from './TradingViewReceipts'
import { TradingViewSteps } from './TradingViewSteps'
import { checkedLine, lastReceiptLine, secretLine } from './tradingViewText'
import styles from './TradingViewSetup.module.css'

/**
 * TradingView alerts into TradeSync, on Knowledge intake: whether the webhook secret is configured, what happens to
 * an alert, how to set one up, and the latest receipts. The secret never reaches this page, and nothing trades
 * from an alert.
 */
export function TradingViewSetup() {
  const setup = useTradingViewSetup()
  const data = setup.data
  const stepsOpen = Boolean(data && (!data.secret_configured || data.receipts.length === 0))

  return (
    <section className={`panel ${styles.panel}`} aria-label="TradingView alerts">
      <div className={styles.heading}>
        <div>
          <h3>TradingView alerts into TradeSync</h3>
          <p>Point a TradingView alert at TradeSync and it arrives on this page as evidence for you to review. Nothing trades from it.</p>
        </div>
        <span className={styles.checked}>{checkedLine(setup.dataUpdatedAt)}</span>
      </div>

      {setup.isError && <p className="tone-bad">TradingView setup unavailable: {setup.error?.message ?? 'no answer'}</p>}
      {setup.isLoading && <p className="tone-dim">Reading the TradingView setup…</p>}

      {data && (
        <>
          <ul className={styles.status}>
            <li className={data.secret_configured ? 'tone-good' : 'tone-warn'}>{secretLine(data.secret_configured)}</li>
            <li>{lastReceiptLine(data.receipts)}</li>
          </ul>

          <div className={styles.next}>
            <span className="pipeline-detail-label">What happens when an alert fires</span>
            <ol>
              <li>TradingView posts the alert message to <span className={styles.url}>{data.webhook_url}</span>.</li>
              <li>TradeSync checks the secret, removes it, and keeps the rest in the list below under <strong>Pine alerts</strong>, awaiting your review.</li>
              <li>It stays evidence: it cannot score, approve or execute, and nothing trades from it. Promoting it is your decision.</li>
              <li>
                An alert with a wrong or missing secret, a message that is not JSON, or no indicator or ticker is refused before it is
                stored, so it does not appear here. The last setup step shows how to see why.
              </li>
            </ol>
          </div>

          <details className={styles.setup} open={stepsOpen}>
            <summary>How to set up an alert</summary>
            <TradingViewSteps setup={data} />
          </details>

          <TradingViewReceipts receipts={data.receipts} error={data.receipts_error} />
        </>
      )}
    </section>
  )
}
