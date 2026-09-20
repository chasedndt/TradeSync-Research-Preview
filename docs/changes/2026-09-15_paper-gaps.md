# Paper gaps closed: held kill-switch exits, part fills, and exits proven on real candles — 16 September 2026

Branch `claude/paper-gaps` in `E:\Projects\TradeSync\paper-gaps-2026-09-15`, branched from
`codex/2026-09-01-dashboard-overhaul` at `566fea9`. Project-local build record.

Nothing here is deployed: no container was built, started, stopped or restarted, **no migration was
added or applied**, and no public table was written. Paper only; no order, wallet, signer or
execution path was touched, and the public entry pause stays on.

## What changed

### 1. A kill-switch exit the book held owed is audited like an immediate one

A kill-switch close walks a fresh book for the position's quantity. When the displayed depth cannot
take it, the exit stays owed and fills at a later observation — which may be the monitor's own retry
or the observer's next tick. That held close recorded `kill_switch` but wrote no audit row and lost
the rule that coincided with it.

- **The owed exit now carries why it fired and whose kill owed it.** `paper_kill.kill_close` labels an
  owed exit with `coincided_rule` and with the operator and reason of the kill (`kill_switch`), and
  the lifecycle carries both into the exit record when a later observation fills it
  (`managed_paper.CARRIED_INTO_EXIT`). The kill that owed the exit is frozen on the exit, so a later
  fill audits that kill and not a newer one.
- **One audit path for both loops.** `app/paper_kill_audit.record_close` writes the close row
  (`paper_kill_switch_events`, action `close`), and both `paper_kill_switch.close_one` and the
  observer (`managed_paper.update`, through `paper_risk_hooks.record_kill_close`) call it. It is
  written in the transaction that stores the close, so a kill-switch close cannot be stored without
  its audit row. The stored event carries the kill's operator and reason too.
- **Detail** (`paper_kill.close_audit`): symbol, exit price and time, `coincided_rule`, `held`,
  `fired_at`, `filled_at`, and `filled_by` (`observer` or `kill_switch`).
- An exit owed before its kill recorded an operator falls back to the kill still standing; a close
  with neither is refused rather than audited anonymously.

### 2. Part fills, and the depth a fill may walk — `managed-paper-lifecycle-v3`

