# 2026-09-15 — Agent harness kill switch: stop and start the Hermes gateway from the Cockpit

Branch `claude/harness-kill-switch` from `566fea9`. Paper-only: no execution flag, gate, signer or wallet
changed, and no `DRY_RUN` or `EXECUTION_ENABLED` touched. **The Hermes gateway was never stopped, started or
restarted here, and no Hermes job was changed.** Implemented and tested locally: **not deployed**, **migration
034 not applied**, and the host control task **not registered**. The first real stop and start belong to the
operator or the lead, after merge.

## What it is

Three parts, so that one press in the Cockpit is both immediate and honest about what it reached:

1. **state-api** keeps the desired state (`running` or `stopped`) with the operator, the reason and the time,
   issues one command per request for the host, and records what the host did. While the state is `stopped`,
   every TradeSync caller of Hermes refuses at once, whatever the gateway is doing.
2. **A host control process** on Windows (Task Scheduler, `pythonw`) polls for that command, stops the gateway
   exactly as `hermes gateway stop` does, or starts its service as the logon script does, and reports the
   command, its exit status and `systemctl --user is-active` afterwards.
3. **The Cockpit** shows the switch in the header on every page, asks for a name and a reason before changing
   anything, follows the command from pending to applied or failed, and warns when the desired state and the
   gateway disagree.

## 1. Persistent state: migration 034

`ops/migrations/034_agent_harness_control.sql`:

- `agent_harness_control`, one row: `desired_state` (`running`/`stopped`), `operator` (1–80 characters),
  `reason` (5–240), `requested_at`, the `command_id` for the host, the `claimed_command_id` it took, and the
  last result (`result_command`, `result_exit_status`, `result_is_active`, `result_detail`, `result_at`).
  Seeded `running` with **no command**, so applying the migration changes nothing and leaves the host nothing
  to run.
- `agent_harness_control_events`, the audit: every `requested`, `applying`, `applied` and `failed` row with
  who, why, the command, the exit status and the systemd state. A trigger refuses `UPDATE` and `DELETE`, and a
  unique expression index allows at most one request, one claim and one result per command.

`services/state-api/app/harness_control_store.py` holds the statements and the memory fallback used without a
database (tests, tooling): `current`, `request`, `claim`, `report`, `history`. Each change takes the control
row's lock, so a request, a claim and a report never interleave. A result that arrives late for a superseded
command is audited but does not replace the current command's result.

## 2. TradeSync refuses to call Hermes while it is stopped

`services/state-api/app/harness_gate.py` reads the switch on **every** check — no cache, so a stop applies to
the next call — and a switch that cannot be read (database down, migration not applied) is itself a refusal.
The refusal names who stopped it, when and why. Callers:

| Caller | While stopped |
|---|---|
| Timeframe reading (`horizon_reading.start`) | No attempt row is written; `POST /state/market/horizons/reading` answers **423** with the reason |
| A reading already running (`horizon_reading.run_reading`) | Finishes `unavailable` with the reason, without asking Hermes |
| Daily reading schedule (`reading_schedule.start_scheduled`) | The slot is recorded `skipped` with the reason, before anything is measured |
| Thesis briefing (`editions.hermes_briefing`) | The edition is built and stored with `briefing.status = "stopped"` and the reason |
| Fleet directives that need the gateway (pause, resume, run now, delivery) | **423** with the reason; the gateway is never called |
| Fleet schedule and enabled changes | Left pending for the host bridge, with the reason in the detail (the bridge edits `jobs.json`; it does not call the gateway) |
| Fleet page job state (`fleet_live.overlay`) | Read from the bridge snapshot; the jobs API is not called |
| `POST /state/agents/harness/ask` (the boundary every ask goes through) | **423** from `AskGate` before `agent_connector.ask` runs |
| core-scorer claim reading | Reads `GET /state/agents/harness/gate` (10 s cache) and asks nothing; a 423 mid-pass ends the pass. Rows stay un-asked and are read after a start |

The Hermes heartbeat (`GET /health`) keeps running while stopped. It is how the Cockpit tells a stopped
gateway from one that still answers, and it costs the gateway nothing.

## 3. Routes

- `GET /state/agents/harness/control` — desired state, host progress and last result, gateway heartbeat,
  whether TradeSync calls Hermes, one sentence on whether these agree, and the audit.
