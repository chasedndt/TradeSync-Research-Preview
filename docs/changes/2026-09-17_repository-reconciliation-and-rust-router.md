# Repository reconciliation, partitioned data plane and Rust alert router — 17 September 2026

## Repo-truth delta

The active integrated checkout was `2cc6a1c`. Three later Claude worktrees were
real but unmerged, so they were not part of the running/product branch:

- `claude/activity-outcomes`: alert-state history, paper activity in the audit
  export, MFE/MAE, costs, realised P&L and expectancy;
- `claude/execution-chain`: State API execution-route split, recovery-phrase
  redaction and the append-only signer/executor journal;
- `claude/market-data-plane`: shared HTTP clients and the market-data model and
  Hyperliquid-context module split.

They are now merged into `codex/2026-09-01-dashboard-overhaul`. Focused suites
passed before merging and the combined suites passed afterwards.

## Seven-area engineering audit

| Area | Current source truth | Remaining acceptance |
|---|---|---|
| Rust | Shared contracts and the new `alert-router-rs` workspace service compile and test. The router has authenticated bounded HTTP ingress, a Redis consumer group, PostgreSQL dedupe/event storage, restricted/expired suppression, mobile-outbox fan-out, dead-letter receipts and routed receipts. | Migration 039 and the service are not deployed because Docker Desktop's privileged Windows service is stopped. |
| PWA/Web Push | Manifest, icons, service worker, permission/subscription flow, RFC 8291/8292 sender, tap acknowledgement, retries and delivery ledger are implemented and previously deployed. | Real Android and iPhone subscription, push, display and tap receipts. |
| Cockpit surfaces | Activity & Evidence has Decisions, Approvals, Orders, Alerts and Outcomes; Settings is operator-focused; the profile menu explicitly says there is no authentication/session. | Latest paper-economics rows are backend/audit data; richer economics presentation may follow measured operator use. |
| Data plane | Migration 039 defines partitioned market events, candles and alert events with default partitions and indexes. A shared validator deterministically refuses duplicate IDs, backward/future/stale timestamps, false authority and missing lineage. | Real PostgreSQL UP acceptance and migration application after Docker recovery; producers can adopt the new tables incrementally. |
| Phase 4 metrics | Thesis adherence, regime fit, five reconciliation views, bounded audit exports, paper MFE/MAE, fees, funding, modelled slippage, realised P&L and closed-position expectancy are implemented. | Forward samples are required; an empty/small cohort is not performance evidence. |
| Alert reliability | Python delivery has bounded backoff, dead letters, acknowledgements, Web Push/ntfy selection and ledger views. Rust ingress adds durable cross-project routing and Redis recovery. | Live Rust-to-mobile acceptance and device receipt after runtime recovery and enrollment. |
| TODO/FIXME | The only actionable production TODO was fusion exposure context. It now reads read-only Hyperliquid positions and aggregates absolute notional by symbol without inventing margin utilization. | Intentional gated stubs remain: live signing/execution and the non-selected TimescaleDB adapter. UI `todo` is a display state, not source debt. |

## New data-plane boundary

Migration `039_partitioned_data_plane.sql` adds:

- `data_event_registry`, the global event-ID dedupe seam;
- range-partitioned `market_events_v1`, `market_candles_v1` and
  `alert_events_v1` parent tables;
- default partitions so ingestion remains available before monthly partition
  maintenance is introduced;
- lookup, sequence, receipt and payload-hash indexes;
- JSON lineage/shape constraints and explicit authority/classification states;
- `mobile_alert_outbox.alert_event_id`, linking delivery lifecycle rows back to
  the reusable alert envelope.

The pure Python quality gate is intentionally independent of PostgreSQL. It
produces stable refusal codes before persistence; database constraints remain
the final durable guard.

## Rust router boundary

`alert-router-rs` owns notification ingress only. It cannot approve, sign or
execute. HTTP producers use a local bearer token, while internal asynchronous
producers write `alert_event_v1` JSON to `alerts:ingress` in the `payload`
field. The router acknowledges a Redis message only after either:

1. the event and its mobile fan-out are committed to PostgreSQL; or
2. malformed/refused input is committed to `alerts:dead-letter`.

Transient PostgreSQL failures leave the Redis entry pending. Successful routes
write `alerts:routed`. Restricted payloads and expired events are retained but
not delivered.

The Compose service is behind the `notifications` profile. A missing producer
token therefore cannot break the standard stack, and enabling the profile with
an empty/short token fails closed.

## Verification

- Pre-merge focused suites: Activity/Outcomes `56 passed`; execution-chain
  `50 passed`; market-data-plane `15 passed`.
- Integrated root suite: `1326 passed, 17 deselected, 62 subtests passed`.
- Integrated State API: `751 passed`.
- Integrated market-data: `172 passed`.
- Cockpit: production build passed; Node suite `250 passed`.
- Rust workspace: `7 passed` (three router, four shared contract).
- Signer, signer-boundary and network isolation: `37 passed`, including restart replay refusal.
- New migration/quality checks: `10 passed`.
- Compose base and `notifications` profile render successfully.

## Verification limit and next safe action

Docker Desktop processes started, but `docker-desktop` stayed stopped because
Windows service `com.docker.service` is stopped. This unelevated session cannot
open that service. Therefore migration 039 is source-verified but **not applied**,
and the Rust container is **not live-verified**.

The next operator action is to start Docker Desktop with the required Windows
privilege (or restart Windows/Docker normally). Then run the transactional
migration, generate/store `ALERT_ROUTER_PRODUCER_TOKEN`, start the
`notifications` profile and perform one paper/system alert acceptance. No wallet
or trading authority is involved.

### Runtime acceptance follow-up

Completed later on 17 September in
[the runtime/wallet continuation](2026-09-17_wallet-runtime-and-style-admission.md):
Docker recovered, migrations 039/040 applied, the router container became live,
unauthenticated ingress was refused, and an authenticated notify-only alert was
persisted and published. The historical limitation above describes the earlier
checkout state and is no longer the current runtime truth.

## Trading-performance boundary

This work improves measurement and routing; it does not establish a profitable
scalp or swing strategy. The legacy measured strategy remains loss-making.
Promotion still requires registered forward observations, costs, sufficient
sample size and a held-out result. Execution remains disabled.

## Signer restart safety follow-up

The integrated durable journal revealed that signer approvals were still held
only in memory. The signer now fsyncs an `approval_spent` fact before it signs,
loads those facts at startup, and refuses signing when its journal is missing or
untrustworthy. Its optional Compose profile mounts a dedicated volume. A crash
may burn an approval before returning its signature (requiring reconciliation),
but can no longer make the approval reusable. This changes no execution gate and
introduces no key.
