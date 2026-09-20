export type WalletConnector = 'phantom' | 'browser_wallet' | 'walletconnect' | 'watch_only'

export interface RegisteredWallet {
  id: string
  address: string
  label: string
  connector: WalletConnector
  status: 'active' | 'disconnected'
  added_by: string
  added_at: string
  last_seen_at: string
}

export interface WalletRegistry {
  wallets: RegisteredWallet[]
  authority: 'address_only'
  execution_authority: false
  note: string
}

export interface WalletChange {
  address: string
  label: string
  connector: WalletConnector
  operator: string
  reason: string
}

export interface WalletChangeResult {
  wallet: RegisteredWallet
  action: 'added' | 'reconnected' | 'renamed' | 'disconnected'
  authority: 'address_only'
  execution_authority: false
}
