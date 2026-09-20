import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const thesis = await readFile(new URL('../src/components/home/MarketThesisCard.tsx', import.meta.url), 'utf8')
const narrative = await readFile(new URL('../src/components/thesis/marketNarrative.ts', import.meta.url), 'utf8')
const edition = await readFile(new URL('../src/components/thesis/EditionView.tsx', import.meta.url), 'utf8')
const comprehensive = await readFile(new URL('../src/components/thesis/ComprehensiveMarketBrief.tsx', import.meta.url), 'utf8')
const walletCss = await readFile(new URL('../src/components/wallet/WalletConnectMenu.module.css', import.meta.url), 'utf8')
const harnessCss = await readFile(new URL('../src/components/harness/HarnessSwitch.module.css', import.meta.url), 'utf8')
const events = await readFile(new URL('../src/components/EventRow.tsx', import.meta.url), 'utf8')
const header = await readFile(new URL('../src/components/layout/Header.tsx', import.meta.url), 'utf8')

test('Mission Control leads with readable paragraphs, a level picture and conditional scenarios', () => {
  for (const phrase of ['The market in plain English', 'Bitcoin decision map', 'Support', 'Resistance', 'What confirms strength', 'What keeps us waiting', 'What proves the recovery wrong']) {
    assert.match(thesis, new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'))
  }
  for (const phrase of ['the monthly chart', 'For this week', 'daily and four-hour charts', 'not a market to reduce to a one-word']) assert.match(narrative, new RegExp(phrase, 'i'))
  assert.doesNotMatch(narrative, /outperforming BTC by .*percentage points/i)
})

test('the interactive player precedes the long written thesis and evidence is optional', () => {
  assert.ok(edition.indexOf('<InteractiveThesisPlayer') < edition.indexOf('<ComprehensiveMarketBrief'))
  assert.match(comprehensive, /Evidence behind this thesis/)
  assert.match(comprehensive, /<details className=\{styles\.appendix\}>/)
})

test('the wallet connector becomes an icon-first control when the desktop sidebar is expanded', () => {
  assert.match(walletCss, /sidebar-expanded[^}]*triggerCopy[^}]*display:\s*none/s)
  assert.match(walletCss, /sidebar-expanded[^}]*\.trigger[^}]*width:\s*48px/s)
})

test('the 390px header keeps the wallet in frame and leaves the full harness action on its page', () => {
  assert.match(harnessCss, /max-width:\s*480px[\s\S]*?\.action\s*\{[\s\S]*?display:\s*none/)
})

test('economic risk keeps forecast and previous beside explicit outcome cases', () => {
  assert.match(events, /forecast/)
  assert.match(events, /previous/)
  assert.match(events, /Outcome scenario map/)
  assert.match(events, /not guaranteed price directions/)
})

test('the header leaves time and health evidence to the readiness surfaces', () => {
  assert.doesNotMatch(header, /System time synced/)
  assert.doesNotMatch(header, /<time/)
  assert.match(header, /<OperatorMenu \/>/)
  assert.match(header, /<WalletConnectMenu \/>/)
})
