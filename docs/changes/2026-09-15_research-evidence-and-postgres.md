# Research evidence closed, and the PostgreSQL crash resets investigated — 15/16 September 2026

Branch `claude/research-evidence` in `E:\Projects\TradeSync\research-evidence-2026-09-15`, from
`codex/2026-09-01-dashboard-overhaul` at `566fea9`. Project-local build record.

**Nothing here is deployed.** No container was built, started, stopped or restarted; no migration
was applied; no live setting, index or row was changed. Live data was read only: GETs, read-only
psql, `docker logs` and `docker inspect`. Paper only, shadow only: no scoring, rulebook, catalog
weight or promotion changed, and no trial was registered.

## What changed

### 1. Research trial specification v2

v1 (`tradesync_core/research_trial.py`) is untouched, and `tests/test_research_trial_v2.py` pins
all three of its fingerprints (`106f31ca…`, `c53b3f0f…`, `401c1b59…`) so any edit fails a test
rather than silently invalidating a registration. It is also no longer a description of anything
that exists: it names BTC, ETH and SOL and "scenario funding", while a managed paper position opens
over whatever markets the API reports and settles Hyperliquid's own hourly funding.

`research_trial_v2.py` freezes, at registration:

- **the universe as the API reported it** (`editions.tracked_symbols`), never a list in code. A
  universe that cannot be read registers nothing at all;
- **the lifecycle rules** a position must have opened under, by version *and* by the SHA-256 of
  every parameter in them (`managed-paper-lifecycle-v2`, `d845a0e5…`; re-frozen on 16 September 2026 to the rules then in force, `managed-paper-lifecycle-v3`, when part fills and the depth bound merged — before any trial was registered), with a test that fails if the
  rules change without a new version;
- **the entry-evidence schema** and the pre-declared context family, by version and digest;
- **settled funding**: a closed position with an unsettled hour stays pending for a day and is then
  excluded and counted, never measured with an hour missing. It also verifies each position's stored
  evidence digest before admitting it.

`research_trials.py` dispatches a stored specification to the evaluator of its own version. New
registrations are v2 only: freezing v1 means never editing it, not going on registering a protocol
whose own text is wrong for every position it could now admit. The refusal says so.

Registration, evaluation and the Cockpit all carry the version; the panel also shows the universe
frozen with each trial.

### 2. The comparisons over the evidence frozen at entry

Six readings, in both polarities, at three horizons: 36 cells declared in
`entry_evidence_family.py` with a digest over the declaration, before any of them was measured.
`entry_evidence_context.py` computes each from plain inputs, so one definition serves a frozen
document and a reading reconstructed from recorded history. `ablation_evidence.py` assesses them.

The method, the population and the live result are in
[the research record](../research/2026-09-16_entry-evidence-comparisons.md). The two points that
matter most here:

- **the paired difference per original opportunity cannot show selection.** After costs the
  signal's mean is negative, so any filter that skips enough trades raises it for that reason alone.
  The tested quantity is the **contrast** between kept and skipped trades, with a block-bootstrap
  error, non-overlapping window counts with symbols pooled, a chronological hold-out, the
  repository's 0.12% round trip and Holm across the whole family;
- **there are no managed paper positions**, so there is no frozen document to read. The population
  is the recorded calls, with evidence reconstructed as of each call's own entry time under the same
  predicates a live entry uses. The timeframe measurement and settled funding rows cannot be
  reconstructed honestly and are absent rather than approximated; the response says which.

`GET /state/research/entry-evidence-comparison`, served from the statistics cache and measured in a
worker thread, with a Cockpit panel on the Signal Ledger.

### 3. The reads that scan whole tables

`app/heavy_query.py` runs them with parallelism off, a server-side statement timeout, a client
timeout five seconds longer so the server's limit fires first, and the duration recorded per read
and reported on `/state/learning/status`. The attribution, candidate, walk-forward and
evidence-combination reads use it.

`learning_store.attributions_since` now selects only the nine columns the aggregations read, and
orders in memory instead of asking PostgreSQL for a sort that did not fit in `work_mem`.

`ops/migrations/036_attribution_range_index.sql` (**proposed, not applied**) covers that range scan.

## The PostgreSQL crash resets

### What was asked, and what can still be answered

The postmaster reset itself in place four times on 13 September (09:52, 14:19, 15:06, 15:08 UTC) and
once on 15 September at 11:26:56 UTC: a backend exited with code 2, every other process was
terminated, and recovery took a few seconds.

**The logs of all five are gone.** The Postgres container was recreated at 17:00:13 UTC on
15 September for the loopback-port change, and `docker logs` begins there; `logging_collector` is
`off`, so PostgreSQL kept no copy inside the volume. Nothing on this machine holds the DETAIL line
naming the statement each crashed backend was running, which is the single line that would have
identified it. That is stated rather than worked around: the per-reset log context the brief asks
for no longer exists.

