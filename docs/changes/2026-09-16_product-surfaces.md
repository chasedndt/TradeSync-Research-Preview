# 2026-09-16 — Product surfaces: the operator menu, Settings, the regime summary, liquidations by source, and opportunity briefs

Branch `claude/product-surfaces` from `f8bfdd5`. **Not deployed.** **No migration**: nothing here needed a
schema change, so migration 040 was not used and `SKIPPED_MIGRATION_NUMBERS` is untouched. Paper mode
untouched (`DRY_RUN=true`, `EXECUTION_ENABLED=false`); no key, signer, wallet or execution path changed;
paper entries stay paused, and every route added here is read-only. `main.py` gained only three
`register(...)` calls at its tail, and `api/types.ts` was not edited: new types sit beside it.

This closes the roadmap's product-surface backlog items that needed no operator input: the operator
profile, Settings, the regime summary, liquidations and opportunities. Regime Lab was already served
through the API, and Activity & Evidence is not part of this branch.

## Commits

| Commit | What |
|---|---|
| `b4a1efa` | The regime summary shows its evidence, and never a bare unknown |
| `c59f11e` | Four liquidation sources told apart, with a side only where the source supports one |
| `8ddff41` | The Market page shows liquidations by source instead of one mixed card |
| `4247dde` | What the operator menu may honestly say, with no sign-in implied |
| `92a2110` | The Market page split into one module per panel, moved unchanged |
| `a018c3a` | Opportunity briefs in the state API, every field read from stored records |
| `3909c0c` | Opportunities read their stored brief, and the fabricated fields are gone |
| `0cb78d6` | Retention policy for Settings, read from the code that deletes |
| `a88f827` | An operator menu that identifies the runtime and says there is no sign-in |
| `c197250` | Settings shows the operator's real settings instead of generic browser fields |

## Regime summary (Market page)

The page rendered the classifier's four labels and a confidence word with none of the evidence behind
them, and a bare `UNKNOWN` read as "this market is unknowable" when it almost always meant one input did
not arrive.

`GET /state/market/regime-summary?symbol=` (`app/regime_summary_routes.py`) reads the market-data snapshot
and the regime labels stored against that market's opportunities (`opportunity_entry_regimes`), and
`tradesync_core.regime_summary` turns them into: the condition with a readable label; confidence with the
count of usable required inputs; each input (funding, open interest, volume) with its status, source, exact
read time and age; readings that disagree, in plain words; every reason confidence is not higher; the
recorded regime now in force and each transition, dated to the first reading that carried the new label.

**The guarantee:** whenever the condition is unknown, `missing_inputs` names every input that could not be
used and `why_not_higher` is non-empty. A test holds that over each way unknown arises: nothing read, one
input missing, and a combination no condition rule matches. A market-data outage answers 200 with every
input named unread, because "the source did not answer" is the explanation the panel exists to show.

## Liquidations (Market page)

One "Liquidations" card held four different things, and the weakest looked most like fact: the legacy
proxy estimates a total from a fall in open interest and splits it fifty-fifty, and the card drew the
halves as a long figure beside a short figure. The feature catalog already calls that split "not observed
market truth".

`components/market/liquidations/liquidationSources.ts` classifies each source once, and whether a side may
be shown is a property of the source, enforced by `sideWords`, which refuses a side for any other source:

| Source | Data | Side shown | Why |
|---|---|---|---|
| Liquidations received | `market_liquidation_events` (Bybit, Binance) and the hour attached to the snapshot | Yes | Each event names the side the venue closed |
| Hyperliquid mechanics | What the venue does and does not publish | No | Hyperliquid publishes no market-wide liquidation feed |
| Inferred pressure | The snapshot's `derived.liquidation_map` | No | Where estimated levels sit, not that anyone was liquidated |
| Legacy proxy estimate | The snapshot's `liquidations` block | No | A total only; the split is an assumption |

The snapshot's `derived` context (resting liquidity, the hour of received liquidations, the liquidation map)
was always served but never declared; it is typed in `api/liquidationSourceTypes.ts`.

## Opportunities (list and detail)

The pages computed a "strength" percentage in the browser with `tanh`, printed a hard-coded "Risk
confidence: VERIFIED", described "multi-venue confluence" on a single-venue system, and drew a trade plan
of dashes. All four are removed (`utils/metrics.ts`, `OpportunityHeader`, `TradeSummary`,
`TradePlanSkeleton`).

`GET /state/opportunity-briefs` (compact, by status) and `GET /state/opportunity-briefs/{id}` (full), in
`app/opportunity_brief_routes.py`, read the opportunity with its stored decision, its entry regime, the
managed paper position opened from it and the outcome job's entry reference price, and
`tradesync_core.opportunity_brief` states:

- **symbol, timeframe, side, status, opening and expiry times, and age** at the time of reading;
- **regime fit**: the side against the regime recorded before entry (with, against, flat, or unlabelled
  with the reason), described and never forecast;
- **entry conditions**: evidence coverage, directional coverage, the directional score against the entry
  threshold (or the hold threshold for a side already held) and the oldest reading against the age bound,
  each with the stored value, the value needed and whether it was met. These restate the paper-signal gate's
  comparisons on the stored values, and tests build decisions with the gate itself to hold them to agreement:
  an admitted decision meets all four, and each refused decision shows the condition that refused it;
- **invalidation, stop, target, expiry, estimated risk and reward, and net reward-to-risk** from the plan
  frozen when a paper position opened. The ratio is the one the entry gate admitted, restated on the stored
  totals. With no position there are no levels, and the brief says so and shows the rules a plan would be
  set under instead of inventing levels from a price never filled;
