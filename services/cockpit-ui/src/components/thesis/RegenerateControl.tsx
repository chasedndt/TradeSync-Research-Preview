import { useState } from 'react'
import { useEditions, useGenerateEdition } from '../../api/hooks/useEditions'
import { ArrowClockwise } from '../icons'
import styles from './Thesis.module.css'

/**
 * Regenerate the thesis now: a black-swan move, a mid-session reset. The
 * optional focus is stored with the edition and passed to Hermes with the
 * measured facts. It is not a hidden web-search box. Building takes a few
 * minutes and runs in the background; this shows the stage while it does.
 */
export function RegenerateControl({ withReason = true }: { withReason?: boolean }) {
  const { data } = useEditions(1)
  const generate = useGenerateEdition()
  const [reason, setReason] = useState('')
  const job = data?.generation
  const running = Boolean(job?.running) || generate.isPending
  const elapsed = job?.running && job.started_at ? Math.max(0, Math.round((Date.now() - new Date(job.started_at).getTime()) / 1000)) : null

  return (
    <div className={styles.regen}>
      {withReason && !running && (
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="focus question (optional), e.g. rate decision"
          maxLength={200}
          aria-label="Optional focus question for the regenerated thesis"
        />
      )}
      <button
        type="button"
        className={`chip chip--active ${styles.regenButton}`}
        disabled={running}
        onClick={() => { generate.mutate(reason); setReason('') }}
      >
        <ArrowClockwise size={13} weight="bold" />
        {running ? 'Regenerating…' : 'Regenerate thesis'}
      </button>
      {running && job?.stage && <span className="metric-sub">{job.stage}{elapsed != null ? ` · ${elapsed}s` : ''}</span>}
      {!running && job?.last_error && <span className="metric-sub tone-bad">last attempt failed: {job.last_error}</span>}
      {generate.isError && <span className="metric-sub tone-bad">could not start: {String(generate.error)}</span>}
      {withReason && !running && <span className={styles.regenHelp}>Uses measured TradeSync evidence; Hermes addresses the focus only when its gateway is live. No unsupported web claims.</span>}
    </div>
  )
}
