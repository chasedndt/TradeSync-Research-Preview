# Desktop launcher, wallet and 4-day liquidity QA — 17 September 2026

## Repo-truth delta

The desktop shortcut already pointed at the safe TradeSync launcher, but an
ordinary Docker Compose progress line on stderr could be interpreted by the
outer PowerShell as a terminating error. The stack could be healthy while the
shortcut stopped before opening the Cockpit.

`tools/start-tradesync.ps1` now preserves real Compose exit codes while treating
progress output as output. It also preserves the separately managed Cloudflare
and signer overlay containers rather than treating them as removable orphans.
`tools/launch-tradesync.ps1` waits for Cockpit HTTP 200, writes a dated `READY`
receipt and then opens the Edge app window. The actual desktop `.lnk` passed this
acceptance with Docker Engine 29.7.2.

## Wallet implementation boundary

The wallet UI is React/TypeScript. Its registry and Hyperliquid account reads
are Python/FastAPI with PostgreSQL audit rows. Rust is used by shared contracts
and the notification router, not by the browser wallet button. Direct Phantom
or another injected EVM wallet uses `eth_requestAccounts`; after address
approval TradeSync reads perpetual account value, withdrawable value, margin,
positions, open orders and fills. It is a Hyperliquid operator connection, not
a Phantom clone or DApp browser, and it grants no signing authority.

## Liquidity addition

The resting-liquidity heatmap now includes an explicit 4-day view in addition
to 6h, 24h, 3d, 7d and 30d. It uses 96 hourly buckets at three significant
figures. Live BTC acceptance returned 62 populated buckets because durable book
recording began on 14 September; missing earlier buckets stay blank.

## Visual QA

The project-specific review is at
`E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-17-wallet-runtime-launcher`.
Desktop 1440x1000 and mobile 390x844 passed with no page errors and no
document-level horizontal overflow. A clipped paper-rehearsal action discovered
during the first pass was fixed and the review rerun.

Physical Phantom approval and readback of a populated operator account remain
operator acceptance. Live trading remains disabled.

