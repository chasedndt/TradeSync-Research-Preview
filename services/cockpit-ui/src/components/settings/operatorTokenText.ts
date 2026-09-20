export type TokenState = 'disabled' | 'required' | 'misconfigured'

export interface TokenAdvice {
  headline: string
  detail: string
  tone: 'tone-good' | 'tone-bad' | 'tone-dim'
}

/** Whether the operator token is on, and whether this PC needs it, in plain words. */
export function tokenAdvice(state: TokenState | undefined): TokenAdvice {
  switch (state) {
    case 'disabled':
      return {
        headline: 'Off.',
        detail: 'You do not need it while the dashboard and state-api can be reached only from this PC, as now: every port listens on '
          + '127.0.0.1 and changes sent from other web pages are refused. Turn it on before any remote access, such as a tunnel, port '
          + 'forwarding or opening the dashboard from your phone.',
        tone: 'tone-dim',
      }
    case 'required':
      return {
        headline: 'On.',
        detail: 'Every change made through the dashboard needs the token kept below; reading does not. Host tools on this PC read it from runtime.env.',
        tone: 'tone-good',
      }
    case 'misconfigured':
      return {
        headline: 'Set, but too short.',
        detail: 'STATE_API_OPERATOR_TOKEN is shorter than 32 characters, so state-api refuses every change. Store a new token with the '
          + 'steps under Turn it on, or turn it off.',
        tone: 'tone-bad',
      }
    default:
      return { headline: 'Not known yet.', detail: 'The access policy has not been read.', tone: 'tone-dim' }
  }
}