- `POST /state/agents/harness/control` — `{desired_state, operator, reason, confirm: true}`. Refused without a
  name, a 5–240 character reason or the confirmation. Passes the access guard like every other change
  (cross-site origins 403, operator token when configured).
- `GET /state/agents/harness/gate` — the short answer core-scorer reads.
- `GET /state/agents/harness/control/command` — the host's poll; records when the host last checked in
  (memory only).
- `POST /state/agents/harness/control/claim` and `.../report` — the host takes a command before running
  anything (claimed once: 409 otherwise) and records the result once (a repeat answers `duplicate`).

`services/state-api/app/main.py` gains registration lines only.

## 4. Host control process

`tools/hermes_harness_control.py` (loop, HTTP, state file) and `tools/hermes_gateway_control.py` (the WSL
commands) run on the Windows host with `pythonw`, logging to `dashboard-runtime\logs\hermes_harness_control.log`.

**What `hermes gateway stop` and `start` actually do**, read from the CLI source
(`~/runtimes/hermes-home/hermes-agent/hermes_cli/gateway.py`) on 15 September:

- `stop` resolves the unit `hermes-gateway` for `HERMES_HOME=/home/operator/runtimes/hermes-home`, writes the
  planned-stop marker `.gateway-planned-stop.json` naming the running gateway, then runs
  `systemctl --user stop hermes-gateway`, waiting up to 90 s. The marker is what makes the gateway treat
  SIGTERM as deliberate: it drains in-flight work (systemd allows `TimeoutStopSec=210`), records
  `gateway_state` stopped and exits cleanly, so the unit ends `inactive`. A bare `systemctl --user stop`
  sends the same SIGTERM without the marker; the gateway exits 1, the unit ends `failed`, and
  `gateway_state.json` still says running.
- `start` checks the user D-Bus session, **rewrites the unit file** when the definition it would generate
  differs from the installed one, then runs `systemctl --user start hermes-gateway`. That generated definition
  takes its Windows `PATH` entries and `node` from the shell that runs it.

So the host process **stops with the CLI itself** (`…/hermes-agent/venv/bin/hermes gateway stop`, which is
what `~/.local/bin/hermes` resolves to, with the unit's `HERMES_HOME`, from the unit's working directory) and
**starts with `systemctl --user start hermes-gateway.service`**, exactly as `%USERPROFILE%\.hermes\gateway.cmd`
does at logon, so a hidden Windows task can never regenerate the operator's unit file from its own `PATH`.

Behaviour:

- Polls `GET .../control/command` every 10 s; claims a command before running anything.
- No exit status is trusted on its own (the CLI answers 0 when it falls back or times out): `is-active`
  afterwards decides, waiting out `deactivating` for up to 240 s and `activating` for 30 s.
- **Runs a command at most once.** The id is written to the state file
  (`dashboard-runtime\hermes-harness-control-state.json`) before the command runs; a command state-api already
  shows as being applied, with no record here, is reported failed and not run; an undelivered report is sent
  again on later polls without running anything. Errors back off to a minute.
- **Tolerates WSL being down.** `wsl --list --running` is asked first, and it does not start the distro: a stop
  with WSL down reports `applied` with `is-active` "not running" and starts nothing. A start wakes the distro
  the way the logon script does, and reports the reason if WSL will not start.
- Never touches the ChaseOS coordination daemon (`%USERPROFILE%\.hermes\hermes-daemon-loop.cmd`), which
  ChaseOS Studio or Task Scheduler controls.
- `--check` is read-only: WSL, the unit's state and the switch, running nothing.

`tools/register-hermes-harness-control-task.ps1` registers the logon task (hidden, `IgnoreNew`, restart a
minute after a failure, and a five-minute repetition that starts it again if it has exited). **It was not
run.**

## 5. Cockpit

- **Header, on every page**: `Agent harness · running · Stop` or `Agent harness · stopped · Start`, with a dot
  for its state and a warning mark when the gateway disagrees. Hovering or focusing shows who asked, what the
  host did (command, exit status, systemd state), the gateway's heartbeat and whether TradeSync is calling
  Hermes. The name opens the record on the Agents page.