### What the current instance shows (read-only)

- Up since 2026-09-15 17:00:13 UTC with **no reset since**; `RestartCount` 0, `OOMKilled` false.
- cgroup `memory.events`: `oom 0`, `oom_kill 0`; peak 170 MB against the 768 MiB limit.
- `cpu.max` 50000/100000 — half a core — with 1,104 of 10,099 periods throttled (63.8 s).
- `/dev/shm` 64 MB, 1.1 MB used. PostgreSQL 16.15 (Debian), image built 2026-08-25.
- `pg_stat_database`: 9,202 sessions, 63 abandoned, 3 killed, 0 fatal; 19 temporary files, 106 MB.

### The query, and what it was really doing

`opportunity_attributions` holds 11,251 rows in 25 MB, averaging 1,746 bytes because every row
carries two JSONB documents (~574 and ~618 bytes) that no aggregation reads. **Every row is inside
the 14-day window**, so the cancelled query's range was the whole table. Its live plan:

```
Gather Merge  (cost=9110.86..10375.14 rows=10836 width=1695)
  Workers Planned: 2
  ->  Sort  Sort Key: opened_at, opportunity_id, horizon_minutes
        ->  Parallel Seq Scan on opportunity_attributions
```

The `($2::int IS NULL OR horizon_minutes = $2)` form also prevents the horizon index being used, so
the one-horizon variant scans the table too.

On a **throwaway `postgres:16`** with the same settings and limits and a table of the same shape
(11,253 rows), `EXPLAIN (ANALYZE, BUFFERS)`:

| Query | Plan | Temporary files | Time |
|---|---|---|---|
| `select *` + `order by` | Gather Merge, 2 workers | external merge sort, **8.8 MB + 7.7 MB to disk** | 349 ms; 0.9–1.3 s wall clock |
| the same, parallelism off | single sort | external merge, 16.5 MB | 212 ms |
| only the columns read | sequential scan | **none** | **4.4 ms** |
| the same, covering index | index-only scan, 0 heap fetches, 132 buffers | none | **2.7 ms** (index 1,056 kB) |

So on an idle server the old query took about a second; on this container, at half a CPU while
serving everything else, the pool's 5 s `command_timeout` was reachable, and that cancel is exactly
what the log recorded before each reset.

### Does a cancelled parallel query cause the reset? No

Measured on the same throwaway server:

- **fifteen heavy parallel scans cancelled mid-flight** produced `canceling statement due to user
  request` from leader and worker and a parallel worker exiting with code 1 — and **the server
  stayed up**. Cancelling a parallel query does not crash a stock 16.15.
- **one `kill -QUIT` to a single ordinary backend** reproduced the operator's signature exactly:

  ```
  LOG:  server process (PID 242) exited with exit code 2
  LOG:  terminating any other active server processes
  LOG:  all server processes terminated; reinitializing
  LOG:  database system was interrupted; last known up at ...
  ```

Exit code 2 is the crash-exit path a backend takes on SIGQUIT, not the code a cancelled or
terminated backend returns (those exit 1).

### Verdict: the cause is not established

Ruled out by evidence: an out-of-memory kill (that is signal 9, not exit code 2; `oom_kill` is 0 and
the container never restarted), `/dev/shm` exhaustion, and the cancellation itself. What remains is
a backend that took the crash-exit path — something signalling it, or a fault whose DETAIL line is
lost. With `log_connections` off, even the surviving log could not have named the client.

What was done about it anyway, because the exposure was real and worth removing:

- the reads that were being cancelled no longer spill 19 MB to disk, no longer launch workers on a
  half-CPU container, and are no longer cancelled at five seconds;
- their durations are visible on `/state/learning/status`, so a read that begins to time out no
  longer looks like a read that is merely slow;
- `tools/postgres_reset_evidence.py` captures a reset's evidence **before** a recreate discards it.

For the operator to decide, not done here (they are live configuration changes): `log_connections`,
`log_disconnections` and `log_min_duration_statement` would name the next reset's backend and its
statement, and a larger `max-size`/`max-file` on the container's log driver would keep more history.

### The other heavy scans, as asked

- **Evidence combination**: hash join, 4,466 rows at width 61, a sort that fits in `work_mem`. Routed
  through the bounded read anyway: same table, same exposure, and it grows.
- **Skill gate**: hash left join over two sequential scans, 10,816 rows at width 49. No sort, no
  workers. Unchanged.
- **Evidence cards**: hash join, 51,614 rows at width 57. No sort, no workers. Unchanged.
- **Source cards**: 99 rows. Unchanged.

## Verification

Project venv, `tools/run_tests.py`, on the committed branch:

