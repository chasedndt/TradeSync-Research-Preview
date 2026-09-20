# 18 September 2026 — Phantom connect and wallet settings

## Repo-truth delta

The header wallet sheet previously combined injected-wallet detection, QR/mobile pairing, a WalletConnect project-ID field, watch-only address entry and connected-account management. The `/settings` route existed, but the primary sidebar did not expose it. Phantom discovery also stopped after a 180 ms EIP-6963 window and did not inspect a multi-wallet `window.ethereum.providers` array, so a later Brave injection could be reported incorrectly as a missing extension.

## Changes

- The global header sheet is now Phantom-only: one public-address connection action, one short safety boundary and a compact Settings handoff.
- Phantom discovery now checks `window.phantom.ethereum`, EIP-6963 announcements, `window.ethereum.providers`, the legacy provider and delayed injection for up to 1.2 seconds.
- The unavailable state no longer claims the extension is uninstalled. It distinguishes a visible Phantom namespace from a missing EVM provider and points to wallet settings.
- Settings is now a visible primary-navigation destination.
- Phone/standalone WalletConnect pairing, connected-account management and its public project ID live under `Settings#wallets`; watch-only inspection remains on Execution Readiness.
- Direct hash navigation scrolls the Settings page to the requested section after the React route mounts.
- Wallet status now reports the active public-address registry count instead of always claiming that no wallet is connected.

## Untouched boundaries

- No recovery phrase, private key, signing request or transaction request is accepted by the Cockpit.
- The Phantom request remains `eth_requestAccounts`; TradeSync stores only the returned public EVM address.
- Live execution remains disabled. Signer, approval, policy and reconciliation gates were not changed.
- No WalletConnect/Reown account or project ID was created.

## Verification

- `npm test`: 265 passed, 0 failed.
- `npm run build`: passed; 3,200 modules transformed.
- Docker image `tradesync/cockpit-ui:dev`: rebuilt and `cockpit-ui` recreated without restarting database, market-data, signer or execution services.
- Rendered browser QA:
  - deployed sidebar exposes Settings;
  - the header sheet contains no phone, project-ID or watch-only form;
  - a controlled injected Phantom provider renders `Connect Phantom`;
  - the no-provider state uses the bounded access message rather than saying Phantom is not installed;
  - the Settings wallet section renders at desktop width.
- Evidence: `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-18-phantom-connect-settings\settings-fullpage.png` (full Settings route, including the wallet section) and `settings-wallets-desktop.png` (desktop navigation acceptance).

The repository has no ESLint configuration, so the existing `npm run lint` script cannot run and reports that no configuration file was found. TypeScript compilation and the full Cockpit test suite pass.

## Remaining physical acceptance

The automated test proves provider discovery and the address-request contract with an injected Phantom-compatible provider. The operator must still press `Connect Phantom` once in the Brave profile that owns the installed extension and approve public-address sharing. That is physical-profile acceptance, not missing source code.
