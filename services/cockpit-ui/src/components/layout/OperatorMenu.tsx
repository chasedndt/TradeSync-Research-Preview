import { useEffect, useRef, useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { readOperator } from '../learning/format'
import { OperatorMenuPanel } from './OperatorMenuPanel'
import styles from './OperatorMenu.module.css'

/**
 * The operator menu, in the place an account menu usually sits and saying at once
 * that it is not one: TradeSync has no sign-in. It names who changes are
 * attributed to, the runtime, what state-api enforces, the mode, what is held for
 * review, enrolled phones and this browser's credentials, the audit records, and
 * the one lock that exists: forgetting the credentials this browser holds.
 */
export function OperatorMenu() {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const name = readOperator().trim()

  useEffect(() => {
    if (!open) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onPointer = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [open])

  return (
    <div className={styles.menu} ref={root}>
      <button
        type="button"
        className={styles.trigger}
        aria-expanded={open}
        aria-controls="operator-menu-panel"
        aria-label={`Local workstation controls. ${name ? `Changes are attributed to ${name}.` : 'No operator label is set.'}`}
        onClick={() => setOpen((value) => !value)}
      >
        <SlidersHorizontal size={17} aria-hidden="true" />
        <span className={styles.triggerText}>
          <strong>Controls</strong>
        </span>
      </button>
      {open && <OperatorMenuPanel name={name} onClose={() => setOpen(false)} />}
    </div>
  )
}
