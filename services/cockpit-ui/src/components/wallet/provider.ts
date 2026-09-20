import type { WalletConnector } from '../../api/walletRegistryTypes'

export interface Eip1193Provider {
  isPhantom?: boolean
  providers?: Eip1193Provider[]
  request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>
  on?(event: string, handler: (...args: unknown[]) => void): void
  removeListener?(event: string, handler: (...args: unknown[]) => void): void
}

type AnnounceProvider = CustomEvent<{
  info?: { name?: string; rdns?: string }
  provider?: Eip1193Provider
}>

type WalletWindow = Window & {
  ethereum?: Eip1193Provider
  phantom?: {
    ethereum?: Eip1193Provider
    solana?: { isPhantom?: boolean }
  }
}

export interface DetectedWallet {
  provider: Eip1193Provider
  connector: WalletConnector
  name: string
}

export interface PhantomDetection {
  wallet: DetectedWallet | null
  extensionDetected: boolean
}

function isPhantom(provider: Eip1193Provider, name = '', rdns = '') {
  return Boolean(provider.isPhantom || /phantom/i.test(`${name} ${rdns}`))
}

/**
 * Prefer Phantom's documented EVM provider, then EIP-6963 discovery, then the
 * legacy injected provider. The provider owns consent and account selection;
 * TradeSync never receives a recovery phrase or private key.
 */
export async function detectEvmWallets(timeoutMs = 1200): Promise<DetectedWallet[]> {
  const browser = window as WalletWindow
  const found = new Map<Eip1193Provider, DetectedWallet>()
  const add = (provider: Eip1193Provider | undefined, name = 'Browser wallet', rdns = '') => {
    if (!provider || found.has(provider)) return
    const phantom = isPhantom(provider, name, rdns)
    found.set(provider, { provider, connector: phantom ? 'phantom' : 'browser_wallet', name: phantom ? 'Phantom' : name })
  }

  const collectInjected = () => {
    add(browser.phantom?.ethereum, 'Phantom', 'app.phantom')
    for (const provider of browser.ethereum?.providers ?? []) add(provider, provider.isPhantom ? 'Phantom' : 'Browser wallet')
    add(browser.ethereum, browser.ethereum?.isPhantom ? 'Phantom' : 'Browser wallet')
  }

  collectInjected()
  const announce = (event: Event) => {
    const detail = (event as AnnounceProvider).detail
    if (detail?.provider) add(detail.provider, detail.info?.name || 'Browser wallet', detail.info?.rdns || '')
  }
  window.addEventListener('eip6963:announceProvider', announce)
  window.dispatchEvent(new Event('eip6963:requestProvider'))
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline && ![...found.values()].some((wallet) => wallet.connector === 'phantom')) {
    await new Promise((resolve) => window.setTimeout(resolve, 75))
    collectInjected()
  }
  window.removeEventListener('eip6963:announceProvider', announce)
  collectInjected()
  return [...found.values()].sort((a, b) => Number(b.connector === 'phantom') - Number(a.connector === 'phantom'))
}

/** Find Phantom specifically and distinguish provider injection from extension presence. */
export async function detectPhantom(timeoutMs = 1200): Promise<PhantomDetection> {
  const browser = window as WalletWindow
  const wallets = await detectEvmWallets(timeoutMs)
  return {
    wallet: wallets.find((candidate) => candidate.connector === 'phantom') ?? null,
    extensionDetected: Boolean(browser.phantom?.ethereum || browser.phantom?.solana?.isPhantom),
  }
}

export async function requestPublicAddress(wallet: DetectedWallet): Promise<string> {
  const result = await wallet.provider.request({ method: 'eth_requestAccounts', params: [] })
  const address = Array.isArray(result) && typeof result[0] === 'string' ? result[0] : ''
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) throw new Error('The wallet did not return a valid public EVM address.')
  return address
}

export const shortAddress = (address: string) => `${address.slice(0, 6)}…${address.slice(-4)}`
