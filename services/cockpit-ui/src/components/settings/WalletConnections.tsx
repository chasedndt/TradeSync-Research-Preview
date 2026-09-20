import { useNavigate } from 'react-router-dom'
import { useAddWallet } from '../../api/hooks/useWalletRegistry'
import { WalletPairing } from '../WalletPairing'
import { readOperator } from '../learning/format'
import { WalletManager } from '../wallet/WalletManager'
import styles from './SettingsPanels.module.css'

/** Secondary wallet routes live here so the global header remains one-action Phantom connect. */
export function WalletConnections() {
  const add = useAddWallet()
  const navigate = useNavigate()

  async function rememberPairedAddress(address: string) {
    await add.mutateAsync({
      address,
      connector: 'walletconnect',
      label: 'Wallet app · Hyperliquid',
      operator: readOperator().trim() || 'local operator',
      reason: 'Public address shared through a short-lived WalletConnect session; no signing authority retained.',
    })
  }

  return (
    <section className="panel" aria-labelledby="wallet-connections-title">
      <div className="panel-heading">
        <div>
          <h3 id="wallet-connections-title">Wallet connections</h3>
          <p>Manage connected public addresses and optional phone pairing away from the trading header.</p>
        </div>
        <span className="chip">NO SIGNING</span>
      </div>
      <div className={styles.body}>
        <WalletManager onAddress={(address) => navigate(`/execution?wallet=${encodeURIComponent(address)}`)} />
        <details>
          <summary>Pair a phone or standalone wallet</summary>
          <WalletPairing onAddress={(address) => void rememberPairedAddress(address)} />
        </details>
        <p className={styles.note}>
          To inspect any public address without connecting a wallet, use Watch-only account on Execution Readiness.
        </p>
      </div>
    </section>
  )
}
