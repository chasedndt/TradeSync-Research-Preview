import { useState } from 'react'
import { getApiBaseUrl, setApiBaseUrl } from '../../api/credentials'
import styles from './SettingsPanels.module.css'

/**
 * The one connection setting kept in this browser: which state API address the
 * Cockpit reads from. It stays because pointing a build at a loopback state API
 * is a real need, and it can never send a credential elsewhere: only a path on
 * this site or a loopback address is used, anything else falls back to /api.
 */
export function StateApiAddress() {
  const [value, setValue] = useState(getApiBaseUrl)
  const [used, setUsed] = useState<string | null>(null)

  const apply = () => {
    const address = setApiBaseUrl(value)
    setValue(address)
    setUsed(address)
  }

  return (
    <details className={styles.details}>
      <summary>Read from a different state API address in this browser</summary>
      <p className={styles.note}>
        Kept in this browser only. A path on this site or a loopback address such as http://127.0.0.1:8000 is used;
        anything else falls back to /api, so credentials never go to another host.
      </p>
      <div className={styles.inline}>
        <input
          className={`input ${styles.address}`}
          aria-label="State API address"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="/api"
        />
        <button type="button" className="chip" onClick={apply}>Use this address</button>
      </div>
      {used && <p className={styles.note} role="status">New readings now go to {used}.</p>}
    </details>
  )
}
