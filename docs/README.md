# TradeSync Documentation

Public release and security boundaries:

- [Public-source and third-party data notice](../PUBLIC_SOURCE_NOTICE.md)
- [Security policy](../SECURITY.md)

Latest integration evidence: [19 September StrikeZone browser-research receipt, deterministic bridge, runtime verification and visual QA](changes/2026-09-19_strikezone-research-evidence-pipeline.md).

Latest wallet experience: [18 September Phantom-only header connection, Brave provider discovery and visible wallet Settings](changes/2026-09-18_phantom-connect-and-wallet-settings.md).

Latest thesis experience: [17 September horizon story, captions and evidence probabilities](changes/2026-09-17_thesis-horizon-story.md).

Research: [deterministic chart structure, probability calibration and overfitting controls](research/2026-09-17_thesis-evidence-and-calibration.md).

This folder is the documentation system of record for the Hyperliquid-only TradeSync product. Documents are grouped by authority and purpose so historical plans do not silently become current architecture.

## Start here

17 September interactive thesis: [narration-synchronized Hyperliquid chart chapters, temporary edition overlays and Market Canvas handoff](changes/2026-09-17_interactive-thesis-playback.md).

17 September wallet and briefing correction: [DApp-style Phantom public-address connection, cleaner local controls, live horizon map, edition archive and missed-edition catch-up](changes/2026-09-17_wallet-connect-and-market-briefing.md).

17 September launcher and visual acceptance: [desktop shortcut Docker/Cockpit startup, wallet implementation boundary, responsive Execution QA and explicit 4-day resting-liquidity view](changes/2026-09-17_launcher-wallet-liquidity-qa.md).

17 September runtime and wallet continuation: [Claude worktree recovery; Docker stale-socket repair and self-starting desktop shortcut; migrations 039/040; live Rust alert routing; audited Phantom/browser public-address wallet manager; and style-aware paper admission](changes/2026-09-17_wallet-runtime-and-style-admission.md). [Wallet onboarding and authority boundaries](runbooks/WALLET_ONBOARDING.md).

17 September reconciliation: [Three unmerged Claude engineering lines integrated; partitioned event/candle/alert schema and deterministic data-quality gates added; `alert-router-rs` implemented with authenticated HTTP ingress, Redis consumer recovery and durable mobile fan-out](changes/2026-09-17_repository-reconciliation-and-rust-router.md). Its runtime acceptance was completed by the continuation above.

