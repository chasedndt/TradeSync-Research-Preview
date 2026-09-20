# Outcome metrics, reconciliation views and audit export — 16 September 2026

Branch `claude/evidence-metrics` in `E:\Projects\TradeSync\evidence-metrics-2026-09-16`, branched from integration
commit `f8bfdd5`. Project-local build record for the Phase 4 measurement and reconciliation work that needs no
operator input.

**Nothing here is deployed.** No container in the running stack was built, started, stopped or restarted. **No
migration was added or applied.** The live database was neither written nor read: every database check ran on a
throwaway PostgreSQL that was rolled back and removed. Paper only: `DRY_RUN` and `EXECUTION_ENABLED` were not
touched, the public paper portfolio was not written, and paper entries stay paused. **Nothing changes scoring**:
no weight, rulebook, champion or threshold moved, and `config/regime/regime-rulebook-v1.json` is unchanged.

## 1. The two missing metrics

Both live in `tradesync_core` with their notation, units and a worked example in the docstring. Neither reads a
market: each is scored from what was stored at the time, so a later observation cannot change an earlier verdict.
Both abstain honestly. A missing input is counted as absent and never scored as a zero, and a cohort that could not
be judged has no rate, not 0%.

### Thesis adherence (`thesis_adherence`, `thesis_adherence_checks`)

Did a managed paper position follow the plan it was opened under? It is scored from the immutable `initial_plan`
and the latest lifecycle state. With `d = +1` long and `-1` short, `m` the entry mid, `p` the entry fill, `h` the half
spread and `b` the style's depth bound in bps, `s` the stop, `g` the target, `x` the expiry, and `p_x`, `t_x`, `r` the
exit's price, time and rule, each check passes, fails or is absent:

| Check | Fails when |
|---|---|
| `entry_in_zone` | `abs(p − m) / m × 10000 > h + b` |
| `stop_respected` | `d × (p_x − s) < 0` and `r` is not `stop` or `trailing_stop` (a gap fill under the stop passes) |
| `target_respected` | `r` is `target` and `d × (p_x − g) < 0` |
| `time_respected` | `t_x > x` and `r` is not `time_expiry` |
| `exit_rule_declared` | `r` is not in the lifecycle's `RULE_ORDER` or `kill_switch` |

`adherence = passes / (passes + fails)`, dimensionless. **Worked example**: a long with `m = 100.00`, `p = 100.02`,
`h = 1.0`, `b = 5.0`, `s = 98.50`, `g = 103.00`, `x = 4600`, closed by `operator_close` at `98.20` at `t = 5000`.
The entry is 2.0 bps against 6.0 allowed (pass), the price is past the stop under a non-stop rule (fail), no target
is claimed (pass), the close is 400 s late (fail), and the rule is declared (pass). That gives `3 / (3 + 2) = 0.6`.
A position opened under lifecycle v2 declares no depth bound, so its entry check abstains rather than being judged
by a rule it never ran under.

### Regime fit (`regime_fit`)

Did a call fire into the regime its rulebook expected? The regime is the frozen `opportunity_entry_regimes` label,
computed only from candles closed before the call and never recomputed. The expectation is read from the rulebook
carrying the digest frozen on the call (`opportunities.confluence.evidence.rulebook_digest`). A rulebook offered
under any other digest is refused, so editing a rulebook cannot restate the verdicts of calls scored under the
version it replaced. `regime_fit_rate = fit / (fit + misfit)`.

A rulebook declares an expectation under an optional key: `"regime_expectation": {"schema":
"regime_expectation_v1", "LONG": [...], "SHORT": [...]}`. A malformed declaration raises rather than reading as
silence. Six verdicts abstain, each counted apart because each has a different remedy: `undeclared`, `unlabelled`,
`digest_mismatch`, `rulebook_altered`, `undirected` and `no_rulebook`. **Worked example**: with `LONG → {rising}`,
calls in rising, falling and unknown regimes, plus one frozen under another digest, give `1 / (1 + 1) = 0.5` with
two abstentions. Counting those as misfits would read 0.25 and would describe gaps in the evidence rather than the
rulebook.

**No rulebook declares an expectation today, so every call abstains as `undeclared`.** That is reported as an
abstention and never as a misfit. A test pins it, so the day a rulebook declares one is noticed. Declaring one
changes the rulebook's digest, which makes it a new rulebook version and an operator decision; nothing here writes
one.

## 2. Reconciliation views (`reconciliation_views`, `reconciliation_view_model`)

These are the five views the roadmap names, built the same way as the existing decisions-against-orders
`reconciliation`: each reads two of this system's records, reports where they disagree, and guesses nothing.

| View | Compares | Findings |
|---|---|---|
| `orphaned_events` | events against the `event_ids` every signal recorded | `orphaned_event` |
| `duplicate_candidates` | opportunities by evidence digest, then by market, timeframe and side | `duplicate_evidence_digest` (certain), `repeated_call` within 60 s (a candidate) |
| `stale_approvals` | control envelopes against their consumption | `stale_approval` past 4 h, `approval_without_a_time` |
| `partial_orders` | orders against their own status and fill | `order_not_terminal` past 300 s, `partial_fill` short by more than 0.01 USD |
| `missing_outcomes` | opportunities against outcome rows per horizon (15, 60, 240 min) | `missing_outcome`, `outcome_still_pending`, `opportunity_without_a_time` |

