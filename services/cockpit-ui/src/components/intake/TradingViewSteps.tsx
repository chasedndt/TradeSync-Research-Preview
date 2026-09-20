import type { TradingViewSetup } from '../../api/tradingViewSetupTypes'
import { CommandBlock } from '../onboarding/CommandBlock'
import { CLEAR_CLIPBOARD, RECREATE_STATE_API, copySecret, refusedAlertsLog, storeNewSecret } from '../onboarding/hostCommands'
import { manualPlaceholders, templateText } from './tradingViewText'
import styles from './TradingViewSteps.module.css'

const SECRET_NAME = 'TRADINGVIEW_WEBHOOK_SECRET'

/**
 * The operator's steps, in an order that works with one clipboard: the address and the message are copied from this
 * page first, the secret last, and the clipboard is cleared at the end. The secret itself never appears.
 */
export function TradingViewSteps({ setup }: { setup: TradingViewSetup }) {
  const byHand = manualPlaceholders(setup.message_template, setup.secret_placeholder)
  return (
    <ol className={styles.steps}>
      {!setup.secret_configured && (
        <li>
          <strong>Set the webhook secret on this PC.</strong> In Windows PowerShell this makes a random value, opens a desktop prompt
          to store it in runtime.env (paste it there), and clears the clipboard. Then recreate state-api so it reads the secret.
          <CommandBlock label="Store a new webhook secret" text={storeNewSecret(SECRET_NAME)} />
          <CommandBlock label="Recreate state-api" text={RECREATE_STATE_API} />
        </li>
      )}
      <li>
        <strong>In TradingView, create a second alert</strong> on the indicator and condition you want. TradingView allows one webhook
        address per alert, so keep your Discord alerts as they are and add this one beside them. Webhook alerts need two-factor
        authentication on your TradingView account.
      </li>
      <li>
        <strong>Tick Webhook URL</strong> in the alert&apos;s notifications and paste this address.
        <CommandBlock label="Webhook URL" text={setup.webhook_url} wrap />
      </li>
      <li>
        <strong>Paste this message</strong> into the alert&apos;s Message box, replacing what is there. Replace{' '}
        {byHand.map((value, index) => (
          <span key={value}>
            {index === 0 ? '' : index === byHand.length - 1 ? ' and ' : ', '}
            <code>{value}</code>
          </span>
        ))}{' '}
        with your own words, and leave the <code>{'{{…}}'}</code> placeholders: TradingView fills them when the alert fires.
        Required fields: {setup.required_fields.join(', ')}.
        <CommandBlock label="Alert message" text={templateText(setup.message_template)} />
        <span className={styles.aside}>If the alert does not let you edit its message, it cannot carry the secret, and TradeSync refuses it.</span>
      </li>
      <li>
        <strong>Copy the secret on this PC</strong>, then in the Message box select <code>{setup.secret_placeholder}</code> and paste
        over it (Ctrl+V). The command copies the secret without showing it.
        <CommandBlock label="Copy the webhook secret" text={copySecret(SECRET_NAME)} />
      </li>
      <li>
        <strong>Save the alert, then clear the clipboard.</strong>
        <CommandBlock label="Clear the clipboard" text={CLEAR_CLIPBOARD} wrap />
      </li>
      <li>
        <strong>Check that it arrives.</strong> When the alert next fires it appears under Latest TradingView alerts within 30 seconds.
        If it does not, this lists the alerts state-api refused in the last hour, with their reason codes (such as bad_secret,
        missing_fields or body_not_json).
        <CommandBlock label="Refused alerts in the state-api log" text={refusedAlertsLog(setup.refusal_log_marker)} />
      </li>
    </ol>
  )
}
