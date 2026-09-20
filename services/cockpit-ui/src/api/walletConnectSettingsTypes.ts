/** GET and PUT /state/settings/walletconnect: the public WalletConnect project ID and who changed it. */

export interface WalletConnectChange {
  changed_by: string
  changed_at: string
  previous: string | null
  next: string | null
}

export interface WalletConnectSettings {
  schema_version: string
  /** Null until an operator saves one. Public by nature: never a secret. */
  project_id: string | null
  updated_by: string | null
  updated_at: string | null
  /** Newest first. */
  changes: WalletConnectChange[]
  project_site: string
  public: boolean
  note: string
}

export interface WalletConnectSaveResult extends WalletConnectSettings {
  /** False when the value was already saved: nothing was written. */
  changed: boolean
  previous: string | null
  changed_by: string
  changed_at: string | null
}
