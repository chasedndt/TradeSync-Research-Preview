import { useState } from 'react'
import { clearMobileControlKey, getMobileControlKey, setMobileControlKey } from '../../api/credentials'
import styles from './MobileKeyEntry.module.css'

/** The mobile control key for this browser session: pasted, never displayed, not kept on disk. */
export function MobileKeyEntry({ onChange }: { onChange: () => void }) {
  const [input, setInput] = useState('')
  const [kept, setKept] = useState(() => getMobileControlKey() !== null)

  const keep = () => {
    if (!input.trim()) return
    setMobileControlKey(input)
    setInput('')
    setKept(true)
    onChange()
  }

  const forget = () => {
    clearMobileControlKey()
    setKept(false)
    onChange()
  }

  return (
    <form className={styles.entry} onSubmit={(event) => { event.preventDefault(); keep() }}>
      <label className={styles.field}>
        Mobile control key
        <input
          className="input"
          type="password"
          autoComplete="off"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={kept ? 'Kept for this browser session' : 'Paste the mobile control key'}
        />
      </label>
      <button type="submit" className="btn btn-primary" disabled={!input.trim()}>Keep</button>
      {kept && <button type="button" className="btn btn-secondary" onClick={forget}>Forget</button>}
    </form>
  )
}
