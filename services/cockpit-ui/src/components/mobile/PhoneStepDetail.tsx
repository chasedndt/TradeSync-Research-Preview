import { CommandBlock } from '../onboarding/CommandBlock'
import { CLEAR_CLIPBOARD, RECREATE_STATE_API, copySecret, storeNewSecret } from '../onboarding/hostCommands'
import { MobileKeyEntry } from './MobileKeyEntry'
import { NTFY_APPS, type StepId } from './phoneChecklist'
import styles from './PhoneStepDetail.module.css'

const KEY_NAME = 'MOBILE_ALERTS_CONTROL_KEY'

interface Props {
  id: StepId
  configured: boolean | undefined
  keyProblem: boolean
  onKeyChange: () => void
}

/** What the operator does for one step of the phone checklist. */
export function PhoneStepDetail({ id, configured, keyProblem, onKeyChange }: Props) {
  switch (id) {
    case 'app':
      return (
        <div className={styles.detail}>
          <p>ntfy is free and open source, and it is the only thing to install: no TradeSync app and no wallet app.</p>
          <ul className={styles.links}>
            {NTFY_APPS.map((app) => <li key={app.url}><a href={app.url} target="_blank" rel="noopener noreferrer">{app.label}</a></li>)}
          </ul>
        </div>
      )
    case 'server_key':
      return configured ? (
        <p className={styles.detail}>MOBILE_ALERTS_CONTROL_KEY is configured on this PC. Its value is never shown here.</p>
      ) : (
        <div className={styles.detail}>
          <p>
            This key lets the dashboard manage phone notifications. It is not a wallet key and grants no trading. In Windows PowerShell on
            this PC, this makes a random key, opens a desktop prompt to store it in runtime.env (paste it there) and clears the clipboard.
            Then recreate state-api so it reads the key, and reload this page.
          </p>
          <CommandBlock label="Store a new mobile control key" text={storeNewSecret(KEY_NAME)} />
          <CommandBlock label="Recreate state-api" text={RECREATE_STATE_API} />
        </div>
      )
    case 'session_key':
      return (
        <div className={styles.detail}>
          <p>
            Copy the key on this PC without showing it, paste it here and choose Keep, then clear the clipboard. It is kept for this
            browser session only and sent only to this dashboard&apos;s state-api.
          </p>
          <CommandBlock label="Copy the mobile control key" text={copySecret(KEY_NAME)} />
          <MobileKeyEntry onChange={onKeyChange} />
          <CommandBlock label="Clear the clipboard" text={CLEAR_CLIPBOARD} wrap />
          {keyProblem && <p className="tone-bad">The key kept in this browser does not match the one on this PC. Copy it again and choose Keep.</p>}
        </div>
      )
    case 'enroll':
      return (
        <p className={styles.detail}>
          Below, choose the phone&apos;s platform, give it a label, accept generic public-topic delivery and choose Create subscription
          details. It sends nothing. Do it once for the Android phone and once for the iPhone.
        </p>
      )
    case 'subscribe':
      return (
        <p className={styles.detail}>
          In the ntfy app, add a subscription with server https://ntfy.sh and the topic shown after step 4 (Show subscription details
          shows it again). Allow notifications for ntfy when the phone asks. Keep the topic private: anyone who has it can read the messages.
        </p>
      )
    case 'test':
      return (
        <p className={styles.detail}>
          Choose Send generic test for that phone. The delivery ledger then shows provider accepted: ntfy took the message, which does not
          yet prove the phone showed it.
        </p>
      )
    case 'confirm':
      return (
        <p className={styles.detail}>
          When the notification with the same reference appears on the phone, choose I received this on my phone in the ledger. Only then
          can that phone be opted in to paper lifecycle and kill-switch notifications.
        </p>
      )
  }
}