16 September afternoon integration: [Product surfaces, Activity & Evidence and the mobile PWA merged; an executed order that could never be recorded (and could reach the venue twice), a TradingView source check that would refuse every tunnel alert and a Cockpit that stayed down after a Docker restart all fixed; Docker Desktop recovered from its 13:37 crash; migration 038 applied and six services deployed with paper invariants unchanged](changes/2026-09-16_afternoon-integration-faults-and-deploy.md).
16 September product surfaces: [An operator menu that says there is no sign-in, Settings grouped by what each setting governs, the regime summary with its evidence, liquidations by source with a side only where the source supports one, and opportunity briefs from stored records — three read-only routes, no migration, deployed 16 September 17:55](changes/2026-09-16_product-surfaces.md).
16 September mobile PWA and delivery: [Installable Cockpit, Web Push sender (RFC 8291/8292, proven against the RFC vector) on the same retry and dead-letter path as ntfy, single-use tap acknowledgement with no key in the service worker, five bounded retries, dead letters and the delivery ledger — migration 038 applied and deployed 16 September 17:55, no real push sent yet](changes/2026-09-16_mobile-pwa-and-delivery.md).
16 September integration and deploy: [Five branches merged, the frozen lifecycle digest re-frozen on the rules in force, 035 retired, market-data and state-api `main.py` split, and migrations 034, 036 and 037 applied to the running stack](changes/2026-09-16_integration-and-deploy.md).
16 September Activity & Evidence: [The `/logs` placeholder replaced by Decisions, Approvals, Orders, Alerts and Outcomes tabs on the audit export and market alerts, each with its reading time, refresh and an empty state distinct from a failed request, and an unreadable alert stream now answering 503 — no migration, no new route, deployed 16 September 17:55](changes/2026-09-16_activity-and-evidence.md).
16 September outcome metrics and reconciliation: [Thesis adherence and regime fit from frozen evidence, the five reconciliation views beside the execution reconciliation, and a bounded audit export as JSON and CSV — no migration, deployed 16 September 17:55](changes/2026-09-16_outcome-metrics-and-reconciliation.md).
16 September security remainder: [Tunnel network isolation, signer and exec caller tokens, Host check, TradingView source check, error trace ids, body limits and Discord redaction — merged and deployed 16 September; the tunnel move and the caller tokens wait for the operator](changes/2026-09-15_security-remainder.md), [review statuses](security/2026-09-15_local-access-review.md).
16 September operator onboarding: [TradingView alert setup and receipts, phone notification checklist with control opt-in, WalletConnect project ID, operator token and wallet guidance — migration 037 applied 16 September](changes/2026-09-16_operator-onboarding.md).
16 September market-data: [main.py split into runtime, pollers, enrichment and route modules, moved unchanged](changes/2026-09-16_market-data-split.md).
16 September research evidence and PostgreSQL: [Trial specification v2 over the configured universe and settled funding, the declared entry-evidence comparisons (nothing selected), and the crash resets investigated — migration 036 proposed, not applied](changes/2026-09-15_research-evidence-and-postgres.md), [comparison method and results](research/2026-09-16_entry-evidence-comparisons.md).
16 September paper gaps: [Held kill-switch exits audited, exits filled in parts within a declared depth bound, and the target, time expiry and a gap at a candle's open proven on real candles — source only, no migration](changes/2026-09-15_paper-gaps.md).
15 September programme summary: [Paper safety, managed positions, opportunity evidence, local access security and refinements — merged, deployed and verified](changes/2026-09-15_paper-safety-and-quant-programme.md).
15 September paper risk engine: [Kill switch, capital ledger with late-funding adjustments, limits, restart reconciliation and Paper risk panel — migration 031 applied](changes/2026-09-15_paper-risk-engine.md).
15 September managed paper positions: [Versioned lifecycles with trailing stops, depth-walked fills, settled funding, entry evidence cut off at entry, and live-data acceptance — migration 032 applied](changes/2026-09-15_managed-paper-positions.md).
15 September local access: [Loopback-only ports, cross-site change refusal, optional operator token, session-only Cockpit credentials and bridge redaction](changes/2026-09-15_local-access-hardening.md), [security review](security/2026-09-15_local-access-review.md).
15 September opportunity evidence: [One-hour return restart gap closed; positioning candidates tested, none admitted](changes/2026-09-15_restart-gap-and-candidates.md), [candidate results](research/2026-09-15_positioning-candidates.md); [sources combined by track record, shadow only](changes/2026-09-15_evidence-combination.md), [design and worked examples](research/2026-09-15_evidence-combination.md).
15 September operations: [Fleet run progress and output, pipeline feed heartbeats, off-by-default reading schedule, heatmap coverage](changes/2026-09-15_fleet-pipeline-reading-schedule.md); [Community Server jobs at their once-daily minimum](changes/2026-09-15_community-minimum-chain.md).
15 September agent harness: [Kill switch in the Cockpit header that stops and starts the Hermes gateway, with an audited host control process and every TradeSync caller of Hermes refusing while it is stopped — migration 034 not applied, host task not registered](changes/2026-09-15_agent-harness-kill-switch.md).

14 September paper safety: [Persistent entry-pause foundation — source only pending SQL/UI acceptance](changes/2026-09-14_paper-control.md).

Consolidated current handover: [14 September integration state, verification limits and next safety work](HANDOVER_2026-09-14_INTEGRATION_STATE.md).

14 September research registration: [Deployed fixed specifications, fingerprints, immutable registry and evaluation API](changes/2026-09-14_research-registration.md).

14 September source comparison: [Deployed cohort API/UI, experimental liquidity filter, mathematics and remaining evaluation gates](research/2026-09-14_source-comparison-v1.md). Empty current cohort is not a measured source benefit.

14 September entry context: [Frozen Bybit receipts and Hyperliquid book history, causal tests and remaining source evaluation](changes/2026-09-14_entry-liquidation-context.md).

14 September liquidation provenance: [First-received timestamps, replay dedupe and remaining durable-entry work](changes/2026-09-14_first-received-liquidations.md).

14 September mobile lifecycle continuation: [Deployed opt-in, quiet hours, budget policy and remaining phone acceptance](changes/2026-09-14_mobile-lifecycle-policy.md).

14 September real-market API acceptance: [Isolated open/close and unchanged evidence](changes/2026-09-14_paper-api-live-market-acceptance.md), [trading-day readiness checklist](runbooks/TRADING_DAY_READINESS.md).

14 September managed-paper dashboard: [Controls, frozen evidence, desktop/mobile QA and remaining acceptance](changes/2026-09-14_managed-paper-dashboard.md).

14 September managed-paper backend: [Implementation/verification](changes/2026-09-14_managed-paper-backend.md), [research protocol and learning exercises](research/2026-09-14_managed-paper-protocol.md).

14 September mobile foundation: [Outbox, enrollment and verification](changes/2026-09-14_mobile-alert-outbox.md), [Android/iPhone setup and acceptance](runbooks/MOBILE_ALERTS.md).

14 September wallet continuation: [Watch-only positions, orders, fills and remaining acceptance](changes/2026-09-14_watch-only-activity.md).

14 September active-goal continuation: [Liquidity feeds, intraday horizons, verification and remaining integration work](changes/2026-09-14_liquidity-intraday-and-integration-goal.md).

Current status: [13 September roadmap reconciliation and handover closure register](ROADMAP_RECONCILIATION_2026-09-13.md).
Development evidence: [Fleet controls and cost-aware trading research](changes/2026-09-13_fleet-and-trade-research.md).

13 September continuation: [Context-card fit, RSI correctness and handover review](changes/2026-09-13_context-fit-and-handover-review.md).

Pairing acceptance follow-up: [Build, dependency audit and setup-screen QA](changes/2026-09-09_walletconnect-build-acceptance.md).

Optional pairing: [WalletConnect address-only implementation and setup gates](changes/2026-09-09_walletconnect-address-only.md).

Watch-only onboarding: [Public-address account inspection](changes/2026-09-09_watch-only-wallet.md).

Latest UI slice: [Canvas modes, paper outcomes and adapter readbacks](changes/2026-09-09_canvas-and-adapter-readbacks.md).

Current review: [9 September usability, measurement and wallet progression](REVIEW_20260909_USABILITY_AND_WALLETS.md), with updated architecture diagrams and explicit acceptance gaps.

Latest continuation: [Claude handover — 7 September 2026](CLAUDE_CONTINUATION_HANDOVER_2026-09-07.md), including checkout recovery boundaries, current Docker availability, historical verification, and the next paper-pipeline slice.

1. [Repository README](../README.md) — current product boundary and operator start/stop.
2. [Roadmap](../roadmap.md) — delivery sequence, three-week mobile-alert sprint, gates, and future phases.
3. [Standalone and federated architecture](architecture/STANDALONE_FEDERATED_ARCHITECTURE.md) — capability tiers and outage behavior.
4. [Data and knowledge plane](architecture/DATA_AND_KNOWLEDGE_PLANE.md) — database roles, ChaseOS projection, and real-time agent access.
5. [Mobile alert control plane](architecture/MOBILE_ALERT_CONTROL_PLANE.md) — reusable cross-project notification design.
6. [Rust boundaries](architecture/RUST_BOUNDARIES.md) — where Rust is adopted and where Python/TypeScript remain appropriate.
7. [Quant Foundations — Book 1](quant-learning/README.md) — notation-first education, weighting, paper-risk caps, and practice gates.
8. [Regime Rulebook v1](architecture/REGIME_RULEBOOK_V1.md) — deterministic scoring, provenance, versioning, and outage behavior.
9. [Regime Lab API](contracts/REGIME_LAB_API.md) — private learning controls, same-evidence comparison, persistence, and fail-closed boundaries.
10. [Regime Lab live-runtime verification](changes/2026-09-02_regime-lab-live-runtime.md) — Docker repair, live feature evidence, restart behavior, tests, and remaining gaps.
11. [Integration Pipeline status v1](contracts/INTEGRATION_PIPELINE_STATUS_V1.md) — live probes, declared connectors, missing links, and recovery semantics.
12. [Regime-backed paper signal path](changes/2026-09-07_regime-backed-paper-signal.md) — one-hour return admission, catalog 1.1.0, the 0.55 coverage ceiling, admission gates, and replay idempotency.
13. [Outcome measurement and directional CVD](changes/2026-09-08_outcomes-and-directional-cvd.md) — forward-return measurement, the first track record, and a second admitted directional feature.
14. [Dashboard truthfulness and 24h change](changes/2026-09-08_dashboard-truthfulness-and-24h-change.md) — venue-published previous-day derivation, the structurally capped Tier A counter, and honest probe defaults.

## Current state

- [Roadmap state and plan — 8 September 2026](ROADMAP_STATE_2026-09-08.md) — decisions taken, the first measured track record, and outstanding work in priority order.

## Planning

- [Implementation sequence](IMPLEMENTATION_SEQUENCE.md) — every outstanding item with its slot, precondition, and the reason it sits there. Includes health-state ageing, Strike Zone, agent harnesses, ChaseOS Gate and Pine Script.

## Recent change records

- [Market Canvas drawings](changes/2026-09-08_canvas_drawings.md) — versioned operator levels that supersede rather than overwrite.
- [Coinbase spot premium](changes/2026-09-08_spot_premium_context.md) — a third directional candidate, deliberately context-only until you admit it.
- [Regime-split skill gate](changes/2026-09-08_regime-split-skill-gate.md) — the pooled figure was a Simpson's-paradox artefact; no skill demonstrated in either regime.

- [Fixed-window replay](changes/2026-09-08_fixed-window-replay.md) — champion/challenger on frozen evidence, and why weight tuning cannot fix the signal.
- [State ageing and quarantine](changes/2026-09-08_state-ageing-and-quarantine.md) — how long each stage has held its state, and the Tier B admission boundary.

## Architecture diagrams

Visual walkthrough of the whole system, verified against the running stack.

- [System map](architecture/SYSTEM_MAP.md) — start here. Service topology, ports, capability tiers, Cockpit routes, runtime profiles.
- [Paper signal dataflow](architecture/PAPER_SIGNAL_DATAFLOW.md) — observation to opportunity, the producer cycle, admission gates, replay safety.
- [Feature and regime mathematics](architecture/FEATURE_AND_REGIME_MATH.md) — feature lifecycle, the five blocks, the 0.55 coverage ceiling, a worked score.
- [Failure modes](architecture/FAILURE_MODES.md) — how this system actually broke, drawn out, with a checklist.
- [Webhook ingress security](architecture/WEBHOOK_INGRESS_SECURITY.md) — the risk analysis for exposing an endpoint to TradingView.

## Brand

- [TradeSync identity](brand/TRADE_SYNC_IDENTITY.md)
- [Canonical transparent mark](brand/assets/tradesync-mark.png)

## Current contracts

- [Preview contract](contracts/PREVIEW_CONTRACT.md)
- [Alert event v1](contracts/ALERT_EVENT_V1.md)
- [Knowledge synchronization v1](contracts/KNOWLEDGE_SYNC_V1.md)
- [Risk limits](contracts/RISK_LIMITS.md)
- [Regime weight configuration v1](contracts/REGIME_WEIGHT_CONFIG_V1.md)
- [Market feature v1](contracts/MARKET_FEATURE_V1.md)
- [Regime Lab API](contracts/REGIME_LAB_API.md)
- [Integration Pipeline status v1](contracts/INTEGRATION_PIPELINE_STATUS_V1.md)

## Quant learning

- [Book 1 index](quant-learning/README.md)
- [Mathematical notation](quant-learning/01_NOTATION_AND_MATH_LANGUAGE.md)
- [Normalization and tanh](quant-learning/02_NORMALIZATION_AND_TANH.md)
- [Weights, quality, risk caps, and experiments](quant-learning/03_WEIGHTING_QUALITY_AND_EXPERIMENTS.md)
- [Year 2 module map and practice](quant-learning/04_YEAR2_MODULE_MAP_AND_PRACTICE.md)
- [Build-in-public evidence practice](quant-learning/05_BUILD_IN_PUBLIC_PRACTICE.md)
- [Book 1 handover](quant-learning/BOOK_1_HANDOVER.md)
- [Applied Lab 1 — rolling normalization and outliers](quant-learning/labs/LAB_01_ROLLING_NORMALIZATION.md)
- [Applied Lab 2 — regime weights and coverage](quant-learning/labs/LAB_02_REGIME_WEIGHTS_AND_COVERAGE.md)

## Legacy contracts requiring reconciliation

- [Market contract](contracts/MARKET_CONTRACT.md)
- [Opportunity contract](contracts/OPPORTUNITY_CONTRACT.md)
- [Symbol normalization](contracts/SYMBOL_NORMALIZATION.md)

These files contain useful historical schema detail but still include retired multi-venue fields. Do not use them as a new implementation contract until a Hyperliquid-only version replaces them.

## Providers and operations

- [Market provider matrix](providers/MARKET_PROVIDER_MATRIX.md)
- [Bring your own provider credentials](providers/BRING_YOUR_OWN_CREDENTIALS.md)
- [Third-party notices and provider boundary](../THIRD_PARTY_NOTICES.md)
- [Runbooks](RUNBOOKS.md)
- [Phase 0 resource readiness](PHASE0_RESOURCE_READINESS.md)

## Public research preview

- [19 September 2026 release-readiness record](changes/2026-09-19_public-research-preview-readiness.md)
- [Public-source notice](../PUBLIC_SOURCE_NOTICE.md)
- [Third-party notices and provider boundary](../THIRD_PARTY_NOTICES.md)
- [Security and history-free export procedure](../SECURITY.md)

## Diagrams

Canonical Mermaid sources live in [diagrams/](diagrams/README.md). Existing PlantUML diagrams and exports are retained as historical evidence; a diagram is not current merely because an export exists.

## Historical handovers and phase reports

- [ChaseOS Market Command handover](CHASEOS_MARKET_COMMAND_HANDOVER.md)
- `phase3A_report.md`, `phase3B_report.md`, and `phase3C_report.md`
- `CLAUDE_HANDOFF_PHASE3B.md`

These preserve decisions and evidence. They do not override the current README, roadmap, source, tests, or Hyperliquid-only boundary.
