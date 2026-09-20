import { useState } from 'react'
import styles from './CommandBlock.module.css'

/** Text the operator copies: a command for this PC, the webhook address or the alert message. Never a secret. */
export function CommandBlock({ label, text, wrap = false }: { label: string; text: string; wrap?: boolean }) {
  const [copied, setCopied] = useState<'idle' | 'copied' | 'failed'>('idle')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied('copied')
    } catch {
      setCopied('failed')
    }
  }

  return (
    <div className={styles.block}>
      <div className={styles.head}>
        <span className={styles.label}>{label}</span>
        <button type="button" className="chip" onClick={() => void copy()} aria-label={`Copy: ${label}`}>
          {copied === 'copied' ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className={wrap ? `${styles.text} ${styles.wrap}` : styles.text}>{text}</pre>
      {copied === 'failed' && <span className={styles.failed}>The browser refused the clipboard. Select the text and copy it.</span>}
    </div>
  )
}
