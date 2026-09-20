# TradeSync public-proof campaign draft

Status: GitHub preview and ChaseInTech case study published; social copy prepared, not published  
Evidence date: 2026-09-19  
Social publication gate: operator review and explicit approval

## Claim boundary

Safe claims:

- TradeSync is a locally verified paper-research workstation.
- The captured run showed 7/7 core stages ready and 10/10 feed heartbeats connected or answering.
- Hyperliquid is the authoritative market-data source in this build.
- Hermes is advisory: it may explain or compare evidence, but it may not score, approve, sign or execute.
- Live execution was disabled and visibly locked.
- The interface exposes optional-connector health separately from the standalone core.

Do not claim:

- continuous 24/7 uptime from a single acceptance snapshot;
- profitability, alpha, win rate or financial performance;
- autonomous trading or live-order safety;
- that the repository is fully open source;
- that third-party market data may be redistributed;
- that Hermes, ChaseOS or any LLM grants trading authority.

## LinkedIn post — architecture-first draft

TradeSync is less interesting to me as a trading dashboard than as a computer-science system: a set of agents, event streams, evidence stores and permission boundaries that must work together without silently becoming one authority.

With TradeSync, the boundary is the product.

I built the current architecture around one rule: observation, normalization, agent commentary, operator decisions and execution authority must remain separate states.

The computer-science work sits in the boundaries between those states:
versioned adapter contracts, low-latency event transport, durable evidence,
read projections, independent health/readiness signals, degraded optional
connectors and fail-closed permission gates. A connector being reachable is a
different fact from its data being fresh, trusted or authorised to cause an
action.

In the latest local paper-mode acceptance run:

- adapters normalize external observations into bounded contracts;
- Redis Streams handles low-latency transport while PostgreSQL remains durable truth;
- the State API projects evidence into a responsive operator cockpit;
- Hermes participates as a read-only research adviser through a quarantined connector;
- the ChaseOS/agent-harness layer can coordinate research continuously without inheriting approval, signing or execution authority.

In the latest local paper-mode acceptance snapshot, all 7 core stages were ready and 10 feed heartbeats were connected or answering. Hermes could explain and compare quarantined evidence, but it could not change a score, approve a trade, sign anything or place an order. The UI exposes gateway health, failures and a human kill switch because “AI connected” must never mean “AI authorised.”

The 24/7 element is the agent-harness workflow: repeated collection, normalization, evidence checks and advisory summaries. It is not a claim of 24/7 uptime, autonomous profitability or unattended trading.

TradeSync remains a research and engineering system. This checkpoint proves local integration, deterministic boundaries and observability—not profitability, uninterrupted uptime or live-execution safety.

#AIEngineering #SoftwareArchitecture #AgenticAI #DistributedSystems #RiskEngineering #BuildInPublic #Python

## X post — architecture-first draft

I built TradeSync as an agent-systems project, not a “magic trading AI.”

Public market observations flow through adapters → normalized contracts → Redis Streams/PostgreSQL → State API → operator cockpit. Hermes can explain quarantined evidence, but it cannot score, approve, sign or execute.

Latest local paper-mode snapshot: 7/7 core stages ready, 10/10 feed heartbeats answering, execution locked.

The engineering question is the interesting part: how do you run a continuous agent harness while keeping evidence, inference and authority as separate states?

Source-available research preview after the public release gate. No profitability or live-trading claim.

## X thread — technical alternative

**1/4** I built TradeSync as an agent-systems and distributed-state project,
not a “magic trading AI.” The hard question is how continuous research can run
without letting inference inherit execution authority.

**2/4** Public observations enter through bounded adapters and versioned
contracts. Redis Streams carries low-latency events; PostgreSQL keeps durable
evidence; the State API exposes a read projection to the operator cockpit.

**3/4** Health, readiness, freshness and authority are separate signals.
Optional connectors may degrade without taking down the standalone core.
Hermes can explain quarantined evidence, but it cannot score, approve, sign or
execute.

**4/4** Latest local paper-mode snapshot: 7/7 core stages ready, 10/10 feed
heartbeats answering, execution locked. That is integration and observability
evidence—not profitability, continuous uptime or live-order safety.

