import { useExecutionStatus } from '../../api/hooks'
import styles from './WalletSafetyNotes.module.css'

/** Wallets in plain words, beside the watch-only account and QR pairing. */
export function WalletSafetyNotes() {
  const status = useExecutionStatus()
  const gate = status.isLoading
    ? { text: 'Reading the execution gate…', tone: 'tone-dim' }
    : status.isError
      ? { text: 'Execution gate status unavailable; TradeSync stays fail-closed.', tone: 'tone-warn' }
      : status.data?.execution_enabled === 'false'
        ? { text: 'Execution gate now: closed (EXECUTION_ENABLED=false).', tone: 'tone-good' }
        : { text: `Execution gate now: EXECUTION_ENABLED=${status.data?.execution_enabled ?? 'unknown'}. Review the gates above.`, tone: 'tone-bad' }

  return (
    <details className={styles.notes} open>
      <summary>How TradeSync uses wallets</summary>
      <ul className={styles.list}>
        <li>
          <strong>Never a seed phrase, private key or passphrase.</strong> TradeSync never asks for them and has nowhere to type them.
          Whoever holds one controls the wallet and everything in it, and no web page can keep it safe. If anything asks you to enter
          one into TradeSync, stop: it is not TradeSync. To import a wallet, use the wallet&apos;s own app.
        </li>
        <li>
          <strong>Watch a wallet by its public address.</strong> Paste the address (0x followed by 40 characters) into Public account
          address below and choose View account. TradeSync reads its balances, positions, open orders and fills from Hyperliquid&apos;s
          public data. Anyone can look up any address, so this proves nothing about ownership and cannot move funds.
        </li>
        <li>
          <strong>Pairing by QR shares only the address.</strong> WalletConnect asks your wallet app for the address and no signing
          methods, and TradeSync closes the session as soon as the address arrives. Approvals and signatures stay inside your wallet
          app: if it asks you to sign anything for TradeSync, reject it.
        </li>
        <li>
          <strong>Trading from TradeSync stays switched off.</strong> TradeSync keeps a paper ledger, and no wallet here can place an order.
          <span className={`${styles.gate} ${gate.tone}`}>{gate.text}</span>
        </li>
      </ul>
    </details>
  )
}
