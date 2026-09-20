# StrikeZone research evidence in Integration Pipeline — 19 September 2026

## Repo-truth delta

TradeSync previously represented Strike Zone only through TradingView/Pine alert receipts and the quant-lab ledger. The completed browser-research evidence pack in ChaseOS was not visible in the Cockpit and therefore could not be distinguished from an absent connector.

This record is also the project-local build log, daily activity record and handover for the work. Canonical ChaseOS promotion remains governed-writer work; no canonical-vault writeback was performed.

## Implemented

- The Windows host bridge now selects the newest complete StrikeZone run by the modification time of its manifest and strict-validation receipts.
- It stores a compact `strikezone_research_evidence_v1` summary in `sz_documents`; private screenshots and browser artifacts remain in ChaseOS and are not copied into TradeSync.
- Migration `041_strikezone_research_evidence.sql` extends the existing constrained document kind.
- State API exposes `GET /state/strikezone/research-evidence` and includes the receipt in the optional Strike Zone Pipeline node.
- Independent Hermes, ChaseOS, TradingView and StrikeZone probes run concurrently.
- The Pipeline card shows receipt freshness, evidence and chart counts, required source coverage, source counts, strict-validation blockers and the no-execution boundary.

## Deterministic status rules

- A complete, fresh receipt with strict validation passing and no missing required source class may read `live`.
- A present but degraded, blocked or stale receipt reads `partial` and lists the exact gaps.
- Missing receipt and missing TradingView evidence remain unverified; repository code alone never reads as connected.
- Evidence readiness never grants publication, wallet, approval, signing or order authority.

## Current 19 September receipt

Run `2026-09-19-tradesync-v2-completion` contains 35 evidence items and 15/15 required charts. It is deliberately shown as degraded because `x_social` and `perplexity_digest` are unavailable. Strict validation remains blocked by the stale Perplexity detail gate and absent publication drafts. External delivery was not performed and execution authority remains false.

## Verification

- Focused Python/API/bridge tests: 29 passed.
- Host bridge tests: 11 passed.
- Full repository harness after repairing a stale horizon-fixture interval: 1,343 root tests, 764 State API tests, 205 market-data tests, 11 execution-service tests, 16 signer-service tests, 62 root subtests and all 17 stack-backed integration tests passed.
- Cockpit production build: passed.
- Cockpit tests: 265/265 passed.
- Python compilation for all changed bridge/API modules: passed.
- Bounded Docker runtime: schema migration 041 applied; Tier A is 7/7 ready; Hyperliquid market stream, scorer and fusion probes are live; paper mode and `execution_authority=false` confirmed by API readback.
- Route smoke: all 20 Cockpit routes returned HTTP 200. State API health, Integration Pipeline, StrikeZone research evidence and execution-status routes returned HTTP 200.
- Rendered desktop and mobile acceptance: the expanded Strike Zone card shows the exact receipt, source gaps and false execution authority; no document overflow, console errors, exceptions or target crashes were observed.
- The host bridge task `TradeSync-StrikeZone-Quant-Bridge` completed with result 0 and remains scheduled at its existing five-minute cadence.
- After the operator started Hermes, TradeSync observed `hermes-agent` 0.21.0 live on the configured gateway with the declared model present, Discord and API-server platforms connected, an open/agreeing kill-switch gate, zero connector gaps and 100% recent heartbeat availability.
- A real bounded `explain` request completed in 11.6 seconds. Its advisory response was stored as accepted untrusted material in `quarantine_intake` under receipt digest `15a47e6dd9b1c984d1beedec615aa014bd78e2d731c172ec4a2fee64d5415d20`; it has no review, extraction, promotion, scoring or execution authority.
- Hermes connector, control, gate, fleet and link regression selection: 62 passed.

Visual evidence: `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-19-strikezone-evidence-dashboard`.

## Runtime gaps kept explicit

- Hermes is now live and integrated. One separate ChaseOS closeout-invariant watchdog reports that its latest governed closeout record is older than 14 days; this is exposed as an operations warning rather than being rewritten or hidden by TradeSync.
- TradingView/Pine is configured but has no alert receipt in the last 24 hours.
- StrikeZone remains partial because `x_social` and `perplexity_digest` are unavailable and strict validation reports `perplexity_latest_markdown_detail_gate` and `draft_files`.
- Direct Hyperliquid liquidation flow, complete regime-block coverage and the closed-loop performance jobs remain unimplemented; cross-venue liquidation streams are context-only and are not substituted as Hyperliquid truth.
- `npm run lint` is not currently runnable because this repository has no ESLint configuration. Build and test verification are unaffected, but lint configuration remains a tooling gap.

## Runtime recovery note

Docker Desktop was initially blocked by two stale local socket directories. They were moved to timestamped quarantine paths under the existing Docker application-data directory; no image, volume, repository, credential or user data was deleted. Docker subsequently started normally.

## Untouched boundaries

No live order, wallet signature, exchange action, publication, external deployment or ChaseOS canonical writeback is introduced by this change.