**The bound.** A taker order on Hyperliquid carries a price limit and fills only what the book offers
inside it. Every style now declares `max_depth_bps`, how far past the touch a fill may walk: **scalp
5, intraday 10, swing 20**. A shorter style tolerates less because its whole move is smaller (a
scalp's stop is about 1.5 × ATR(15m); 5 bps is a small fraction of it). The half spread every taker
pays is bounded separately by `max_spread_bps` (20), so the two together bound the total. The walk
model is `observed_depth_walk_v2`.

**At entry: refused, not part filled.** A walk that cannot fill the notional within the bound raises,
naming the share it could fill and what stopped it (`the depth bound` or `the displayed ladder`), and
the entry is refused. The alternative — filling what the book takes and recording the rest unfilled —
was rejected: an entry is optional where an exit is not, and a part-filled entry would quietly change
the size the operator chose, the planned risk the gates approved and the notional the risk engine
admitted, after the fact. It would also need a minimum-fill rule to stop a 2% fill becoming a
fee-dominated position. The entry still also requires that the same book could take a full exit
within the bound, so nothing is opened that could not be closed at that moment.

**At exit: filled in parts.** `paper_exit_fills` records each part with its own quantity, price, fee,
gross result and book snapshot; the rest stays owed with the reason; the position closes at the
observation that fills the last part. Gross, fees and the exit price are summed from the parts, never
one average applied to the whole size. `exit_price` is the quantity-weighted price, `slippage.exit` is
the single part's own fill when one part filled it and a summed record (`book_walk_parts`) when
several did. A position is marked on, and exposes, only the quantity still held (`open_quantity`).
On candles an owed exit fills at the next candle's open, its first observed instant.

**Funding stays exact.** A settlement is paid on the quantity held at that hour, so
`paper_funding_store` writes each row for `held_quantity(state, hour)`, and an open position settles
only the hours it has been observed past — a part filled before an hour but seen after it would
otherwise settle that hour at the size before the part. The observer and the kill switch therefore
advance the position first and settle funding from the advanced state.

**Ledger and reconciliation.** Unchanged in shape and still exact: the realised entry books once, at
the full close, from the `closed` event's state; its slippage is the entry fill's cost plus the sum of
the parts' costs, reported beside gross and never subtracted twice; funding settled after the close is
still one adjustment of exactly the change. Reconciliation compares the same stored states.

**Older positions.** A position opened under `managed-paper-lifecycle-v2` declares no bound, so its
exits still fill whole or stay wholly owed, and its closed states keep the single-fill accounts.

### 3. Target, time expiry and a gap at a candle's open, proven on real candles

- `tools/qa_paper_rule_windows.py` (read-only) searches every tracked symbol's real 1-minute candles
  and the books TradeSync recorded for windows where each rule fires under v3. Nothing is written.
- `tools/qa_paper_rule_fixtures.py` replays the windows it found in a throwaway schema inside one
  rolled-back transaction, with funding settled from Hyperliquid's published rates at the oracle
  prices recorded in `market_open_interest`, and emits each window as a fixture.
- `tests/fixtures/paper_rules/{target,time_expiry,gap_at_open}.json` hold those windows — candles, ATR
  candles, recorded books, settled funding, source and exact time range — and
  `tests/test_paper_rule_windows.py` replays them as regression tests.

### 4. Cockpit

- **Position details** (`ledger/paper/PaperFills.tsx`, CSS module): every part an exit filled, with its
  time, quantity, fill price, fee, cost against the mid and how many displayed levels the book took,
  plus what stopped the fill (the depth bound or the ladder). While an exit is owed it states how much
  of the size is still owed and why. `PaperExit` adds the part count, any coincided rule and the kill
  that owns the close.
- **Paper risk** (`ledger/paperRisk/KillHistory.tsx`, CSS module): recent kill switch activity,
  including a close the book held owed — where it filled, that it was held, which loop filled it, and
  any rule that coincided.

## Verification

### Unit suites

`tools/run_tests.py`, project venv, on the committed branch:

| Suite | Result | At `566fea9` |
|---|---|---|
| root | **1037 passed**, 17 deselected, 2 warnings, 49 subtests | 1019 |
| state-api | **409 passed** | 401 |
| market-data | 160 passed | 160 |
| exec-hl-svc | 3 passed | 3 |
| signer-svc | 10 passed | 10 |

New: `tests/test_paper_partial_fills.py` (8), `tests/test_paper_rule_windows.py` (7),
`services/state-api/tests/test_paper_kill_audit.py` (4),
`services/state-api/tests/test_paper_part_fills.py` (4), two in `tests/test_paper_kill.py`, one in
`tests/test_paper_lifecycle_rules.py`. Changed for v3: the owed-exit test in `tests/test_paper_exits.py`
(it now part fills) and the entry-walk ladder in `tests/test_managed_paper.py` (its third level sat
7 bps past the touch, outside the scalp bound).

Cockpit, `services/cockpit-ui`: `npm test` **98 passed** (was 97; the new one covers part quantities),
`npm run build` **passed** in 24.13 s with only the existing warnings.

### Real-candle search, 16 September 06:31–06:41 UTC

Read-only, inside the running state-api container against this checkout's code. 40 hours (the window
the recorded books cover: 14 September 11:38 to 16 September 06:13 UTC), 60 real opportunities per
symbol × 3 styles × 10 symbols = **1800 attempts**.

- Exits fired: stop 369, trailing stop 150, target 59, time expiry 55, and **4 with an adverse fill at
  a candle's open** — the rarity is why the first pass of 360 attempts found none.
- Refusals recorded, never replaced by a guess: 18 "Insufficient reward after declared costs",
  19 whose last candle was not closed at the search's clock, 6 with no book recorded at or before the
  entry minute, and 20 refused by the new depth bound on recorded books, which quote 3-significant-figure
  bucket edges (for example "displayed depth within 5 bps past the touch fills 13.6% of the size").

### Isolated acceptance, 16 September 06:54:59–06:55:23 UTC: 29 of 29 checks passed

`tools/run_in_state_api.py tools/qa_paper_rule_fixtures.py --with tools/qa_paper_rule_windows.py`.
One throwaway schema (`qa_paper_rules_…`) inside one transaction, rolled back; public tables read only.
Each window was checked for: real candles and a recorded book covering it, the state reading back from
JSONB unchanged, the rule and level it fired at, the exit fill recomputed as the trigger price moved by
the book recorded at or before that candle, both fees as the taker rate on their own fill, a funding row
or a missing marker for every hour crossed, each payment as side × quantity × price × rate, and
net = gross − fees − funding.

