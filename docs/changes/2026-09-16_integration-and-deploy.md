# 2026-09-16 — Four branches merged, two `main.py` files split, and the lot deployed

Integration branch `codex/2026-09-01-dashboard-overhaul`. Paper mode untouched throughout
(`DRY_RUN=true`, `EXECUTION_ENABLED=false`); no key, signer, wallet or execution path changed, and
paper entries stayed paused from before the first merge to after the last deploy.

## What merged

| Commit | Branch | Migration |
|---|---|---|
| `b48abbb` | agent harness kill switch | 034 |
| `ef991be` | security remainder (M3, M4, L1–L7) | — |
| `1547fcf` | operator onboarding | 037 |
| `6253543` | research evidence and PostgreSQL resets | 036 |
| `5e82dd3` | paper trading gaps | none needed |

Each branch's own record carries its detail; this one records the integration, the things that only
appeared once they met, and the deploy.

## What only appeared once the branches met

**The frozen lifecycle digest collided (`f524cfd`).** Research froze trial specification v2 against
the managed-paper lifecycle rules by *version and digest*, precisely so a parameter change could not
quietly alter what an experiment admits. Paper gaps then shipped lifecycle **v3** (a fill-depth
bound and exits that fill in parts). On the merged tree the specification named v3 while carrying
v2's digest, and the two guarding tests contradicted each other. Re-frozen deliberately to the rules
now in force (`a9b3a187…`), with the reason recorded in the code, and the test's hardcoded version
string replaced by the imported constant so the name can never drift from the rules again. No trial
had been registered under v2, so no experiment was disturbed; pinning the specification to dead v2
rules would instead have left it admitting nothing, ever.

**The kill switch met a security test (`54c02e2`).** `test_a_harness_transport_error_names_its_type_but_not_its_text`
asserted a 502 from the harness ask route; the merged tree answered 423, because the new kill
switch's `AskGate` refuses that route before the connector is reached. The test now runs with the
harness explicitly running, matching the pattern the harness branch's own tests use.

**Migration 035 was never written (`eae2b58`).** It was reserved for the paper gaps branch, which
needed no schema change — the kill audit reuses the existing `close` action and part fills live in
JSONB. Rather than renumber 036 and 037, which are named throughout three change records, their
acceptance runs and their deploy steps, 035 is **retired**: `RESERVED_BY_PARALLEL_BRANCHES` is now
`SKIPPED_MIGRATION_NUMBERS = {"035"}` with the reason in the comment. A gap at a skipped number is
allowed; any other gap still fails.

## Two `main.py` files split

Both moves were code **moved unchanged**, verified by dumping the route table from a fresh process
before and after and diffing it.

**market-data (`71a4219`)**: 1,133 lines → 142, across `runtime`, `pollers`, `reference_pollers`,
`enrichment`, `health_routes`, `market_routes` and `chart_routes`. The venue loops and the Tier B
reference loops are separate files because their standing differs. 24 routes before, 24 after.

**state-api (`436e211`, `2a23f0d`, `617c380`)**: 3,441 lines → 2,638, moving the knowledge-graph
projection, the macro and context feeds, the outcome/evidence-timeline/refusal-history routes and
the advisory harness routes into `register(app, state)` modules, plus a shared `json_util`. 164
routes before, 164 after, at every step.

**What deliberately stayed, and why.** The market proxies, quarantine, the knowledge gate, execution
and wallet routes remain in `main.py`. Their tests patch `app.main.state` and `app.main._market_data_get`
*wholesale* — replacing the attribute on `app.main`. A route moved into its own module would hold its
own reference, ignore the patch, and the test would keep passing while testing nothing. Moving them
means rewriting working tests to suit a refactor, which trades a real safety net for a line count.
`main.py` is therefore still above the size rule, deliberately, and the remaining work is a test
change first and a move second.

## Deploy

Applied to the running stack: **state-api**, **discord-reader**, **cockpit-ui** rebuilt and recreated,
then state-api rebuilt again after the split. `schema-init` applied the pending migrations.

- **Migrations**: live was `033`; now `034 036 037` recorded.
- **Networks**: state-api joined `pine-ingress` (172.29.53.2) and `signer` (172.19.0.2) alongside
  `default`, as the security branch intends.
- **Paper invariants, before and after, unchanged**: `entries_paused=true` with its original reason
  ("Initial paper safety review required", 14 September), kill switch inactive, 0 managed positions,
  1 ledger row, 0 kill-switch events.
- **Routes checked live** after the split: every moved route (graph status, macro and context status,
  outcomes summary, refusal history, harness status, evidence timeline) and every retained one
  (health, market status, quarantine, opportunities) answered 200, as did the new surfaces
  (harness gate and control, TradingView setup, paper rules — reporting `managed-paper-lifecycle-v3`).

### Not deployed, deliberately

- **cloudflared stays on `default`.** Moving it to the isolated `pine-ingress` network drops the live
  public webhook while it reconnects and needs one real TradingView alert to re-accept. That
  acceptance is the operator's. state-api is already on `pine-ingress`, so the connector has
  somewhere to land whenever it is run.
- **signer-svc was not rebuilt.** Its `/sign` refuses everything until `SIGNER_CALLER_TOKEN` exists,
  and that secret is the operator's to set. exec-hl-svc stays stopped.
- **The Cloudflare rate-limiting rule (L3)** and **the harness host control task** are operator acts.

## A live fault found and fixed in passing (`df32e5d`)

market-data was pinned at **511.6 MiB of a 512 MiB cap** (99.9%) after 14 hours, CPU 87%, with host
probes timing out at 10 s while Docker still called the container healthy and Coinbase spot reads
failed with empty errors. Zero restarts, never OOM-killed: thrashing against the cap, not crashing.
The cap was sized when the default universe was three symbols; the service now runs **ten**, each
with two depth-book aggregations plus trade and liquidation streams.

Raised to 1 GiB and recreated: memory **69.6 MiB** at start and **96.9 MiB** after 25 minutes — a
warm-up as the books and trade windows fill, not a climb back toward the ceiling — with probes
answering in 3–28 ms. If it ever approaches 500 MiB again, that is a leak the larger cap is masking
and should be investigated as one.

## Verification on the shipped tree

- Python: root **1,139**, state-api **576**, market-data **160**, exec-hl-svc **11**, signer-svc
  **14**; runner exit 0.
- Cockpit: **134 tests, 134 pass, 0 fail**; `npm run build` exit 0.
- Three of the operator's standing requirements are now enforced by Cockpit tests rather than by
  inspection: no field anywhere asks for a seed phrase, private key or passphrase; no rendered string
  uses the retired execution wording; the header reads `running` with **Stop**, and `stopping`,
  `stopped` or `failed` with **Start**.

## Honest notes

- The research merge was committed once with conflict markers still in `tests/test_migrations.py`,
  because the commit ran despite the resolution script failing. Caught by the root suite within the
  minute and amended (`6253543`), which is why that merge commit is an amend.
- Browser QA was not run on this tree: Playwright is not installed here.
- The Hermes gateway has been down since 15 September 17:39 BST and was **not** started; starting it
  resumes automations that post publicly, so it waits for the operator.
