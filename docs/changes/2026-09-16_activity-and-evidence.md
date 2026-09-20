# Activity & Evidence — 16 September 2026

Branch `claude/activity-evidence` in `E:\Projects\TradeSync\activity-evidence-2026-09-16`, branched from integration
commit `67cd33f`. It replaces the Decisions & Orders placeholder at `/logs` with the roadmap's Activity & Evidence
page: Decisions, Approvals, Orders, Alerts and Outcomes, each backed by real data.

**Nothing here is deployed.** No container was built, started, stopped or restarted, and the running stack was not
read. **No migration** was added. **No state-api route** was added, and `services/state-api/app/main.py` is
unchanged. Nothing on the page writes anything. `DRY_RUN` and `EXECUTION_ENABLED` were not touched.

## 1. What was removed

The old page was a placeholder dressed as a feature:

- the Decisions and Orders tabs rendered hardcoded empty tables and fetched nothing;
- venue, status and date filters were wired to nothing, and the venue filter offered Hyperliquid, the only venue;
- fixed legends listed statuses (Allowed, Blocked, Pending; Placed, Pending, Failed) that no query produced;
- it was styled with Tailwind utility classes.

All of it is gone. The route stays `/logs`, so existing links and the sidebar entry still work.

## 2. The five tabs

| Tab | Data source | Columns | Statuses shown |
|---|---|---|---|
| Decisions | `GET /state/audit/export`, section `decisions` | recorded, market, plan, size, verdict, policy reason, opportunity (links to its detail), decision | `risk.allowed` (Allowed or Blocked) and `risk.reason_code` |
| Approvals | the same reading, section `approvals` | bound, approved, state, consumed, consumed by, candidate, candidate hash, approval digest, ChaseOS decision, approval, envelope | consumed or not consumed |
| Orders | the same reading, section `orders` | recorded, status, mode, market, size, error, order, decision, transaction | `status` exactly as stored, and the `dry_run` flag as Paper or Live |
| Alerts | `GET /state/market/alerts?limit=100` through the existing `useMarketAlerts` hook | raised, market, type, metric, change | none: a market alert carries no status |
| Outcomes | the same reading, section `outcomes` | called, market, side, horizon, status, signed return, market move, max favourable, max adverse, entry → exit, candles, reason, measured, evidence digest, opportunity | measured, pending or insufficient candles |

The four audit tabs share one reading, `GET /state/audit/export?days=<window>&rows=200`. That route already existed
and already bounds, orders, scrubs and digests every section (`tradesync_core.audit_export`). The page asks for the
newest 200 rows a section rather than the route's 5,000. The reading refreshes every five minutes and when Refresh is
pressed, never faster, like the other readings that scan a table.

