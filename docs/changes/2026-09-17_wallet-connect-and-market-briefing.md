# Wallet connect and live market briefing — 2026-09-17

## Repo-truth delta

Before this change, the wallet registry and direct EIP-1193 request existed, but the operator had to discover them inside a form-heavy Execution Readiness card. The top-right control was an operator-attribution drawer with raw API JSON links. Mission Control refreshed market rows, but did not expose its lower-to-higher-timeframe state in one scan, did not put the edition archive on the homepage, and a State API restart after an edition slot could skip that edition.

After this change, TradeSync has a persistent DApp-style wallet control in the header, a modal wallet chooser with official Phantom branding, a compact connected-account registry, a cleaner local-control drawer, a cross-market horizon map, a prominent market-moving-event banner, an on-page briefing archive, and startup catch-up for a missed same-day scheduled edition.

## Wallet boundary

- The connector uses Phantom's documented injected EVM provider and requests `eth_requestAccounts` only.
- EIP-6963 discovery is supported for multiple injected wallets, with `window.phantom.ethereum` preferred for Phantom.
- TradeSync receives and persists only the public EVM address plus connector/audit metadata.
- Recovery phrases and private keys are never entered into TradeSync. Import/restore remains inside Phantom's trusted application.
- The full Phantom Connect SDK modal is not claimed: it needs an operator-created Phantom Portal app and App ID. The injected-provider connector works without pretending that requirement is satisfied.
- The desktop launcher now prefers Chrome and reuses the standard Chrome profile that already contains Phantom. When no profile contains Phantom, it opens Chrome `Default`; the operator can use the in-app official Phantom install link once, after which the same launcher profile is reused. The automated StrikeZone browser profile is deliberately not repurposed as a wallet profile.
- Wallet connection grants no order, signing, approval, or live-execution authority.

## Mission Control

- BTC, ETH and SOL now show 1h, 4h, 8h, 1d, 1w and 1m measured state in one table.
- The 1d and 1w volatility corridors are shown as scenarios, not guaranteed targets.
- The next market-moving calendar event is promoted above the horizon grid.
- The latest six frozen thesis editions are linked as a briefing archive.
- Horizon data polls every minute; market snapshots continue to poll every five seconds.
- Scheduled thesis editions remain frozen records. The scheduler now catches up the most recently missed same-day slot after a State API restart and keeps the original three daily future slots.
- System Health and the context-only provider strip now use full-width stacked rows. This removes the unusable blank column produced when the short health card previously sat beside the taller provider card.

## Operator UI

- The top-right trigger reads `Local controls` rather than implying an online account.
- The drawer has a real header and close control.
- Audit entries open their Cockpit pages; raw JSON links were removed from the primary operator interaction.
- The local attribution/authentication limitation remains explicit inside the drawer.

## Tests and evidence

- Cockpit production build: passed; Cockpit suite: `250 passed`.
- State API scheduler tests: `3 passed`.
- Docker: rebuilt and locally deployed `state-api` and `cockpit-ui`.
- Startup catch-up observed live as `ny-premarket`, trigger `schedule_catchup`, reason `runtime started after scheduled edition`.
- Responsive visual QA: `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-17-wallet-mission-control`.

## Untouched boundaries and remaining acceptance

- No private key, recovery phrase, wallet signature, order, deposit, withdrawal, bridge, or live-trading authority was requested.
- The isolated signer and live executor remain disabled/fail-closed.
- A physical Phantom extension connection must be accepted by the operator in the browser profile where Phantom is installed.
- A future official Phantom Connect SDK/social-login modal needs a Phantom Portal app, verified allowed origin and public App ID supplied through governed configuration.
