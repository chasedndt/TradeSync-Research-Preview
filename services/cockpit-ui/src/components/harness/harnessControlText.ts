import type { HarnessControl, HarnessControlEvent, HarnessDesired, HarnessGatewayHealth, HarnessHost, HarnessState } from '../../api/harnessControlTypes'
import { ageText, utcStamp } from '../ledger/paperRisk/paperRiskFormat'

/** Pure wording for the agent harness kill switch, shared by the header and the Agents page; no React, so node tests import it. */

export { utcStamp }

export type Tone = 'good' | 'warn' | 'bad' | 'dim'
export type Change = 'stop' | 'start'

export const OPERATOR_MAX = 80
export const REASON_MIN = 5
export const REASON_MAX = 240

/** The bounds state-api enforces: a name, and a reason of 5 to 240 characters once trimmed. */
export function canSubmit(operator: string, reason: string): boolean {
  const who = operator.trim().length
  const why = reason.trim().length
  return who > 0 && who <= OPERATOR_MAX && why >= REASON_MIN && why <= REASON_MAX
}

export const desiredFor = (change: Change): HarnessState => (change === 'stop' ? 'stopped' : 'running')

export interface SwitchView {
  label: string
  tone: Tone
  action: Change | null
  warning: string | null
}

/** The header's reading: what the switch is doing, its colour, the one action it offers, and a warning when reality disagrees. */
export function switchView(control: HarnessControl | undefined, failed = false): SwitchView {
  if (!control) {
    return failed
      ? { label: 'unavailable', tone: 'bad', action: null, warning: 'The State API did not answer, so the agent harness switch cannot be read.' }
      : { label: 'checking', tone: 'dim', action: null, warning: null }
  }
  const stopping = control.desired.state === 'stopped'
  const status = control.host.status
  const moving = status === 'pending' || status === 'applying'
  const disagree = control.agreement.state === 'disagree'
  const label = moving
    ? stopping ? 'stopping…' : 'starting…'
    : status === 'failed'
      ? stopping ? 'stop failed' : 'start failed'
      : stopping ? 'stopped' : 'running'
  const tone: Tone = status === 'failed' || stopping
    ? moving ? 'warn' : 'bad'
    : moving || disagree ? 'warn' : control.agreement.state === 'agree' ? 'good' : 'dim'
  return { label, tone, action: stopping ? 'start' : 'stop', warning: disagree ? control.agreement.message : null }
}

export const CHANGE_COPY: Record<Change, { title: string; lead: string; points: string[]; after: string; confirmLabel: string }> = {
  stop: {
    title: 'Stop the agent harness?',
    lead: 'This stops the Hermes gateway on this PC, the same as running hermes gateway stop. Until you start it again:',
    points: [
      'every Hermes cron job stops, including the StrikeZone and Community Server automations;',
      'the Hermes Discord bots go offline;',
      "TradeSync's Hermes readings, scheduled readings, thesis briefings, fleet job changes through the gateway and core-scorer's claim reading are refused.",
    ],
    after:
      'Paper trading and market data continue. Nothing is switched off for good: Start brings the gateway back and every job keeps its schedule. ' +
      'The ChaseOS coordination daemon is separate and keeps running.',
    confirmLabel: 'Stop agent harness',
  },
  start: {
    title: 'Start the agent harness?',
    lead: "This starts the Hermes gateway's service on this PC, as the Windows logon script does. Once it is running:",
    points: [
      'Hermes cron jobs run on their schedules again, including StrikeZone and Community Server;',
      'the Hermes Discord bots reconnect;',
      'TradeSync calls Hermes again for readings, briefings, fleet job changes and claim reading.',
    ],
    after: 'TradeSync allows its own Hermes calls as soon as you confirm; the gateway answers once the host control process has started it.',
    confirmLabel: 'Start agent harness',
  },
}

export const SCOPE_NOTE =
  'The host control process (Task Scheduler task TradeSync-Hermes-Harness-Control) applies each request once and reports what systemd says. ' +
  'The ChaseOS coordination daemon (hermes-daemon-loop) is separate: ChaseOS Studio or Task Scheduler controls it, and this switch never touches it. ' +
  'A Windows logon (Hermes Gateway.vbs) or a WSL restart starts the gateway again; this page warns when it answers while stopped.'

/** The command the host ran, in the operator's own words. */
export function commandName(command: string | null | undefined): string {
  if (!command) return '—'
  if (command.includes('gateway stop')) return 'hermes gateway stop'
  if (command.includes('systemctl --user start')) return 'systemctl --user start hermes-gateway'
  return command
}

export function requestLine(desired: HarnessDesired): string {
  return `${desired.state === 'stopped' ? 'Stopped' : 'Running'} · by ${desired.operator} at ${utcStamp(desired.requested_at)}`
}

export function hostLine(host: HarnessHost): string {
  if (host.status === 'none') return 'No stop or start has been requested from TradeSync.'
  if (host.status === 'pending') {
    return host.seconds_since_poll == null
      ? 'Waiting for the host control process; it has not checked in since the State API started.'
      : `Waiting for the host control process (last checked in ${ageText(host.seconds_since_poll)} ago).`
  }
  if (host.status === 'applying') return `Applying since ${utcStamp(host.claimed_at)}.`
  const result = host.result
  return `${host.status === 'applied' ? 'Applied' : 'Failed'} ${utcStamp(result?.at)} · ${commandName(result?.command)} · exit ${result?.exit_status ?? '—'} · systemd ${result?.is_active ?? 'unknown'}`
}

export function gatewayLine(gateway: HarnessGatewayHealth): string {
  if (gateway.status === 'not_configured') return 'Not configured in TradeSync (AGENT_HARNESS_URL is unset).'
  if (gateway.status === 'checking') return 'Checking: no heartbeat yet.'
  if (gateway.status === 'live' || gateway.status === 'degraded') {
    const failing = gateway.status === 'degraded' ? ' · the key or a platform is failing' : ''
    return `Answering · last answer ${ageText(gateway.seconds_since_seen)} ago${failing}`
  }
  return gateway.last_seen_at ? `Not answering since ${utcStamp(gateway.last_seen_at)}` : 'Not answering since the State API started'
}

export function agreementTone(state: HarnessControl['agreement']['state']): Tone {
  return state === 'agree' ? 'good' : state === 'pending' ? 'warn' : state === 'disagree' ? 'bad' : 'dim'
}

/** One audit row as the history table shows it. */
export function eventLine(event: HarnessControlEvent): { title: string; detail: string } {
  const verb = event.desired_state === 'stopped' ? 'Stop' : 'Start'
  if (event.kind === 'requested') return { title: `${verb} requested by ${event.operator ?? 'an unnamed operator'}`, detail: event.reason ?? '' }
  if (event.kind === 'applying') return { title: `${verb} taken up by the host control process`, detail: '' }
  const outcome = `${commandName(event.command)} · exit ${event.exit_status ?? '—'} · systemd ${event.is_active ?? 'unknown'}`
  const title = event.kind === 'applied' ? `${event.desired_state === 'stopped' ? 'Stopped' : 'Started'} by the host control process` : `${verb} failed`
  return { title, detail: event.detail ? `${outcome} · ${event.detail}` : outcome }
}
