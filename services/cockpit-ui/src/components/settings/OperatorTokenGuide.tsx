import { CommandBlock } from '../onboarding/CommandBlock'
import { CLEAR_CLIPBOARD, RECREATE_TOKEN_READERS, copySecret, removeSecretLine, storeNewSecret } from '../onboarding/hostCommands'
import { tokenAdvice, type TokenState } from './operatorTokenText'
import styles from './OperatorTokenGuide.module.css'

const NAME = 'STATE_API_OPERATOR_TOKEN'

/** The operator token in plain words: what it is, whether this PC needs it now, and how to turn it on and off. */
export function OperatorTokenGuide({ state }: { state: TokenState | undefined }) {
  const advice = tokenAdvice(state)
  return (
    <div className={styles.guide}>
      <p className={styles.text}>
        <strong>What it is.</strong> An optional password that state-api asks for on every change made through its API: saving a
        setting, pausing paper entries, adopting a proposal. Reading is never blocked. It is not a wallet key and unlocks no trading.
      </p>
      <p className={`${styles.text} ${advice.tone}`}>
        <strong>Now: {advice.headline}</strong> {advice.detail}
      </p>
      <details className={styles.steps}>
        <summary>Turn it on</summary>
        <ol>
          <li>
            In Windows PowerShell on this PC, make a 48-character token, store it through the desktop prompt (paste it there), and clear
            the clipboard.
            <CommandBlock label="Store a new operator token" text={storeNewSecret(NAME)} />
          </li>
          <li>
            Recreate the three containers that read it. No rebuild is needed.
            <CommandBlock label="Recreate state-api, core-scorer and discord-reader" text={RECREATE_TOKEN_READERS} />
          </li>
          <li>Host tools need nothing: on their next run they read the same line from runtime.env.</li>
          <li>
            In this browser, once per session: copy the token, paste it into Operator token below and choose Keep, then clear the clipboard.
            <CommandBlock label="Copy the operator token" text={copySecret(NAME)} />
            <CommandBlock label="Clear the clipboard" text={CLEAR_CLIPBOARD} wrap />
          </li>
          <li>Check: this panel says On, a change made here succeeds, and the Fleet page&apos;s snapshot time keeps advancing.</li>
        </ol>
      </details>
      <details className={styles.steps}>
        <summary>Turn it off</summary>
        <ol>
          <li>
            Remove the STATE_API_OPERATOR_TOKEN line from runtime.env. This removes only that line and shows nothing.
            <CommandBlock label="Remove the operator token line" text={removeSecretLine(NAME)} />
          </li>
          <li>
            Recreate the same three containers.
            <CommandBlock label="Recreate state-api, core-scorer and discord-reader" text={RECREATE_TOKEN_READERS} />
          </li>
          <li>Forget the token in this browser with the bin button beside Keep.</li>
        </ol>
      </details>
    </div>
  )
}
