# 2026-09-16 (afternoon) — Three branches merged, three live faults fixed, Docker recovered, deployed

Integration branch `codex/2026-09-01-dashboard-overhaul`. Paper mode untouched throughout
(`DRY_RUN=true`, `EXECUTION_ENABLED=false`). No key, signer, wallet or execution path was enabled, and
paper entries stayed paused with their original reason from the first merge to after the deploy.

## What merged

| Commit | Branch | Migration |
|---|---|---|
| `fa856d3` | product surfaces (regime summary, liquidations by source, opportunity briefs, operator menu, Settings, retention) | — |
| `aed2484` | Activity & Evidence | — |
| `574bfa0` | mobile PWA and delivery (Web Push sender, tap acknowledgement, retries, dead letters, delivery ledger) | 038 |

Each branch's own record carries its detail: `2026-09-16_product-surfaces.md`,
`2026-09-16_activity-and-evidence.md`, `2026-09-16_mobile-pwa-and-delivery.md`.

## What only appeared once they met

- **`main.py`'s tail.** Every branch registers its routes there, so each merge conflicted on the same
  lines. Resolved by keeping every registration from both sides. The route table was checked for
  duplicates on each merged tree: 177, then 184 routes, none duplicated.
- **Retention policy (`bdf1d87`).** Product surfaces' retention test fails whenever the service code
  deletes from a table the policy does not declare. The mobile branch added a deletion from
  `mobile_web_push_subscriptions`. It is an operator removing one browser, never ageing out, so it is
  declared as not retention. Merge commit `574bfa0` carries that one failing root test; the next commit
  fixes it.
- **Skipped migration numbers.** 038 arrived. 039 and 040 had been held for branches that needed no schema
  change, and all of them are merged, so both numbers are released. `SKIPPED_MIGRATION_NUMBERS` is back to
  the retired `035`.

## Three live faults fixed

**An executed order could never be recorded (`513a7be`).** The Activity & Evidence branch found this by
reading the code. `/actions/execute` used the venue's order id as the row's primary key, in the `uuid`
column `exec_orders.id`. In paper mode that id is `sim_hl_<hex>`; on Hyperliquid it is a number. Every
insert therefore failed, and the caller was told the order failed, with `dry_run: false`.

It was worse than reported. With no row kept, the idempotency check found no order for the decision, so a
repeat call reached the venue again: a duplicate order once live. Reproduced through the real route
against a throwaway PostgreSQL built by `ops/apply_schema.py`: `DataError`, zero rows, two venue calls.
After the fix the row gets its own UUID and the venue's id is kept in `txid`. The same run then shows
one row, `status=placed`, `dry_run=true`, the opportunity marked executed, and the repeat returning the
stored result with one venue call in total. The last-resort failure now reports the configured mode.
`tests/test_exec_order_record.py` fails on the old route and passes on the new.

**The TradingView source check would refuse every tunnel alert (`b0326fa`).** The morning deploy made
state-api believe `CF-Connecting-IP` only from cloudflared's future fixed address on `pine-ingress`
(172.29.53.10). The running connector was created before that compose change and still sits on the
default network at 172.18.0.9, deliberately, because moving it is the operator's step. From that address a
real TradingView alert would have been judged by the connector's own address and refused with 403.

None had arrived since 07:21. The only two refusals in the log were local posts from the Docker host at
10:27. `TRADINGVIEW_INGRESS_HOSTS` (compose default `cloudflared`) is now resolved for each alert, off the
event loop. A name that does not resolve adds no peer, and any other container is still judged by its
own address. Live, the name resolves to 172.18.0.9 inside state-api.

A probe of the public URL from a non-TradingView address gets Cloudflare's own 403 page. The edge
allowlist is active, so only a real TradingView alert can exercise the receiver end to end.

**The Cockpit did not come back after a Docker restart (`81668d1`).** It was the one service with
`restart: no`. It now has `unless-stopped` like the rest.

## Docker Desktop crashed at 13:37 and was recovered at 17:29