| Suite | At `566fea9` | Now |
|---|---|---|
| root | 1,019 | **1,057** (+38) |
| state-api | 401 | **423** (+22) |
| market-data | 160 | 160 |
| exec-hl-svc / signer-svc | 3 / 10 | 3 / 10 |

New root tests: `test_multiple_testing` (5), `test_entry_evidence_context` (6),
`test_entry_evidence_family` (6), `test_ablation_evidence` (9), `test_research_trial_v2` (12). New
state-api tests: `test_heavy_query` (8), `test_research_trials_routes` (8),
`test_entry_evidence_comparison` (6).

Cockpit, `services/cockpit-ui`: `npm test` **105 passed** (97 before, plus 8 new format tests,
including the retired-wording scan over every rendered string); `npm run build` (`tsc` and Vite)
**passed in 18.57 s**, with the existing warnings only. Browser QA not run: Playwright is not
installed in this environment.

**Live read-only acceptance** (`tools/run_in_state_api.py tools/qa_entry_evidence_comparison.py`,
16 September): 4,451 measured calls over 1,509 opportunities and ten markets; 18 of 36 cells
testable; **no cell selects** against a first-ranked Holm bar of 0.00139; the strongest cell is
funding received, as read, at 15 minutes (contrast +15.2 bps, z +1.45). Every 240-minute cell has
too few independent windows. The bounded reads took 0.075 s, 0.010 s, 2.739 s and 0.001 s.

Afterwards, read-only: migration 036 is not applied and `idx_attributions_opened_cover` does not
exist; `research_trials` and `managed_paper_positions` are both empty; no `qa_%` schema; no
transaction open for more than a minute; the postmaster has not restarted since 17:00:13 UTC.

## Deploy steps for the lead

Nothing below has been done.

1. **Merge `claude/research-evidence`.** Empty `RESERVED_BY_PARALLEL_BRANCHES` in
   `tests/test_migrations.py` once 034 and 035 are in (034 is already on the integration branch).
2. **Test the merged tree**: `.venv\Scripts\python.exe tools\run_tests.py`, then in
   `services/cockpit-ui` `npm test` and `npm run build`.
3. **Apply migration 036 and replace state-api** (schema-init runs pending migrations first):

   ```powershell
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml build state-api
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml up -d state-api
   ```

4. **Replace cockpit-ui** from the tested build (low-memory path):

   ```powershell
   docker build -f ops/cockpit-prebuilt.Dockerfile -t tradesync/cockpit-ui:dev services/cockpit-ui
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml up -d --no-deps cockpit-ui
   ```

5. **Read back** (read-only):
   - `SELECT version FROM schema_migrations WHERE version = '036'` returns one row, and
     `to_regclass('idx_attributions_opened_cover')` is not null;
   - `GET /state/research/entry-evidence-comparison` answers 202 `computing`, then 200 with
     `schema_version: entry-evidence-ablation-v1` and `promotion_allowed: false`;
   - `GET /state/research-trials` shows `registerable_version: research-trial-v2` and an empty list;
   - `GET /state/learning/status` shows `heavy_reads` with durations and no failures;
   - Signal Ledger shows the comparison panel and the trials panel naming the version.
6. **Rollback**: revert the merge and rebuild the two services. Migration 036 can stay — the old code
   never uses the index — or be dropped with the migration's DOWN section.
7. **Operator's decision, separately**: turn on `log_connections`, `log_disconnections` and
   `log_min_duration_statement`, and raise the container log retention, so the next reset can be
   attributed. Registering a v2 trial is also the operator's decision; none exists.

## What remains open

- **The cause of the resets.** Not established, and not establishable from what survives. The next
  one can be, if the logging above is on and `tools/postgres_reset_evidence.py` is run before
  anything is recreated.
- **The comparison rests on a day of history.** The four-hour horizon cannot be measured at all yet,
  and no cell has enough evidence to clear a family bar. Nothing here is a finding about any source.
- **The timeframe measurement has never been tested**: it is stored nowhere for a past call, so it
  can only be measured once managed paper positions exist and freeze one.
- **No managed paper position and no registered trial exist**, so v2's evaluator has been exercised
  on fixtures and unit tests only, never on a real cohort.
- **Browser QA not run** (Playwright absent), so the new panel was not exercised at 1366 or 375 CSS
  pixels; `tsc`, Vite and the node tests passed.
- The 500-row liquidation cap and the 3-significant-figure book apply to the reconstruction exactly
  as they do to a live entry, so both populations share those limits.

[Comparison method and results](../research/2026-09-16_entry-evidence-comparisons.md) ·
[Frozen v1 protocol](../research/2026-09-14_source-comparison-v1.md) ·
[Documentation index](../README.md)