| | Target | Time expiry | Gap at the open |
|---|---|---|---|
| Market, style, side | BTC-PERP scalp long | BTC-PERP scalp short | PUMP-PERP scalp short |
| Opportunity | `ef7b7733…` | `3a1ccafe…` | `b1949b7e…` |
| Entry (UTC) | 15 Sep 17:14:00 | 15 Sep 20:21:00 | 15 Sep 17:56:00 |
| Exit (UTC) | 15 Sep 17:35:00 | 15 Sep 23:21:00 | 15 Sep 18:38:00 |
| Minutes evaluated | 22 | 180 | 43 |
| ATR (14 closed 15m) | 361.357143 | 502.714286 | 0.0000412143 |
| Entry fill | 76,260.0393959291 | 75,825.04937458855 | 0.003558987341772152 |
| Quantity | 0.003278256895489428 | 0.0032970634646732346 | 70,244.70052639068 |
| Stop / target | 75,718.0036816 / 77,344.1108245 | 76,579.1208032 / 74,316.9065174 | 0.0036208088 / 0.0034353445 |
| Rule | target, inside the candle | time expiry, at the close | trailing stop, at the open |
| Level → fill | 77,344.1108245 → 77,293.8547421 | expiry 23:21:00, close 75,893.0 → 75,943.0283454 | 0.0034932143 → 0.0035260516 |
| Gap fill | no | no | **yes**: the candle opened at 0.003521, already past the trailing stop, and filled worse still |
| Parts | 1 | 1 | 1 |
| Fees | 0.2265251005 | 0.2251750429 | 0.2239588990 |
| Settled funding | 0 rows (no hour crossed) | 3 rows, −0.0071547433 (a short receives) | 1 row, +0.0021293488 paid |
| Gross / net (USDC) | +3.3891122872 / **+3.1625871867** | −0.3889841543 / **−0.6070044539** | +2.3135578102 / **+2.0874695624** |

Fixtures written from that run: `target.json` 52,820 bytes (22 candles, 81 books, 15 ATR candles),
`time_expiry.json` 164,870 bytes (180 candles, 240 books), `gap_at_open.json` 69,648 bytes (43 candles,
102 books). Recorded books are trimmed to the five levels a 250 USDC walk can reach; on
3-significant-figure books the bound is tighter than the second bucket everywhere, so the trim can only
cause a recorded refusal, never a different fill.

### Live read-only checks, after the runs

No `qa_%` schema; `public.managed_paper_positions` count **0** before and after; `entries_paused`
**true** with its original reason; no transaction idle for more than a minute;
`schema_migrations` holds 001–033 (031, 032 and 033 already applied), and this branch adds none.

## What remains

- **Browser QA not run**: Playwright is not installed here, so the new panels were not exercised at
  1366 or 375 CSS pixels. `tsc`, the Vite build and the Cockpit node tests passed.
- **Part fills are proven on constructed books and the observer, not on a live thin book.** On the ten
  tracked markets a 250–1000 USDC exit fills inside the bound at the touch, so no live part fill
  occurred during this work; the depth bound did refuse 20 replay entries on 3-significant-figure books.
- **Swing and intraday windows** were not needed for the three rules: all three fired on scalp
  positions, which also keeps the fixtures small. The census above covers every style tried.
- **The bound's values are engineering hypotheses.** Nothing here was tuned on results, and no result
  is evidence of an edge.
- The kill-switch close audit is proven by unit tests and the isolated API acceptance; no live kill has
  been engaged (`paper_kill_switch_events` is empty).

## Deploy steps for the lead

Nothing below has been done. Paper only; the public entry pause stays on.

1. **Merge `claude/paper-gaps`** into the dashboard-overhaul branch. It touches
   `libs/tradesync_core/tradesync_core/{paper_lifecycle_rules,paper_depth,paper_exit_fills,managed_paper,paper_opening,paper_account,paper_kill,paper_observations}.py`,
   `services/state-api/app/{managed_paper,paper_kill_switch,paper_kill_audit,paper_risk_hooks,paper_funding_store}.py`
   and the Cockpit ledger panels. **No migration**: 035 was not needed, and
   `RESERVED_BY_PARALLEL_BRANCHES` is untouched.
2. **Test the merged tree**: `.venv\Scripts\python.exe tools\run_tests.py`, then in
   `services/cockpit-ui` `npm test` and `npm run build`.
3. **Replace state-api and cockpit-ui** (no schema change, so no schema step):

   ```powershell
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml build state-api
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml up -d state-api
   docker build -f ops/cockpit-prebuilt.Dockerfile -t tradesync/cockpit-ui:dev services/cockpit-ui
   docker compose --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml up -d --no-deps cockpit-ui
   ```

4. **Read back** (read-only): `GET /state/paper-positions/rules` shows
   `managed-paper-lifecycle-v3` and `max_depth_bps` per style; `GET /state/paper-risk` still returns
   its kill switch and reconciliation state; `GET /state/paper-control` still shows
   `entries_paused: true`. Resuming entries is an operator decision, not part of this deploy.
5. **Optionally re-run the acceptance** against the merged checkout (isolated schema, rolled back):
   `python tools/run_in_state_api.py tools/qa_paper_rule_fixtures.py --with tools/qa_paper_rule_windows.py -- <windows>`,
   and the search itself with `tools/qa_paper_rule_windows.py`.
6. **Rollback**: redeploy the previous state-api and cockpit-ui images. No schema changed, and the
   public portfolio is empty, so no position state needs converting. A position opened under v3 and
   read by v2 code would lose its part fills, which is another reason the pause stays on until the
   deploy is read back.

[Managed paper positions](2026-09-15_managed-paper-positions.md) ·
[Paper risk engine](2026-09-15_paper-risk-engine.md) ·
[Documentation index](../README.md)