- **evidence and provenance**: contributing features, missing blocks, risk caps, signal id, evidence digest,
  rulebook and catalog versions and digests, the entry evidence fingerprint and the entry reference price;
- **paper state**: position open or closed, research only with the entry refusal, entries paused, or
  unknown when the pause cannot be read. The pause is read, never changed.

The detail page still shows the stored record, outcomes, evidence trail and preview controls if the brief
cannot be read, so the Cockpit does not depend on the state API being deployed first.

## Settings

Settings led with a browser-local API URL field and a "Danger Zone", and described a client-side
"authority level" that does not exist. It is regrouped by what each setting governs; every reading shows
its exact time and has a refresh control.

| Section | Shows | From |
|---|---|---|
| Operator and access | Token policy and guidance (existing), now with its reading time | `GET /state/access-policy` |
| Data connections and connector health | State API address and database health; each pipeline stage's measured status; the feed heartbeats panel, embedded rather than rebuilt; the loopback address override, kept in a disclosure | `/state/health`, `/state/integration-pipeline` |
| Notification devices and quiet hours | The existing phone setup, unchanged | mobile alerts routes |
| Execution mode and wallet | Execution gate, entry pause and what blocks entries, kill switch, executor; signer reachability; WalletConnect pairing; that no watched address is kept | `/state/execution/status`, `/state/paper-risk`, `/state/execution/signer-status`, `/state/settings/walletconnect` |
| Risk policy | Paper limits in force with who changed them and why; the versioned lifecycle rules | `/state/paper-limits`, `/state/paper-positions/rules` |
| Display and time | Which times are UTC, this browser's timezone, that quiet hours belong to each phone. No display preference is offered, because none exists | the browser |
| Retention, exports and diagnostics | Retention windows; audit records as read-only JSON; failing Cockpit readings, state API health, feeds with errors, and clearing cached previews | `GET /state/operator/retention` and the audited routes |

`GET /state/operator/retention` reads every window from the constant the deleting code uses
(`tradesync_core.market_history`, `tradesync_core.retention`, and the `keep_days` defaults of the paper
store functions). "Every other table is kept" is stated only because `tests/test_retention_policy.py` scans
the service code for deletions and fails on any table the policy neither declares nor explains.

Secrets stay server-side: the page says so, no new field asks for one, and the session-only operator token
and mobile key entries keep their existing behaviour.

## Operator profile (header)

The header's "More options" button did nothing. It is replaced by the operator menu, which opens with the
statement that TradeSync has **no sign-in and no session**, that nobody is authenticated, and that the
operator name is attribution rather than a credential. Each line comes from a real endpoint:

- **operator and runtime**: who changes are attributed to, the state API address and its health;
- **trust**: change authority exactly as state-api enforces it, with no tier invented beyond the policy;
- **mode**: the execution gate and whether paper entries are admitted;
- **approval inbox**: connector submissions held for review, counted from `/state/quarantine`, "at least"
  when the listing is cut at its limit, and never called approvals;
- **device sessions**: enrolled phones (or that listing them needs the mobile control key) and which
  credentials this browser session holds;
- **audit exports**: each audited record's Cockpit page and its read-only JSON record;
- **lock**: forgetting the credentials this browser holds, offered only while one is held. There is no
  sign-out, because nobody signed in.

## Market page split

`pages/Market.tsx` was 691 lines with a 289-line page component. Every panel moved to
`components/market/snapshot/` unchanged, scripted from asserted line boundaries; the page is now 93 lines.
The only edit besides re-indentation turns one leading JSX comment into a plain comment.

## Rules held

- **No mathematics in TypeScript.** Every level, ratio, threshold comparison and confidence figure is
  calculated in `tradesync_core` and read through the API; the brief wording test fails on `Math.tanh`,
  `log`, `sqrt`, `exp`, `pow`, `abs`, `max` or `min` in its module.
- **Wording.** The Cockpit's retired-wording test passes, and the new Python notes the Cockpit renders were
  scanned for the same words.
- **Exact times and refresh controls** on every new reading.
- **File sizes.** The largest new component is 121 lines; CSS modules per component family, no utility
  classes added.

## Verification

- `npm test` (services/cockpit-ui): **177 passed, 0 failed** (135 at the branch point).
- `npm run build`: clean. `tsc --noEmit`: clean.
- `.venv\Scripts\python.exe tools\run_tests.py`: **runner exit code 0**, read from the runner itself.
  root **1177 passed** (17 deselected, 62 subtests; 1139 at the branch point), state-api **588 passed**
  (576), market-data 160, exec-hl-svc 11, signer-svc 14 (all three unchanged). The new tests account exactly
  for the difference: root +38 (regime summary 15, opportunity brief 19, retention policy 4) and state-api
  +12 (regime summary route 4, brief routes 7, retention route 1).
- No browser QA: Playwright is not installed here. Components were verified by tests, type-checking, the
  build, and reading their render logic.
- Nothing deployed, and no live database was queried.

## Not done here, and what needs the operator

- **Deploy** (the lead): rebuild `state-api` and `cockpit-ui`. No migration is needed.
- The header's "System time synced" is static text with no measurement behind it. It is outside this
  brief and was left as it is.
- Some older panels (received liquidations, feed heartbeats) still show local time; Display and time says so.
- The regime transition history comes only from opportunities' entry regimes, so a market with no scored
  opportunity has none to show, and the panel says so.
- The refusal retention window can be overridden in core-scorer, which the state API cannot see; Settings
  shows the declared default and names the override.
