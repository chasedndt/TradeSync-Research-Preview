import { test } from 'node:test'
import assert from 'node:assert/strict'
import { importTs } from './support/importTs.mjs'

// Commands the dashboard shows for the operator to run on this PC. They name a secret, never carry one.
const commands = await importTs('src/components/onboarding/hostCommands.ts')
const LOOKS_LIKE_A_VALUE = /[A-Za-z0-9_-]{32,}/

test('storing a new secret makes it on the clipboard, writes it through the prompt, then clears the clipboard', () => {
  const lines = commands.storeNewSecret('MOBILE_ALERTS_CONTROL_KEY').split('\n')
  assert.equal(lines[0], 'Set-Location E:\\Projects\\TradeSync\\dashboard-overhaul-2026-09-01')
  assert.ok(lines.includes('[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)'))
  assert.ok(lines.includes('powershell -ExecutionPolicy Bypass -File tools\\set-runtime-secret.ps1 -Name MOBILE_ALERTS_CONTROL_KEY'))
  assert.equal(lines.at(-1), "Set-Clipboard -Value ' '")
  assert.ok(lines.findIndex((line) => line.includes('set-runtime-secret')) > lines.findIndex((line) => line.startsWith('Set-Clipboard -Value ([Convert]')))
})

test('copying names the variable and nothing else', () => {
  assert.equal(commands.copySecret('TRADINGVIEW_WEBHOOK_SECRET'),
    'Set-Location E:\\Projects\\TradeSync\\dashboard-overhaul-2026-09-01\npowershell -ExecutionPolicy Bypass -File tools\\copy-runtime-secret.ps1 -Name TRADINGVIEW_WEBHOOK_SECRET')
})

test('only an environment variable name is accepted, so no command can carry anything else', () => {
  for (const name of ['lowercase', 'SPACE NAME', 'NAME; Get-Content runtime.env', '', '1NAME']) {
    assert.throws(() => commands.copySecret(name))
    assert.throws(() => commands.storeNewSecret(name))
    assert.throws(() => commands.removeSecretLine(name))
  }
})

test('removing a secret removes only its own line and displays nothing', () => {
  const command = commands.removeSecretLine('STATE_API_OPERATOR_TOKEN')
  assert.ok(!/Write-Host|Write-Output|Get-Content [^|]*$/m.test(command))
  const pattern = new RegExp(command.match(/-notmatch '([^']+)'/)[1])
  const lines = ['POSTGRES_DB=tradesync', 'STATE_API_OPERATOR_TOKEN=abc', '  STATE_API_OPERATOR_TOKEN = abc', 'STATE_API_OPERATOR_TOKEN_OLD=1', '# STATE_API_OPERATOR_TOKEN=note']
  assert.deepEqual(lines.filter((line) => !pattern.test(line)), ['POSTGRES_DB=tradesync', 'STATE_API_OPERATOR_TOKEN_OLD=1', '# STATE_API_OPERATOR_TOKEN=note'])
})

test('recreating reads runtime.env again without rebuilding or removing anything', () => {
  for (const command of [commands.RECREATE_STATE_API, commands.RECREATE_TOKEN_READERS]) {
    assert.match(command, /up -d/)
    assert.doesNotMatch(command, /\bdown\b|--build|\s-V\b|--renew-anon-volumes|\s-v\b/)
  }
  assert.match(commands.RECREATE_STATE_API, /--no-deps --no-build state-api$/)
  assert.match(commands.RECREATE_TOKEN_READERS, /up -d state-api core-scorer discord-reader$/)
})

test('the refused-alert log command searches for the marker the receiver logs', () => {
  assert.equal(commands.refusedAlertsLog('tradingview alert refused'),
    'docker logs --since 1h tradesync-full-state-api-1 2>&1 | Select-String "tradingview alert refused"')
})

test('no command contains anything shaped like a secret value', () => {
  const all = [
    commands.storeNewSecret('STATE_API_OPERATOR_TOKEN'), commands.copySecret('TRADINGVIEW_WEBHOOK_SECRET'),
    commands.removeSecretLine('STATE_API_OPERATOR_TOKEN'), commands.RECREATE_STATE_API, commands.RECREATE_TOKEN_READERS, commands.CLEAR_CLIPBOARD,
    commands.SET_WEB_PUSH_SUBJECT,
  ]
  for (const command of all) {
    const stripped = command.replace(/[A-Z][A-Z0-9_]{8,}/g, '').replace(/dashboard-overhaul-2026-09-01|dashboard-runtime|RandomNumberGenerator|ExecutionPolicy/g, '')
    assert.doesNotMatch(stripped, LOOKS_LIKE_A_VALUE, command)
  }
})

test('the Web Push contact is entered through the desktop prompt and never typed into the command', () => {
  const lines = commands.SET_WEB_PUSH_SUBJECT.split('\n')
  assert.equal(lines[0], 'Set-Location E:\\Projects\\TradeSync\\dashboard-overhaul-2026-09-01')
  assert.match(lines[1], /^powershell -ExecutionPolicy Bypass -File tools\\set-runtime-secret\.ps1 -Name MOBILE_WEB_PUSH_SUBJECT -Prompt '/)
  assert.equal(lines.length, 2)
  assert.doesNotMatch(commands.SET_WEB_PUSH_SUBJECT, /Write-(Host|Output)|Get-Content/)
})