- **The crash.** Docker's host logs stop mid-stream at 13:37:44 with no shutdown sequence. At that
  moment its network forwarder reported about 2,060 TCP connections in progress, flat across the 13
  minutes of log that survived rotation. The machine did not reboot; it went through Modern Standby
  between 14:37 and 15:08.
- **Load.** Host memory was 15.8 GB total with about 0.5 GB free; the WSL VM is capped at 6 GB. Three
  agents were building, testing and running throwaway databases at once. That is the same pattern as
  the crashes of 8, 11 and 14 September.
- **Recovery.** The stale socket folders were renamed aside, never deleted and never reset, and Docker
  Desktop was started; the engine answered 1 minute 30 seconds later. Every service with a restart policy
  came back healthy. Redis kept its compose limits. Paper invariants were unchanged.
- **Sockets.** Sampled every two minutes for 40 minutes afterwards, no container's socket counts grew.
  state-api's CLOSE_WAIT sockets held at 10: idle keep-alive connections of its two long-lived feed
  clients, reset on redeploy. market-data holds 140–210 sockets in TIME_WAIT from opening a new
  connection per request. That is churn, not a leak, and connection reuse is being built on the
  market-data plane branch.
- **Prevention.** Parallel agents now take a shared lock (`E:\ChaseOSTemp\tradesync-heavy.lock`) around
  builds, full test suites and throwaway containers.

## Refactors, all moved unchanged and proven

| Commit | What | Proof |
|---|---|---|
| `1f23c77` | `ablation_statistics.py` out of `ablation_evidence.py` | golden output of `assess_family` and the error functions byte-identical |
| `c49fe45` | session A's script out of `tools/qa_paper_risk_sql.py` | generated SQL, commands and `--help` byte-identical; 16/16 live checks on a throwaway cluster before and after |
| `b9200aa` | phase 3D, paper signal and regime pipeline tests split by concern | every definition AST-identical and moved once; all 1,256 root tests run in the same order with the same outcomes |
| `6807adf` | Cockpit `api/types.ts` into 15 domain files behind a barrel | all 134 exported type shapes identical under the TypeScript checker (union members sorted, internal symbol ids stripped); `tsc`, 249 tests and the build pass |

## Deploy, 17:55

- **Migrations.** `schema-init` applied **038**; recorded versions from 030 are now `030 031 032 033 034 036 037 038`.
- **Rebuilt and recreated.** Built one image at a time: state-api, market-data, core-scorer, fusion-engine,
  discord-reader, cockpit-ui.
- **Deliberately untouched.** cloudflared (the operator's move to `pine-ingress`) and signer-svc (needs
  `SIGNER_CALLER_TOKEN` first); Postgres and Redis too.
- **Paper invariants, identical before and after.** `entries_paused=true` ("Initial paper safety review
  required", 14 September); kill switch inactive; 0 managed positions; 1 ledger row; 0 kill events; 0
  exec orders.
- **Live checks.**
  - state-api answered 200 on /healthz, the regime summary, opportunity briefs, retention, the audit
    export, reconciliation views, the outcomes summary, TradingView setup, harness status and paper rules.
  - The Cockpit served `/`, `/logs`, `/settings` and `/market`, plus `manifest.webmanifest`
    (`application/manifest+json`), `sw.js` and `offline.html`.
  - market-data /readyz answered 200.

## Verification on the shipped tree

Python: root **1,256**, state-api **725**, market-data **164**, exec-hl-svc **11**, signer-svc **14**; runner
exit 0. Cockpit: **249/249**; `npm run build` exit 0.

## Honest notes

- The Cockpit restart-policy commit was made before its checks ran. The checks then ran properly:
  compose resolves `restart: unless-stopped`, and 1,256 root tests pass.
- No browser QA of the new pages yet. The Cockpit answered over HTTP only.
- No real Web Push has been sent: the VAPID key pair, `MOBILE_WEB_PUSH_SUBJECT` and HTTPS reachability for
  phones are operator steps.