## Short caption

TradeSync now makes its trust boundary visible: live market evidence, paper decisions, advisory agents and execution authority are separate states. Latest local run: 7/7 core stages ready, 10/10 feed heartbeats answering, Hermes advisory, execution locked. Integration proof—not a profitability or live-trading claim.

## 55-second voiceover — architecture-first

TradeSync started as a trading workstation, but the real engineering problem became much more interesting: how do multiple data sources, agents and operator controls work continuously without sharing authority?

Public market observations enter through adapters and normalized contracts. Redis Streams handles low-latency transport, PostgreSQL keeps durable truth, and the State API projects the result into the operator cockpit.

Hermes joins through a quarantined advisory connector. It can explain and compare evidence, but it cannot score, approve, sign or execute. The 24/7 agent harness can keep researching while those permission boundaries remain locked.

The latest local paper-mode snapshot showed all seven core stages ready and ten feed heartbeats connected or answering. That proves local integration and observability. It does not prove profitability, continuous uptime or live-order safety.

That distinction is the architecture: evidence before authority.

## Screen-capture plan

Capture clean local pages only. Before recording, hide notifications and close terminals, wallets, email, Discord and any browser profile containing private tabs.

1. **0-04s — title:** “Evidence before authority” over a clean Mission Control establishing shot.
2. **04-13s — market evidence:** slow crop across thesis, horizon map and live market pulse. Keep the execution-disabled state visible.
3. **13-26s — pipeline:** show the 7/7 core path, feed state and paper/locked badges. Do not linger on provider identifiers beyond the product UI.
4. **26-38s — Hermes boundary:** show only the gateway header, advisory contract and kill switch. Do not capture the job table, local workdirs, prompts or output.
5. **38-47s — operator review:** show opportunities or journal in paper mode; omit wallet addresses and private annotations.
6. **47-55s — close:** return to Mission Control with “Integration verified locally · Execution locked” and the ChaseInTech URL after the website change is actually deployed.

Exports:

- 1080 × 1920, 55 seconds, captions inside a 120 px side-safe zone for LinkedIn/Reels/Shorts.
- 1920 × 1080, 55 seconds, centered 16:9 composition for the project page and YouTube.
- 1200 × 627 still from the Integration Pipeline for link previews.

Audio/edit direction:

- restrained, technical pacing rather than market-hype pacing;
- use the operator's recorded voice or an explicitly approved voice model;
- keep UI sounds subtle; do not use exchange notification sounds that imply order execution;
- captions should highlight `7/7 CORE`, `HERMES: ADVISORY`, and `EXECUTION: LOCKED`.

## Privacy and sanitization checklist

- [x] No `.env`, terminal, key, token, secret, webhook URL or browser developer-tools request headers in the prepared website/video assets.
- [x] No wallet address, account value, private journal entry or identifiable position in the prepared website/video assets.
- [x] No Hermes job table, private workdir, prompt, output, internal hostname or ChaseOS vault path in the prepared website/video assets.
- [x] No provider data exported as a downloadable dataset.
- [x] No claim of 24/7 uptime; the copy describes a workflow design and a dated local snapshot.
- [x] No live-trading or performance language.
- [x] Silent proxy frames reviewed at 100% scale; final audio master still requires a separate review.

## Presence-update checklist

- [x] Canonical social-account register checked: no TradeSync-specific account or profile is currently recorded. Use the verified ChaseInTech channels rather than inventing a dedicated TradeSync identity.
- [x] GitHub README: public-source and redistribution boundary prepared locally.
- [x] ChaseInTech project page: new evidence-led case study prepared locally.
- [x] LinkedIn: post and video copy drafted here.
- [x] GitHub research preview published at <https://github.com/chasedndt/TradeSync-Research-Preview>.
- [x] ChaseInTech case study deployed and read back at <https://chaseintech.com/projects/tradesync/>.
- [ ] LinkedIn posted and permalink recorded.
- [ ] Other profiles updated only after an inventory confirms the account, current copy and edit authority.
