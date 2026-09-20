# Runtime recovery, wallet registry and style-aware paper admission — 17 September 2026

## Repo-truth delta

The active branch contained every Claude branch tip, but two Claude worktrees
still held uncommitted engineering. Those files were preserved in commits
`eeb271e` and `e6df2a6`, then integrated by merge commits `455630c` and
`bb19272`. Nothing was discarded and nothing was pushed.

## Docker recovery and repeatable startup

Docker Desktop was failing before its engine started. Its host logs named
unreadable AF_UNIX reparse points under
`%LOCALAPPDATA%\Docker\run`, including `sailor-ingest.sock` and
`dockerInference`. The E: project location was not the cause.

The disposable `run` directory was moved intact to
`run.stale-20260917-1102`, a clean directory was created, and Docker started
without resetting volumes, images, containers, Ubuntu, or Hermes. The recovery
is now encoded in `tools/repair-docker-runtime.ps1`: it changes nothing unless
Docker first fails normal startup **and** the exact known socket signature is in
the current Docker logs. `tools/start-tradesync.ps1` starts the operator,
evidence, and notification profiles but not paper execution. The desktop
`TradeSync.lnk` uses `tools/launch-tradesync.ps1`, retains the canonical icon,
starts/repairs the stack, and then opens the Cockpit.

Qdrant 1.19 removed `curl`; the old Compose health check could therefore never
pass. It now performs a container-local TCP liveness check with Bash. The API
`/healthz` was separately read back successfully.

## Deployed data and alert plane

- migrations 039 and 040 are applied;
- the Rust 1.88 router is live on loopback port 8010;
- an unauthenticated alert was refused with HTTP 401;
- authenticated event `router-proof-4a17181e7be54531a33684a337eb8d9d`
  was accepted, published to Redis, and persisted in `alert_events_v1` as an
  internal queued notification;
- Hyperliquid's market stream is connected and non-degraded for all ten tracked
  markets; context, order-book, and candle channels were fresh;
- Binance and Bybit liquidation streams are connected as context-only evidence;
- PostgreSQL, Redis, market-data, ingest gateway, core scorer, fusion engine,
  Qdrant, State API, Cockpit, Discord reader, and alert router are running.

The producer token authenticates notification producers only. It is not a
wallet token and carries no trading authority.

## Wallet manager

Migration 040 adds an audited public-address registry. The Execution surface
now supports direct Phantom/EIP-1193 browser connection, the existing optional
WalletConnect QR path, account selection, and disconnect. It records only:

- public EVM address;
- label and connector type;
- operator, status, and timestamps;
- append-only add/reconnect/rename/disconnect events.

Recovery phrases and private keys are deliberately imported in Phantom or the
chosen wallet, never in TradeSync. This matches the safe product flow while
still giving the operator a simple Add Wallet action. Automated Hyperliquid
orders remain a later, separately approved agent/API-wallet step through the
isolated signer.

## Opportunity-quality correction

The previous actionable list mixed a one-minute label with 15-minute
opportunity lifetime, a five-minute entry-freshness rule, and scalp/intraday/
swing lifecycle choices. It could present a short-lived directional episode
without proving that its intended holding horizon agreed.

`paper-style-alignment-v1` now gates managed-paper candidates and entry:

| Style | Required measured horizon | Minimum ordinary implied move |
|---|---:|---:|
| scalp | 1 hour | 0.40% |
| intraday | 8 hours | 0.80% |
| swing | 3 days | 2.00% |

The measurement must be available, no more than 15 minutes old, point in the
same direction, and have an implied range at least as large as the target
floor. Refused candidates remain inspectable with exact reasons. The decision
is frozen into entry evidence. This should produce fewer, more coherent paper
trades; it is not evidence of profitability.

Three immutable forward trials are registered for scalp, intraday, and swing.
Paper entries were resumed only after clean reconciliation, but the system does
not create a synthetic position when no candidate passes. Forward outcomes,
costs, sufficient sample size, and held-out validation remain mandatory before
any strategy or execution promotion.

## Verification

- wallet State API: `3 passed`;
- style alignment, horizon route and managed-paper routes: `27 passed`;
- broader focused wallet/paper suite: `20 passed`;
- Rust workspace: `7 passed`;
- Cockpit TypeScript and production build: passed;
- market-data recovered Claude slice: `39 passed`;
- complete Python suite: `1341 passed, 17 deselected, 62 subtests`;
- live State API, wallet registry, market-data, router and Cockpit readback: HTTP 200;
- Qdrant and ingest gateway: healthy after full-profile startup.

The live intraday admission readback withheld all candidates. For BTC, the
measured 8-hour ordinary range was 1.02% (above the 0.80% floor), but the lean
was `mixed` rather than `up`; the exact deterministic refusal was retained.

## Boundaries and next operator acceptance

Execution remains `EXECUTION_ENABLED=false`, `DRY_RUN=true`. No private key was
created, imported, printed, stored, or used. No wallet was connected on the
operator's behalf and no order was placed.

The operator reconfirmed
`${CHASEOS_HOME}` as canonical ChaseOS on
17 September. The live read-only GraphSnapshot mount already points there;
`AGENTS.md`, `CLAUDE.md` and the README preserve the same rule. The retained
`retired private ChaseOS stub` directory was not deleted or copied and is not an active
TradeSync connector or writeback target.

The next operator actions are physical acceptance: click Connect with an
unlocked wallet and approve public-address sharing; enroll Android/iPhone Web
Push or ntfy; and run the supervised paper workflow long enough for the three
registered trials to accumulate outcomes. Agent-wallet approval and non-
broadcast signing acceptance come only after that evidence and an explicit
operator decision.
