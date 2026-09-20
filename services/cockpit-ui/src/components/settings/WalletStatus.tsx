import { Link } from 'react-router-dom'
import { useSignerStatus } from '../../api/hooks/useOperatorSettings'
import { useWalletConnectSettings } from '../../api/hooks/useWalletConnectSettings'
import { useWalletRegistry } from '../../api/hooks/useWalletRegistry'
import { ReadingStamp } from '../ReadingStamp'
import { signerLine } from './settingsText'
import { StandingRow } from './StandingRow'
import { savedLine } from './walletConnectText'
import styles from './SettingsPanels.module.css'

/**
 * Wallet connection status: whether a signer is reachable, whether pairing is set
 * up, and what TradeSync keeps of a wallet, which is nothing.
 */
export function WalletStatus() {
  const signer = useSignerStatus()
  const walletConnect = useWalletConnectSettings()
  const registry = useWalletRegistry()
  const saved = walletConnect.data
  const connected = registry.data?.wallets.filter((wallet) => wallet.status === 'active').length ?? 0

  return (
    <section className="panel" aria-labelledby="wallet-status-title">
      <div className="panel-heading">
        <div>
          <h3 id="wallet-status-title">Wallet connection</h3>
          <p>{connected ? `${connected} public account${connected === 1 ? '' : 's'} connected for read-only visibility.` : 'No wallet is connected. TradeSync can read a public address, and nothing more.'}</p>
        </div>
        <ReadingStamp
          at={signer.dataUpdatedAt || null}
          onRefresh={() => { void signer.refetch(); void walletConnect.refetch() }}
          refreshing={signer.isFetching || walletConnect.isFetching || registry.isFetching}
        />
      </div>
      <div className={styles.body}>
        <dl className={styles.standings}>
          <StandingRow name="Signer" standing={signerLine(signer.data, signer.isError)} />
          <div>
            <dt>WalletConnect pairing</dt>
            <dd className={styles.value}>
              {saved
                ? savedLine(saved.project_id, saved.updated_by, saved.updated_at)
                : walletConnect.isError ? 'The saved project ID could not be read.' : 'checking…'}
            </dd>
            <dd>Pairing shares a public address once and closes the session; no session is kept.</dd>
          </div>
          <div>
            <dt>Connected public accounts</dt>
            <dd className={styles.value}>{registry.isError ? 'Registry unavailable' : connected}</dd>
            <dd>These records grant no signing or order authority.</dd>
          </div>
          <div>
            <dt>Watched addresses</dt>
            <dd className={styles.value}>None kept</dd>
            <dd>A watch-only lookup on Execution Readiness reads one public address for that visit; the Cockpit keeps no address.</dd>
          </div>
        </dl>
        <p className={styles.note}>
          Every gate between paper research and a live order is listed on <Link to="/execution">Execution Readiness</Link>.
        </p>
      </div>
    </section>
  )
}