**Statuses the data carries.** Each audit tab lists, above its table, the distinct values its rows carry ("Statuses
in these rows: Rejected · Placed"), in the order first seen. The fixed legends are gone. No count is computed: the
only figures are the row count and truncation that state-api reports.

**No mathematics in TypeScript.** Percentages, prices and sizes are formatted exactly as state-api sent them.
`forward_return_pct` is already a percentage and is never rescaled; a test pins that. A missing measurement is a dash,
never 0.

## 3. Reading times, refresh and empty states

- **Exact time.** An audit tab shows the API's own `generated_at` and the window's `from` and `to` as UTC stamps. The
  alert stream reports no time of its own, so that tab says when the Cockpit *received* the answer, and says why.
- **Refresh.** Every tab has a Refresh button. On the audit tabs it reads "Refreshing…" while the export is being
  read.
- **Four states that never read as each other** (`readingState`):
  - no data yet: "Reading…";
  - no data and an error: "No reading. The request to the state API failed, so this is not an empty result: …",
    with the API's own reason and HTTP status;
  - data and an error (a failed refresh): the earlier rows stay on screen, with "The latest refresh failed (…). What
    is shown is the earlier reading, taken …";
  - data and no rows: "Nothing in this window: no order was recorded between … and …", with both exact bounds.
- **Truncation.** A section that reached its cap says "This window holds more than the 200 shown here". It never
  presents `rows_available_in_window` as a total, because that is at most the cap plus the one probe row. It links the
  CSV export, which carries up to 5,000 rows over the same window length.
- **Redaction.** When state-api replaced fields under secret-looking keys, the tab counts them.
- **Tab counts.** Taken only from a current reading, with a plus where a section was capped or the alert read came
  back full. A failed refresh removes the counts rather than leaving old ones on the tabs.

## 4. Controls: removed, wired and not added

- **Removed**: the venue filter (Hyperliquid is the only venue), the status filter and the date input. None changed
  a query.
- **Wired**: a window of 1, 7, 14 or 31 days on the four audit tabs. It sets `days` on the export query, and 31 is
  the route's bound. The tab and window are in the address (`/logs?tab=orders&days=14`), so a reading can be linked.
  An address naming an unknown tab or window falls back to Decisions over 7 days.
- **Not added**:
  - no window on Alerts, because the stream has none and filtering a capped read by time would hide what it left
    out;
  - no status filter, because the export takes no status parameter, and filtering 200 capped rows in the browser
    would make a truncated section look complete.

## 5. What the roadmap names that the stored rows do not carry

The roadmap item lists richer lifecycles than the tables hold. The page shows what is stored and invents none of the
rest.

- **Decisions** (roadmap: proposed, allowed, blocked, expired). A decision row is written only when the risk check
  allows a preview (`preview_action`), so a stored row is always allowed. **While `EXECUTION_ENABLED=false`, the
  check refuses every preview with `EXEC_DISABLED` before anything is stored**, so this tab is empty in the paper
  default by construction. The tab says so, and points to the paper rehearsal journal on Execution readiness.
- **Approvals** (roadmap: pending, approved, denied, expired, consumed). `control_envelopes` is written only when an
  approval is bound, so every row is approved and the only state that varies is consumed or not. Staleness is judged
  by the `stale_approvals` reconciliation view on the Signal Ledger.
- **Orders** (roadmap: preview, submitted, placed, partial, filled, cancelled, failed, reconciled). The execution
  boundary writes `placed`, `rejected` or `error`. `/actions/execute` checks the gate again before inserting, so no
  order row is written while it is closed.
- **Alerts** (roadmap: triggered, routed, delivered, acknowledged, expired, dead-lettered). Market alerts are
  regime changes held in a capped Redis stream, with no delivery status. Delivery states exist in
  `mobile_alert_outbox`, but today they are readable only through `GET /state/mobile-alerts/devices`: behind the
  mobile control key (`X-API-Key` against `MOBILE_ALERTS_CONTROL_KEY`), the newest 50, with no window. Per the brief, this tab uses the market alerts.
- **Outcomes** (roadmap: P&L, MFE/MAE, fees, funding, slippage, thesis adherence, lessons). Outcome rows carry the
  market move, the signed return, max favourable and max adverse excursion, prices, candles, the reason and the
  evidence digest. No position existed behind them, so they hold no fees, funding or slippage. Costed paper positions
  and thesis adherence are on the Signal Ledger, which the tab links. Nothing stores lessons.

## 6. market-data: an unreadable alert stream is an error (`d08afc3`)

`MarketRedisClient.get_alerts` swallowed any Redis failure and returned `[]`, so `GET /alerts` answered
`{"alerts": [], "count": 0}` for a stream it could not read. That is the same answer as a stream in which no alert was
ever raised. The Alerts tab could not honour its empty-state rule with that.

The read now raises, and the route answers **503** with `alert_stream_unreadable`. state-api already turns any failed
market-data answer into its own 503, so the Cockpit shows a failed request, not an empty stream. A stream that was
never written still reads as empty, because `XREVRANGE` on a missing key returns nothing without an error. Nothing
else calls this read. `tests/test_alerts_read.py` has four tests, and the two failure-path tests fail against the
previous code.

## 7. Files

`services/cockpit-ui`:

- `src/api/activityTypes.ts`: the audit export types, in a new file beside the shared `api/types.ts`, which is
  unchanged.
- `src/api/hooks/useAuditExport.ts`: the one reading the four audit tabs share.
- `src/pages/Logs.tsx` and `Logs.module.css`: the page, its tabs, and the tab and window in the address.
- `src/components/activity/`:
  - `ActivityTabs`, `ReadingBar`, `ReadingNotice`, `EvidenceTable` and `AuditSectionPanel`, the frame of an audit tab;
  - `DecisionsPanel`, `ApprovalsPanel`, `OrdersPanel`, `OutcomesPanel` and `AlertsPanel`;
  - `cells.tsx`;
  - every component with a CSS module of its own;
  - `activityFormat.ts` (tabs, windows, reading state and messages) and `rowFormat.ts` (verdicts, statuses, payload
    fields and number formatting), both pure.
- Names: the sidebar entry, the header title and the Execution readiness link now say Activity & Evidence. The
  Execution footer used to say "every decision, rehearsal and refusal is kept in the ledger", which the linked page
  never showed. It now names what the page shows.

The largest file is `rowFormat.ts` at 135 lines, and the largest component is `AuditSectionPanel.tsx` at 72. No
Tailwind utility class is used.

**Wording.** `tests/ui-wording.test.mjs` gains two tests:

- every file of the page must yield rendered text to the scanner, and none may use retired wording;
- every message the helpers build at runtime is produced, every branch, and checked the same way.

The paper flag lives in a column named `dry_run`, and its labels read Paper and Live. Planting "dry run" in a label
and "simulated" in a description fails all three wording tests.

## Verification

Node tests and the build ran in `services/cockpit-ui`, through the shared `node_modules` junction:

- `npm test`: **166 passed, 0 failed**, exit 0. At `67cd33f`: 146. The difference is
  `tests/activity-format.test.mjs` (18) and the two new wording tests.
- `npm run build` (`tsc && vite build`): **passed**, exit 0, 36.2 s wall clock (Vite reported "built in 15.59s").
  The page chunk is `Logs-*.js`, 16.95 kB (6.03 kB gzip).
- Both were re-run on the final tree, after the last copy change, with the same test count.

Python ran with `tools/run_tests.py` and the project venv at `E:\Projects\TradeSync\dashboard-overhaul-2026-09-01\.venv`,
since this worktree has none:

`tools/run_tests.py` exited **0**, read from the runner's own exit code, in 73.8 s.

| Suite | Result | Added by this branch |
|---|---|---|
| root | **1218 passed**, 17 deselected, 2 warnings, 49 subtests | none |
| state-api | **611 passed** | none |
| market-data | **164 passed** | 4 (`test_alerts_read.py`), so 160 at `67cd33f` |
| exec-hl-svc | 11 passed | none |
| signer-svc | 14 passed | none |

The root suite's `test_rendered_cockpit_strings_avoid_retired_wording` ran the extended node wording test. It passed
when run alone, not skipped.

**Not run**:

- browser QA, because Playwright is not installed here;
- a live read-back, because nothing was deployed.

The page was checked by `tsc`, the Vite build and the node tests only, not at 1366 or 375 CSS pixels.

## Findings for the operator

1. **Decisions and Orders are empty in the paper default, by construction.** With `EXECUTION_ENABLED=false`,
   `RiskGuardian.check` refuses every preview (`EXEC_DISABLED`) before a decision is stored. The execute path
   re-checks before an order is stored. The paper activity that does happen lives in the rehearsal journal and in
   managed paper positions, neither of which the audit export covers. Whether the export, and so this page, should
   carry rehearsals and managed positions is an operator decision.
2. **A paper order could not be recorded even with the gate open.** Found by reading the code, not by running it.
   Under `DRY_RUN=true`, exec-hl-svc answers `placed` with `order_id = "sim_hl_<hex>"`. state-api then inserts that
   value as `exec_orders.id`, a `uuid` column (`ops/sql/schema.sql`). asyncpg refuses it, the outer handler answers a
   generic error with a literal `dry_run: false`, and no order row is written. Not reachable while the gate is closed,
   and not changed here, since the fix belongs in the execute route in `main.py`.
3. **The running state-api predates the audit export.** Its merge (`e050696`) came after the 16 September deploy,
   and its record says it was not deployed. Until state-api is rebuilt, the four audit tabs will say, correctly, that
   the request failed (HTTP 404).
4. **Alert delivery states have no windowed read.** A delivery ledger tab would need a read-only, windowed route over
   `mobile_alert_outbox`. That was not added, because the brief names the market alerts for this tab.
5. `limit` on `GET /state/market/alerts` is not bounded, in state-api or in market-data. The page asks for 100.

## Deploy steps for the lead

Nothing below has been done. Paper only.

1. **Merge** `claude/activity-evidence`. It has **no migration, no schema step and no `main.py` change**.
2. **Test the merged tree**: `.venv\Scripts\python.exe tools\run_tests.py`, then `npm test` and `npm run build` in
   `services/cockpit-ui`.
3. **Rebuild and replace market-data, state-api and cockpit-ui**, as in the [paper gaps record](2026-09-15_paper-gaps.md).
   state-api must carry the audit export, from `e050696` or later. market-data must carry `d08afc3` for the Alerts tab
   to tell an unreadable stream from an empty one.
4. **Read back** (read-only):
   - `/logs` shows five tabs;
   - Decisions and Orders show either their stored rows or "Nothing in this window" with exact bounds, and never a
     failed request once state-api carries the export;
   - Outcomes lists measured rows with a reading time;
   - changing the window changes the `days` in the request;
   - stopping Redis briefly makes Alerts say the request failed, not that the stream is empty. That check is
     optional, and restoring Redis is part of it.
5. **Rollback**: redeploy the previous images. Nothing was written and no schema changed.

[Outcome metrics and reconciliation](2026-09-16_outcome-metrics-and-reconciliation.md) ·
[16 September integration](2026-09-16_integration-and-deploy.md) · [Documentation index](../README.md)
