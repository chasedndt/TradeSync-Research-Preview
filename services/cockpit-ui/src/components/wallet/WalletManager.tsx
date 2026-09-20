import { readOperator } from '../learning/format'
import { useDisconnectWallet, useWalletRegistry } from '../../api/hooks/useWalletRegistry'
import { shortAddress } from './provider'

export function WalletManager({ onAddress }: { onAddress: (address: string) => void }) {
  const registry = useWalletRegistry()
  const disconnect = useDisconnectWallet()
  const active = registry.data?.wallets.filter((wallet) => wallet.status === 'active') ?? []
  return <section className="wallet-registry" aria-label="Connected wallet accounts">
    <div className="wallet-registry__intro">
      <div><h3>Connected accounts</h3><p>Use <strong>Connect wallet</strong> in the top bar to open the wallet chooser.</p></div>
      <span className="chip">PUBLIC ADDRESS ONLY</span>
    </div>
    {registry.isLoading && <p className="metric-sub">Reading the wallet registry…</p>}
    {!registry.isLoading && active.length === 0 && <div className="wallet-registry__empty">
      <img src="/brand/phantom-icon.svg" alt="" />
      <div><strong>No wallet connected</strong><span>Open Connect wallet above, then approve address sharing in Phantom.</span></div>
    </div>}
    {active.map((wallet) => <div key={wallet.id} className="wallet-registry__row">
      <img src={wallet.connector === 'phantom' ? '/brand/phantom-icon.svg' : '/brand/tradesync-mark.png'} alt="" />
      <div><strong>{wallet.label}</strong><span>{shortAddress(wallet.address)} · {wallet.connector.replace('_', ' ')}</span></div>
      <button type="button" className="chip" onClick={() => onAddress(wallet.address)}>View</button>
      <button type="button" className="chip" disabled={disconnect.isPending} onClick={() => void disconnect.mutateAsync({ id: wallet.id, operator: readOperator().trim() || 'local operator', reason: 'Disconnected from Execution Readiness' })}>Disconnect</button>
    </div>)}
    <p className="metric-sub">To restore/import with 12 or 24 words, use Phantom’s own app. TradeSync intentionally has no recovery-phrase or private-key form.</p>
  </section>
}
