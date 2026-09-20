import type { MobileDevice, MobileEvent } from '../../api/mobileAlertTypes'
import { PhoneStepDetail } from './PhoneStepDetail'
import { STATE_WORDS, checklist, stepsRemaining } from './phoneChecklist'
import styles from './PhoneSetupChecklist.module.css'

interface Props {
  configured: boolean | undefined
  keyEntered: boolean
  authorized: boolean
  refused: boolean
  devices: MobileDevice[]
  events: MobileEvent[]
  onKeyChange: () => void
}

/** Phone notification setup as seven steps, each marked from live state where TradeSync can see it. */
export function PhoneSetupChecklist({ onKeyChange, ...input }: Props) {
  const steps = checklist(input)
  const remaining = stepsRemaining(steps)
  return (
    <details className={styles.checklist} open={remaining > 0}>
      <summary>
        Set up phone notifications · {remaining === 0 ? 'every step done' : `${steps.length - remaining} of ${steps.length} steps done`}
      </summary>
      <p className={styles.lead}>
        Marks come from live state. TradeSync cannot see your phone, so installing ntfy and subscribing are proved by the test you
        confirm in the last step.
      </p>
      <ol className={styles.steps}>
        {steps.map((step) => (
          <li key={step.id} className={styles.step}>
            <div className={styles.head}>
              <strong className={styles.title}>{step.title}</strong>
              <span className={styles.marks}>
                {step.marks.map((mark) => (
                  <span key={mark.label} className={`${styles.mark} ${styles[mark.state]}`}>{mark.label}: {STATE_WORDS[mark.state]}</span>
                ))}
              </span>
            </div>
            <PhoneStepDetail
              id={step.id}
              configured={input.configured}
              keyProblem={step.marks.some((mark) => mark.state === 'problem')}
              onKeyChange={onKeyChange}
            />
          </li>
        ))}
      </ol>
    </details>
  )
}
