/**
 * Commands the operator runs on this PC in Windows PowerShell, from the main checkout.
 *
 * They set, copy or remove a secret without displaying it: tools\set-runtime-secret.ps1 writes runtime.env from a
 * desktop prompt, and tools\copy-runtime-secret.ps1 copies one value to the clipboard. No command here prints a
 * secret or carries one on its command line, and the dashboard never receives one: it shows only whether each is
 * configured.
 */

export const MAIN_CHECKOUT = 'E:\\Projects\\TradeSync\\dashboard-overhaul-2026-09-01'
export const RUNTIME_ENV = 'E:\\Projects\\TradeSync\\dashboard-runtime\\runtime.env'
export const CLEAR_CLIPBOARD = "Set-Clipboard -Value ' '"

const VARIABLE = /^[A-Z][A-Z0-9_]*$/

function variable(name: string): string {
  if (!VARIABLE.test(name)) throw new Error(`Not an environment variable name: ${name}`)
  return name
}

const inCheckout = (...lines: string[]): string => [`Set-Location ${MAIN_CHECKOUT}`, ...lines].join('\n')

/**
 * Put a new random value on the clipboard (48 URL-safe characters), store it under the name through the desktop
 * prompt, then clear the clipboard. The steps from docs/changes/2026-09-15_local-access-hardening.md.
 */
export function storeNewSecret(name: string): string {
  return inCheckout(
    '$bytes = New-Object byte[] 36',
    '[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)',
    "Set-Clipboard -Value ([Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_'))",
    `powershell -ExecutionPolicy Bypass -File tools\\set-runtime-secret.ps1 -Name ${variable(name)}`,
    CLEAR_CLIPBOARD,
  )
}

/**
 * Generate the Web Push (VAPID) key pair on this PC and store both halves, without showing the private one.
 *
 * Node is already installed here (the Cockpit is built with it) and its own crypto module makes a P-256 key
 * pair offline: nothing is downloaded, no account is created, and no key is ever written into the repository.
 * The private half goes to the clipboard and into runtime.env through the same desktop prompt as every other
 * secret, and the clipboard is cleared afterwards. The public half is printed at the end because it is public
 * by design — a browser sends it to its push service with every subscription.
 *
 * docs/runbooks/MOBILE_ALERTS.md quotes this command; keep the two in step.
 */
export const GENERATE_VAPID_KEYS = inCheckout(
  `$pair = node -e "const {generateKeyPairSync}=require('crypto');const {privateKey}=generateKeyPairSync('ec',{namedCurve:'prime256v1'});const k=privateKey.export({format:'jwk'});const b=(s)=>Buffer.from(s,'base64url');console.log(JSON.stringify({public:Buffer.concat([Buffer.from([4]),b(k.x),b(k.y)]).toString('base64url'),private:k.d}))" | ConvertFrom-Json`,
  'Set-Clipboard -Value $pair.private',
  'powershell -ExecutionPolicy Bypass -File tools\\set-runtime-secret.ps1 -Name MOBILE_WEB_PUSH_VAPID_PRIVATE_KEY',
  'Set-Clipboard -Value $pair.public',
  'powershell -ExecutionPolicy Bypass -File tools\\set-runtime-secret.ps1 -Name MOBILE_WEB_PUSH_VAPID_PUBLIC_KEY',
  CLEAR_CLIPBOARD,
  'Write-Output "Public key, safe to show: $($pair.public)"',
)

/**
 * Store the contact push services are given for the sender, through the same desktop prompt as a secret.
 *
 * It is an address rather than a secret, but it is the operator's own, so the dashboard never shows it: the status
 * reports only whether it is set and well formed. Apple's push service refuses a push without one.
 */
export const SET_WEB_PUSH_SUBJECT = inCheckout(
  'powershell -ExecutionPolicy Bypass -File tools\\set-runtime-secret.ps1 -Name MOBILE_WEB_PUSH_SUBJECT '
    + "-Prompt 'A mailto: address or an https: URL push services can use to reach you, for example mailto:you@example.com'",
)

/** Copy the configured value to the clipboard without displaying it. */
export function copySecret(name: string): string {
  return inCheckout(`powershell -ExecutionPolicy Bypass -File tools\\copy-runtime-secret.ps1 -Name ${variable(name)}`)
}

/** Remove the name's line from runtime.env and nothing else, displaying no value. */
export function removeSecretLine(name: string): string {
  return [
    `$envFile = '${RUNTIME_ENV}'`,
    `$kept = @(Get-Content -Path $envFile -Encoding UTF8 | Where-Object { $_ -notmatch '^\\s*${variable(name)}\\s*=' })`,
    'Set-Content -Path $envFile -Value $kept -Encoding UTF8',
  ].join('\n')
}

/** Recreate state-api alone so it reads runtime.env again, without rebuilding (docs/runbooks/MOBILE_ALERTS.md). */
export const RECREATE_STATE_API = inCheckout(
  'docker compose --project-name tradesync-full --env-file E:/Projects/TradeSync/dashboard-runtime/runtime.env '
    + '-f ops/compose.full.yml -f ops/compose.market-command.yml up -d --no-deps --no-build state-api',
)

/** Recreate the three containers that read the operator token (docs/changes/2026-09-15_local-access-hardening.md). */
export const RECREATE_TOKEN_READERS = inCheckout(
  'docker compose `',
  `  --env-file ${RUNTIME_ENV} \``,
  '  -f ops\\compose.full.yml -f ops\\compose.market-command.yml `',
  '  up -d state-api core-scorer discord-reader',
)

/** The state-api log lines for TradingView alerts refused before storage, over the last hour. */
export function refusedAlertsLog(marker: string): string {
  return `docker logs --since 1h tradesync-full-state-api-1 2>&1 | Select-String "${marker.replace(/"/g, '')}"`
}
