import { useEffect, useId, useRef, useState } from 'react'
import { useHarnessChange } from '../../api/hooks/useHarnessControl'
import { rememberOperator, rememberedOperator } from '../ledger/paperRisk/paperRiskOperator'
import { CHANGE_COPY, OPERATOR_MAX, REASON_MAX, canSubmit, desiredFor, type Change } from './harnessControlText'
import styles from './HarnessChangeDialog.module.css'

interface Props {
  change: Change
  onClose: () => void
}

/**
 * Asks before the agent harness is stopped or started, with the operator's name and a reason; state-api records both.
 * Focus starts on Cancel, so a stray Enter changes nothing, and Escape closes it.
 */
export function HarnessChangeDialog({ change, onClose }: Props) {
  const mutation = useHarnessChange()
  const [operator, setOperator] = useState(rememberedOperator)
  const [reason, setReason] = useState('')
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const titleId = useId()
  const bodyId = useId()
  const copy = CHANGE_COPY[change]
  const ready = canSubmit(operator, reason) && !mutation.isPending

  useEffect(() => {
    cancelRef.current?.focus()
  }, [])

  const confirm = () => {
    const body = { desired_state: desiredFor(change), operator: operator.trim(), reason: reason.trim(), confirm: true as const }
    rememberOperator(body.operator)
    mutation.mutate(body, { onSuccess: onClose })
  }

  return (
    <div
      className={styles.backdrop}
      onKeyDown={(event) => {
        if (event.key !== 'Escape') return
        event.stopPropagation()
        onClose()
      }}
    >
      <div className={styles.dialog} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={bodyId}>
        <h4 id={titleId}>{copy.title}</h4>
        <div id={bodyId} className={styles.body}>
          <p>{copy.lead}</p>
          <ul>
            {copy.points.map((point) => <li key={point}>{point}</li>)}
          </ul>
          <p>{copy.after}</p>
        </div>
        <label className={styles.field}>
          Operator
          <input value={operator} maxLength={OPERATOR_MAX} autoComplete="name" onChange={(event) => setOperator(event.target.value)} />
        </label>
        <label className={styles.field}>
          Reason
          <input value={reason} maxLength={REASON_MAX} placeholder="Why (5 characters or more)" onChange={(event) => setReason(event.target.value)} />
        </label>
        {mutation.isError && <p role="alert" className={styles.error}>{mutation.error?.message}</p>}
        <div className={styles.actions}>
          <button ref={cancelRef} type="button" className="chip" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={`chip ${change === 'stop' ? styles.stop : styles.start}`} disabled={!ready} onClick={confirm}>
            {mutation.isPending ? 'Sending…' : copy.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