- **Confirmation**: a name and a reason (5–240 characters), and plain words about what a stop does — every
  Hermes cron job including StrikeZone and Community Server, the Discord bots, and TradeSync's own readings,
  briefings, fleet changes and claim reading — and what it does not: paper trading and market data continue,
  nothing is switched off for good, and the ChaseOS coordination daemon is separate.
- **Progress**: `stopping…` while pending or applying, then `stopped`, or `stop failed` with the reason.
- **Agents page** gains the kill switch section: the four readings side by side (requested, host control
  process, gateway health, TradeSync calls), the agreement sentence, Stop or Start with a `Stop again` or
  `Start again` when they disagree, the scope note, and the full history.
- An edition built while stopped says the briefing was not asked, and why.
- New files are CSS-module per component; `src/api/types.ts` (1,060 lines) was deliberately not touched, so
  the briefing status widening lives in `BriefingCard.tsx`.

## 6. Security finding L8 (owned here)

`agent_connector`'s probe and ask, the Hermes jobs API client in `hermes_jobs`, and core-scorer's claims
client now pass `trust_env=False`, so no proxy variable in a container can receive the gateway Bearer key or
the operator token. `services/state-api/tests/test_harness_clients_ignore_proxies.py` fails if any harness
client stops doing so. The review's L8 row is updated to "Fixed on `claude/harness-kill-switch`, not deployed".

## Live, read-only (nothing was changed)

At 18:09 UTC on 15 September, from this environment:

- `wsl.exe -d Ubuntu -- systemctl --user is-active hermes-gateway.service` → `failed`, exit 3, in 0.45 s.
  **WSL status queries do work from these shells**, contrary to the 13 September handover note; the read-only
  `show` query answered in 0.53 s and `wsl --list --running --quiet` in 0.2 s (`Ubuntu`, `docker-desktop`).
- `systemctl --user show hermes-gateway.service`: `ActiveState=failed`, `SubState=failed`, `Result=exit-code`,
  `ExecMainStatus=1`, `MainPID=0`, `NRestarts=0`, `UnitFileState=enabled`,
  `ExecMainStartTimestamp=Mon 2026-09-14 18:43:54 BST`, `ExecMainExitTimestamp=Tue 2026-09-15 17:39:12 BST`.
  **The gateway has been down since 16:39 UTC, before this branch existed**: the exit code and the absence of a
  restart are what a stop made without the planned-stop marker leaves behind.
- `GET http://127.0.0.1:8642/health` → connection refused.
- `GET http://127.0.0.1:8000/state/hermes/status` → `offline`, 263 consecutive failures, while the fleet
  bridge's last `gateway_state` snapshot still reads `running` — the stale reading the marker exists to avoid.
- `python tools/hermes_harness_control.py --check` → "WSL distro Ubuntu: running", "hermes-gateway.service:
  failed", "state-api: HTTP 404 for /state/agents/harness/control" (not deployed), in 2.0 s, with
  `TRADESYNC_RUNTIME_ENV` pointed at a file that does not exist so no token was read.
- The Hermes Discord health monitor (`hermes-discord-health-monitor.timer`, every five minutes) is
  "deliberately observation-only: it never restarts the gateway", so it will not undo a stop.
- Re-checked at 22:41 UTC, unchanged and untouched: `is-active` still `failed`, `:8642/health` still refused,
  the heartbeat at 1,357 consecutive failures, and the fleet bridge's 22:36 snapshot still reporting
  `gateway_state` `running`. `GET /state/agents/harness/control` answers 404 until this is deployed.

## Verification

- `tools/run_tests.py` (every Python unit suite, the project venv): root **1044 passed**, 17 deselected,
  2 warnings, 49 subtests passed in 43.0 s; state-api **451 passed** in 26.1 s; market-data **160 passed**;
  exec-hl-svc **3 passed**; signer-svc **10 passed**. Targeted runs before that: the new state-api suites with
  the reading, schedule, fleet, connector and access-guard suites, 108 passed; the core-scorer gate, migration
  and caller-token suites, 20 passed; the host control process and host-tool suites, 25 passed.
- Isolated SQL acceptance, `tools/qa_harness_control_sql.py` on a throwaway `postgres:16` container
  (PostgreSQL 16.15), one rolled-back transaction in a throwaway schema: **37 checks, all passed**. 034 UP
  with its seed and constraints, the append-only trigger (`P0001` on update and delete), the
  one-request/claim/result-per-command index (`23505`), then state-api's own store and gate driving a stop,
  its claim, its result, a duplicate result, a superseded command, a late result, history order and the gate
  text; then 034 DOWN leaving nothing (the gate then refuses because it cannot be read) and 034 UP again
  restoring the seed. The container was removed afterwards.