Every view states what it compared and over what window. A counterpart that merely predates the window goes to
`outside_window` and is never a finding. A view that examined no record says "nothing to compare", so an empty order
table (the live state: no order has ever been placed) cannot read as a clean reconciliation.

`GET /state/reconciliation/views?hours=` (1–720) serves all five, with the exact `generated_at` and the window's
`from` and `to`. Each read is capped at 5,000 rows.

## 3. Audit export (`audit_export`)

- `GET /state/audit/export?days=&rows=` returns every section as JSON: decisions, approvals, orders and outcomes.
- `GET /state/audit/export.csv?section=&days=&rows=` returns one section as CSV.
- **Bounds**: at most 5,000 rows a section and a 31-day window, both stated in the JSON. The CSV carries its generated
  time, window, row count, cap, truncation, redaction count and content digest in `X-Export-*` response headers. A
  section reads one row past its cap, so it can say `truncated` honestly.
- **Checkable**: rows carry the digests already stored beside them (`approval_digest`, `candidate_hash`, the
  opportunity's `evidence_digest`). `content_digest` is over the sections only, not `generated_at`, so the same rows
  give the same digest whenever the export is taken.
- **No secret**: each section exports only its declared columns, so a column added to a table later cannot export
  itself. Every free-form payload is then scrubbed by key: a field under a secret-looking key becomes `[redacted]`
  and is counted. The tests assert that the secret *values* are absent from both the JSON and the CSV.
- **Access**: like every GET, the export is not behind the operator token. `AccessGuard` guards changes only, and
  the port is loopback-bound. It carries no secret by construction, but anything that can reach state-api can read it.

## 4. Metric routes and the bounded read path

`GET /state/outcomes/thesis-adherence?limit=` and `GET /state/outcomes/regime-fit?hours=&limit=` serve per-position
and per-call results with a summary and exact times. All 13 new reads (six reconciliation, four export, three metric)
go through `heavy_query`, with parallel workers off, a server-side statement timeout, and duration and failures
recorded under a name.

**`main.py`**: the only change is three `register(...)` calls appended at its tail (19 lines added, none removed or
moved), per the coordination rule for the three parallel branches.

## 5. Cockpit

The **Reconciliation and audit** panel sits on the Signal Ledger, directly under Paper risk and its restart
reconciliation (`components/ledger/reconciliation/`, a CSS module per component):

- **Execution reconciliation card**: the existing decisions-against-orders reconciliation, which had no Cockpit surface
  before, shown as a card beside the five views.
- **The five views**: each card shows what it compared, its window in UTC, its record count, its summary and every
  finding. A view that examined nothing reads **Nothing compared**, not Clean. The older route answers `clean: true`
  over zero decisions and zero orders. It also reports no time of its own, so its card states when the Cockpit
  received it.
- **Metric cards**: thesis adherence and regime fit, with a missing measure as a dash (never 0%), departures written
  as what went wrong, and abstentions counted by reason.
- **Audit export**: JSON and per-section CSV links over 1–31 days.
- **Readings**: every reading shows its exact UTC time and has a Refresh button. They refresh every five minutes,
  never faster, because each one scans a table on a database with a history of crash resets.

## 6. Size limits, migrations and wording

- **Splits**: three files went over ~300 lines and were split in move-only commits. Every top-level definition was
  compared with the previous commit by source text and found byte-for-byte identical:
  - `thesis_adherence` (325 lines, split to 189 + 164);
  - `reconciliation_views` (320 lines, split to 263 + 70);
  - `tools/qa_outcome_metrics_sql.py` (306 lines, split to 235 + 90).
- **Migrations**: none. `SKIPPED_MIGRATION_NUMBERS` is now `{035, 038, 039, 040}`: 038 and 040 are reserved by the
  parallel branches. **039** is included too, because this branch did not need it, and once 040 lands an unused 039
  would otherwise fail the contiguity check.
- **Wording**: `tests/test_outcome_reporting_wording.py` holds every finding, verdict and note the panel prints
  verbatim to the retired-wording rule, imported from `test_ui_wording.py` rather than copied.

## Verification

### Unit suites

`tools/run_tests.py` exited 0 on the final code tree. It ran with the project venv at
`E:\Projects\TradeSync\dashboard-overhaul-2026-09-01\.venv`, since this worktree has none of its own.

| Suite | Result | At `f8bfdd5` |
|---|---|---|
| root | **1214 passed**, 17 deselected, 2 warnings, 49 subtests | 1139 |
| state-api | **611 passed** | 576 |
| market-data | 160 passed | 160 |
| exec-hl-svc | 11 passed | 11 |
| signer-svc | 14 passed | 14 |

- **Root, +75**: `test_thesis_adherence` 18, `test_regime_fit` 15, `test_reconciliation_views` 23, `test_audit_export`
  15, `test_outcome_reporting_wording` 4.
- **State-api, +35**: `test_reconciliation_routes`, `test_audit_export_routes` and `test_outcome_metrics`, over a
  shared fake connection (`audit_fakes`) that asserts every read took the bounded path.

Cockpit, `services/cockpit-ui`, on the final tree:
- `npm test`: **146 passed, 0 failed**, exit 0. The 11 new tests are `tests/reconciliation-format.test.mjs`, the only
  test file changed since `f8bfdd5`, which puts the base at 135. The integration record gives 134 for its tree.
- `npm run build`: **passed**, exit 0, in 23.06 s.

### Isolated PostgreSQL acceptance: 26 of 26 checks, run twice

`tools/qa_outcome_metrics_sql.py` (seed rows in `qa_outcome_metrics_seed.py`) ran against PostgreSQL 16.15 in a
throwaway `postgres:16` container on `127.0.0.1:55462` (confirmed with `docker port`), database `tradesync_qa`.
The schema was loaded by `ops/apply_schema.py` (migrations 001–034, 036, 037). Everything ran in one transaction
that was rolled back, and the container was removed. The script refuses port 5432 and a database named `tradesync`,
and can only make in-process requests. It passed before the tool was split and again, on a fresh container, after.

The checks cover the following, through the real route modules and real tables:
- every view finds its seeded divergence and nothing it should not, with horizons not yet due never reported;
- fit, misfit, `undeclared` and `no_rulebook` verdicts, and a rate of 0.5;
- the repository's own rulebook still hashes to its stored digest after a JSONB round trip;
- the adherence worked example reads 0.6 from stored JSONB, and an open position abstains on four checks;
- no secret from real JSONB reached the JSON or the CSV, and both redactions were counted;
- exported approval digests, candidate hashes and evidence digests match the rows they came from;
- the content digest is stable across two readings, and a capped section says truncated;
- **no route wrote**: this transaction's insert, update and delete counters stayed at 20 across every reading;
- `SHOW` in the server gave `max_parallel_workers_per_gather = 0` and `statement_timeout = 30s`, with all 13 named
  reads recorded and none failed;
- a newer rulebook expecting the opposite regimes changed neither earlier verdict;
- a stored rulebook rewritten in place was refused as `rulebook_altered`;
- the database's own trigger refused a rewrite of the plan adherence reads.

## Findings worth the operator's attention

- **Live regime fit will abstain on every call** until a rulebook declares a `regime_expectation`. That is the
  operator's rulebook decision, not a fault.
- **Thesis adherence has nothing to score live yet**: the 16 September deploy record shows 0 managed positions, and
  entries are paused.
- **The frozen managed-paper entry evidence records `rulebook_version` but not `rulebook_digest`**
  (`paper_entry_rows.scorer_verdict`). Regime fit therefore reads the digest from the opportunity's own
  `confluence`, which is written once and never rewritten. Carrying the digest into the entry evidence would be a
  schema v3 of that document, so it was left alone.
- **`/state/execution/reconciliation` answers `clean: true` over nothing compared.** The route was not changed, under
  the `main.py` rule; the Cockpit card reads it honestly. The lead's `main.py` split is a natural moment to align it.
- **`docs/AGENT_INTERFACE.md`** describes a `debug.regime_fit ∈ {trend, range, high_vol, low_vol}` agent field that was
  never implemented. The implemented entry-regime vocabulary, and the one this metric uses, is rising, falling, flat
  and unknown.

## What remains

- **Browser QA not run**: Playwright is not installed here. The panel was checked by `tsc`, the Vite build, the node
  tests and the wording guards, not at 1366 or 375 CSS pixels.
- **Not deployed**, and not read back against the live stack.

## Deploy steps for the lead

Nothing below has been done. Paper only; the public entry pause stays on.

1. **Merge** `claude/evidence-metrics`. `main.py` conflicts, if any, are confined to its tail, and there is **no
   migration and no schema step**.
2. **Test the merged tree**: `.venv\Scripts\python.exe tools\run_tests.py`, then `npm test` and `npm run build` in
   `services/cockpit-ui`.
3. **Rebuild and replace state-api and cockpit-ui**, as in the [paper gaps record](2026-09-15_paper-gaps.md).
4. **Read back** (read-only):
   - `GET /state/reconciliation/views?hours=24` returns five views, each with its window;
   - `GET /state/outcomes/regime-fit` shows every call `undeclared`;
   - `GET /state/outcomes/thesis-adherence` returns an empty portfolio with a `null` mean;
   - `GET /state/audit/export.csv?section=orders` returns only the header row, with `X-Export-Row-Count: 0`.
5. **Optionally re-run the acceptance** against the merged checkout with the commands in the tool's docstring, on a
   throwaway container on its own port.
6. **Rollback**: redeploy the previous state-api and cockpit-ui images. Nothing was written and no schema changed.

[Paper gaps](2026-09-15_paper-gaps.md) · [16 September integration](2026-09-16_integration-and-deploy.md) ·
[Documentation index](../README.md)
