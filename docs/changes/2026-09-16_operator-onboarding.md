# 2026-09-16 — Operator onboarding: TradingView alerts, phone notifications, WalletConnect and the operator token, in plain words

Branch `claude/operator-onboarding` from `566fea9`, merged into
`codex/2026-09-01-dashboard-overhaul` at `1547fcf`. **Not deployed**, and **migration 037 is not
applied** — the live database is at `033`. Paper mode untouched (`DRY_RUN=true`,
`EXECUTION_ENABLED=false`); no key, signer, wallet or execution path changed.

This exists because four setup steps were the operator's to do but were never explained anywhere:
what a TradingView alert does once it arrives, whether a phone needs an app, what the operator
token is for, and where a WalletConnect project ID comes from. Each is now answered on the screen
where the step is taken.

## What it adds

**TradingView alert setup, on Knowledge intake** (`components/intake/TradingViewSetup.tsx`,
`TradingViewSteps.tsx`, `TradingViewReceipts.tsx`, with a pointer to it from Settings). It shows
the public webhook URL, the exact message template to paste (in template order, with the
placeholders an operator must replace by hand marked), whether the webhook secret is configured —
never its value — and the most recent alerts TradingView actually sent, each with its verdict:
accepted into quarantine for review, or refused with the reason. An interval TradingView sends as
bare minutes is shown as "15m"; anything it sends as text ("1D") is shown as sent.

**Phone notifications** (`components/mobile/PhoneSetupChecklist.tsx`, `PhoneStepDetail.tsx`,
`MobileKeyEntry.tsx`, `phoneChecklist.ts`). A seven-step checklist, each step marked from live
state rather than assumption: install the free **ntfy** app (Play Store / App Store links are in
the checklist), set the mobile control key on this PC, enter it in this browser session, create
subscription details per phone, subscribe to the topic in ntfy, send the generic test, and confirm
it arrived. No other app is required.

**Control-event opt-in per phone** (migration 037's `control_events_enabled_at`, plus
`state-api`'s producer). A phone that opts in is notified when the paper kill switch is engaged or
cleared. Two rules are enforced in the database and the producer: a phone must have confirmed a
test receipt before it can opt in, and opting in never replays events from before the opt-in.
Messages stay generic — "TradeSync needs attention. Open your dashboard." with a reference — so a
lock screen never shows what happened.

**WalletConnect project ID** (`components/settings/WalletConnectSettings.tsx`,
`walletConnectText.ts`, `operator_public_settings` in migration 037). The public project ID from
the Reown dashboard is saved with an audit row for every change (who, when, what it replaced), and
pairing starts from it. Text shaped like a recovery phrase or a private key is refused in the
browser, cleared from the box and never sent.

**The operator token, explained** (`components/settings/OperatorTokenGuide.tsx`,
`operatorTokenText.ts`). Three states in plain words: off (correct while everything listens on
127.0.0.1, as now), on (every change needs the token; reading does not), and set-but-too-short
(under 32 characters, so state-api refuses every change), each with the steps to change it.

**Wallets, explained** (`components/wallet/WalletSafetyNotes.tsx`, beside the watch-only account).
It states plainly that TradeSync never asks for a seed phrase, private key or passphrase and has
nowhere to type one. The watch-only field accepts a public EVM address only.

## Verification

- **Real-SQL acceptance**, `tools/qa_operator_onboarding_sql.py`, against a throwaway PostgreSQL
  16.15 container on a non-default port with `ops/sql/schema.sql` and all 34 migrations applied,
  everything inside one transaction that was rolled back, with network egress blocked in-process
  (only in-process ASGI requests allowed, ntfy publishing replaced by a local fake):
  - settings: save, no-op save, clear, audit newest first, malformed ID refused by the database;
  - receipts: newest TradingView receipt with verdict and reasons, no payload returned;
  - notifications: confirmed receipt required; engage and resume queued once each as the generic
    message; paper lifecycle events beside them; shared budget; opt-out enforced at delivery;
    all-day quiet hours; no event from before the opt-in.
- **Cockpit**: `npm test` and `npm run build` both pass on the merged tree.
- **Every Python suite** passes on the merged tree (root 1083, state-api 546, market-data 160,
  exec-hl-svc 11, signer-svc 14).

## Still the operator's to do

Nothing here performs the setup. Sending a real TradingView alert, installing ntfy and confirming a
test on each phone, pasting a WalletConnect project ID, and deciding whether to turn the operator
token on remain operator acts, and migration 037 must be applied first.