- Cockpit `npm test`: **102 passed, 0 failed**, including the five new wording tests (`node --test
  tests/harness-control-text.test.mjs` alone: 5 passed). `npm run build`: passed, 1 min 7 s cold and 16.9 s
  warm, with no new warnings and every chunk inside Rollup's size limit.
- No browser check: seeing the header in a browser needs a deploy, and the Vite dev server proxies to the
  running state-api, which does not serve these routes yet.

## Deploy (operator or lead, after merge)

1. Merge `claude/harness-kill-switch`.
2. Apply migration 034. `schema-init` applies pending migrations when the bounded profile comes up, so
   recreating state-api is enough; otherwise run `python ops/migrate.py up`. Check:
   `select desired_state, operator, command_id from agent_harness_control;` → one `running` row, `command_id`
   null.
3. Rebuild and recreate `state-api` and `cockpit-ui` (and `core-scorer`, if it is running) in the bounded
   profile:

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml `
     -f ops\compose.market-command.yml `
     up -d --build postgres redis market-data state-api cockpit-ui
   ```

4. Check, read-only:
   - `GET /state/agents/harness/control` → `desired.state` `running`, `host.status` `none`, `gate.open` true.
   - `GET /state/agents/harness/gate` → `{"open": true, "reason": null}`.
   - The Cockpit header shows `Agent harness · running · Stop` on every page.

## Register the host control task (not done here)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File E:\Projects\TradeSync\dashboard-overhaul-2026-09-01\tools\register-hermes-harness-control-task.ps1
Start-ScheduledTask -TaskName TradeSync-Hermes-Harness-Control
E:\Projects\TradeSync\dashboard-overhaul-2026-09-01\.venv\Scripts\python.exe tools\hermes_harness_control.py --check
```

The script refuses to replace an existing task unless `-Replace` is given, and registering starts nothing.
Within about ten seconds of the task running, `GET /state/agents/harness/control` shows `host.last_poll_at`;
the log is `dashboard-runtime\logs\hermes_harness_control.log`.

## The first real stop and start (operator)

1. Press **Stop** in the Cockpit header, give your name and a reason, and confirm.
2. Within about ten seconds the header reads `stopping…`; the gateway drains in-flight work first, so up to
   about four minutes is normal. It then reads `stopped`, and the Agents page shows the command
   (`hermes gateway stop`), its exit status, `is-active` `inactive`, and the audit rows.
3. Confirm outside TradeSync: `wsl.exe -d Ubuntu -- systemctl --user is-active hermes-gateway.service` →
   `inactive`, and `http://127.0.0.1:8642/health` refuses the connection. The Hermes cron jobs and Discord
   bots are then off, which is the point.
4. Press **Start** and confirm. The header reads `starting…`, then `running`, and the gateway answers the
   heartbeat within about fifteen seconds.
5. If the header ever warns that the gateway answers while the switch says stopped, press **Stop again**: a
   Windows logon or a WSL restart starts the enabled service, which this switch does not prevent.

## Limits and decisions

- A Windows logon (`Hermes Gateway.vbs`) or a WSL restart starts the gateway again. The switch mirrors
  `hermes gateway stop`, which does not survive a reboot either; TradeSync's own refusal does survive, and the
  header warns about the disagreement rather than re-stopping on its own.
- The host process does not run `hermes gateway start`, because that rewrites the unit file from the calling
  shell's `PATH`. If Hermes is updated and the unit falls behind, run `hermes gateway start` once from a WSL
  shell.
- Schedule and enabled fleet directives still reach `jobs.json` through the host bridge while stopped; nothing
  goes to the gateway, and the reason is recorded on the directive.
- A scheduled reading whose slot falls while stopped is recorded as skipped with the reason and is not started
  late, exactly as the schedule already treats a missed slot.
- `GET /state/agents/harness/status` (the Agents page's harness probe) and the heartbeat still reach the
  gateway while stopped: both are status reads, and they are what makes a disagreement visible.
- The ChaseOS coordination daemon is never controlled here, and the UI and this record say so.
