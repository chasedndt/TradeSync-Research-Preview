import { useState } from 'react'
import { Link } from 'react-router-dom'
import { QrCode } from 'lucide-react'
import { useSaveWalletConnectSettings, useWalletConnectSettings } from '../../api/hooks/useWalletConnectSettings'
import { readOperator, saveOperator } from '../learning/format'
import { REOWN_DASHBOARD, changeLine, checkProjectId, savedLine } from './walletConnectText'
import styles from './WalletConnectSettings.module.css'

/** The public WalletConnect project ID: where to get it, why it is not a secret, and who saved it when. */
export function WalletConnectSettings() {
  const settings = useWalletConnectSettings()
  const save = useSaveWalletConnectSettings()
  const [input, setInput] = useState('')
  const [operator, setOperator] = useState<string>(readOperator)
  const [warning, setWarning] = useState<string | null>(null)
  const check = checkProjectId(input)
  const saved = settings.data
  const named = operator.trim().length > 0

  const submit = (projectId: string) =>
    save.mutate({ project_id: projectId, changed_by: operator.trim() }, { onSuccess: () => setInput('') })

  return (
    <section className="card" aria-label="WalletConnect project ID">
      <h3 className="text-sm font-medium text-gray-400 mb-4 flex items-center gap-2">
        <QrCode size={14} />
        WalletConnect project ID
      </h3>
      <p className={styles.text}>
        Needed only to pair a wallet by QR code in <Link to="/settings#wallets">Wallet Settings</Link>. Watching a wallet by its
        public address works without it.
      </p>
      <p className={styles.text}>
        <strong>Public, not a secret.</strong> It tells the WalletConnect relay which app is asking, and the relay receives it
        with every pairing. It cannot sign, move funds or read a wallet, so TradeSync saves it and shows it.
      </p>
      <ol className={styles.steps}>
        <li>
          Open <a href={REOWN_DASHBOARD} target="_blank" rel="noopener noreferrer">dashboard.reown.com</a> (Reown Cloud;
          cloud.reown.com now redirects there) and sign up or sign in. The free Starter plan is enough.
        </li>
        <li>Create a project and copy its Project ID: 32 characters, digits and the letters a to f.</li>
        <li>Paste it below, add your name and choose Save. Your name and the time are kept with the change.</li>
      </ol>

      <p className={styles.current} role="status">
        {settings.isLoading && 'Reading the saved project ID…'}
        {settings.isError && `Saved project ID unavailable: ${settings.error?.message ?? 'no answer'}`}
        {saved && (saved.project_id
          ? <>Saved: <code className={styles.id}>{saved.project_id}</code> · {savedLine(saved.project_id, saved.updated_by, saved.updated_at)}</>
          : savedLine(null, null, null))}
      </p>

      <form className={styles.form} onSubmit={(event) => { event.preventDefault(); if (check.ok && named) submit(check.value) }}>
        <label className={styles.field}>
          Project ID
          <input
            className="input"
            value={input}
            autoComplete="off"
            spellCheck={false}
            maxLength={80}
            placeholder="32 characters, digits and a to f"
            onChange={(event) => {
              const typed = checkProjectId(event.target.value)
              if (!typed.ok && typed.kind === 'looks_secret') {
                setInput('')
                setWarning(typed.message)
                return
              }
              setWarning(null)
              setInput(event.target.value)
            }}
          />
        </label>
        <label className={styles.field}>
          Your name
          <input
            className="input"
            value={operator}
            maxLength={80}
            autoComplete="name"
            placeholder="Kept with the change"
            onChange={(event) => { setOperator(event.target.value); saveOperator(event.target.value) }}
          />
        </label>
        <div className={styles.actions}>
          <button type="submit" className="btn btn-primary" disabled={!check.ok || !named || save.isPending}>Save project ID</button>
          {saved?.project_id && (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!named || save.isPending}
              onClick={() => { if (window.confirm('Clear the saved WalletConnect project ID? Pairing by QR will ask for one again.')) submit('') }}
            >
              Clear saved ID
            </button>
          )}
        </div>
      </form>

      {warning && <p role="alert" className={`${styles.message} tone-warn`}>{warning}</p>}
      {input.trim() !== '' && !check.ok && check.kind === 'shape' && <p className={`${styles.message} tone-warn`}>{check.message}</p>}
      {!named && (input.trim() !== '' || Boolean(saved?.project_id)) && <p className={styles.message}>Add your name to save a change.</p>}
      {save.isError && <p role="alert" className={`${styles.message} tone-bad`}>{save.error?.message}</p>}
      {save.isSuccess && (
        <p role="status" className={`${styles.message} tone-good`}>
          {!save.data?.changed
            ? 'Nothing changed: that project ID was already saved.'
            : save.data.project_id ? 'Saved. Phone pairing in Wallet Settings now starts with this project ID.' : 'Cleared.'}
        </p>
      )}

      {saved && saved.changes.length > 0 && (
        <details className={styles.history}>
          <summary>Changes ({saved.changes.length})</summary>
          <ul>
            {saved.changes.map((change) => <li key={`${change.changed_at}-${change.next ?? 'cleared'}`}>{changeLine(change)}</li>)}
          </ul>
        </details>
      )}
    </section>
  )
}
