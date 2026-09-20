import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import { readOperator } from '../learning/format'
import { useAddWallet, useDisconnectWallet, useWalletRegistry } from '../../api/hooks/useWalletRegistry'
import type { DetectedWallet, PhantomDetection } from './provider'
import { detectPhantom, requestPublicAddress, shortAddress } from './provider'
import styles from './WalletConnectMenu.module.css'

export function WalletConnectMenu() {
  const registry = useWalletRegistry()
  const add = useAddWallet()
  const disconnect = useDisconnectWallet()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [detection, setDetection] = useState<PhantomDetection>({ wallet: null, extensionDetected: false })
  const [detecting, setDetecting] = useState(false)
  const [message, setMessage] = useState('')
  const active = registry.data?.wallets.filter((wallet) => wallet.status === 'active') ?? []

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    setDetecting(true)
    void detectPhantom().then(setDetection).finally(() => setDetecting(false))
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [open])

  async function connect(wallet: DetectedWallet) {
    setMessage('')
    try {
      const address = await requestPublicAddress(wallet)
      await add.mutateAsync({
        address,
        connector: wallet.connector,
        label: wallet.connector === 'phantom' ? 'Phantom · Hyperliquid' : `${wallet.name} · Hyperliquid`,
        operator: readOperator().trim() || 'local operator',
        reason: `Public address shared through ${wallet.name}; TradeSync requested no signature or key.`,
      })
      setMessage(`${wallet.name} connected for read-only Hyperliquid account visibility.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The wallet connection was cancelled or unavailable.')
    }
  }

  function inspect(address: string) {
    setOpen(false)
    navigate(`/execution?wallet=${encodeURIComponent(address)}`)
  }

  const first = active[0]
  async function refreshWallets() {
    setDetecting(true)
    setMessage('')
    try { setDetection(await detectPhantom()) } finally { setDetecting(false) }
  }
  return <div className={styles.root}>
    <button type="button" className={styles.trigger} onClick={() => setOpen(true)} aria-label={first ? `Wallets. ${first.label} ${shortAddress(first.address)}` : 'Connect wallet'}>
      <img src="/brand/phantom-icon.svg" alt="" />
      <span className={styles.triggerCopy}>
        <strong>{first ? shortAddress(first.address) : 'Connect wallet'}</strong>
        {first && <small>{active.length} connected</small>}
      </span>
    </button>
    {open && <div className={styles.backdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
      <section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="wallet-dialog-title">
        <header className={styles.head}>
          <div><h2 id="wallet-dialog-title">Phantom</h2><p>Connect your public Hyperliquid account address.</p></div>
          <button type="button" className={styles.close} onClick={() => setOpen(false)} aria-label="Close wallet menu"><X size={17} /></button>
        </header>
        <div className={styles.body}>
          <p className={styles.notice}><strong>Public address only.</strong> TradeSync never asks for your recovery phrase or private key.</p>
          {detecting && <div className={styles.detecting}><img src="/brand/phantom-icon.svg" alt="" /><span>Looking for Phantom…</span></div>}
          {!detecting && detection.wallet && <button type="button" className={styles.walletOption} onClick={() => void connect(detection.wallet as DetectedWallet)} disabled={add.isPending}>
            <img src="/brand/phantom-icon.svg" alt="" />
            <span><strong>Connect Phantom</strong><span>Approve public address sharing in Phantom</span></span>
            <span className={styles.arrow}>→</span>
          </button>}
          {!detecting && !detection.wallet && <div className={styles.missingWallet}>
            <img src="/brand/phantom-icon.svg" alt="Phantom" />
            <div><strong>Phantom is not available to this TradeSync tab</strong><span>{detection.extensionDetected ? 'The extension is present, but its Ethereum provider is not available here.' : 'Allow Phantom on 127.0.0.1, then reload this tab.'}</span></div>
            <div className={styles.missingActions}><button type="button" className={styles.primaryButton} onClick={() => void refreshWallets()}>Try again</button><button type="button" className={styles.smallButton} onClick={() => { setOpen(false); navigate('/settings#wallets') }}>Wallet settings</button></div>
          </div>}
          {message && <p className={message.includes('connected') ? styles.notice : styles.error} role="status">{message}</p>}
          {active.length > 0 && <><div className={styles.divider} /><div className={styles.connected}><h3>Connected accounts</h3>{active.map((wallet) => <div className={styles.account} key={wallet.id}>
            <div><strong>{wallet.label}</strong><span>{shortAddress(wallet.address)} · public address only</span></div>
            <div className={styles.accountActions}>
              <button type="button" className={styles.smallButton} onClick={() => inspect(wallet.address)}>View</button>
              <button type="button" className={styles.smallButton} disabled={disconnect.isPending} onClick={() => void disconnect.mutateAsync({ id: wallet.id, operator: readOperator().trim() || 'local operator', reason: 'Disconnected from wallet menu' })}>Disconnect</button>
            </div>
          </div>)}</div></>}
          <button type="button" className={styles.settingsLink} onClick={() => { setOpen(false); navigate('/settings#wallets') }}>More wallet options in Settings →</button>
        </div>
      </section>
    </div>}
  </div>
}
