# Security remainder — 15 September 2026

Branch `claude/security-remainder`, from `codex/2026-09-01-dashboard-overhaul` at `566fea9`.
The findings the [local access review](../security/2026-09-15_local-access-review.md) left
open: M3, M4 and L1 to L7. L8 stays with the harness branch.

- Source, compose, tests and documents only. Nothing was deployed, and no container, network,
  tunnel, Cloudflare setting or secret was changed.
- No secret was opened. The filled tunnel config was read for its structural keys alone, to
  confirm the one ingress rule still resolves; the credentials file was not opened.
- Paper mode is untouched: `DRY_RUN=true`, `EXECUTION_ENABLED=false`, no key, signing off.

## Commits

| Commit | Change | Finding |
|---|---|---|
| `20323f5` | cloudflared joins `pine-ingress` (internal, with state-api) and `pine-egress`, never `default` | M3 |
| `439b1cc` | `tradesync_core.service_tokens`: both caller tokens, their headers, and the fail-closed ASGI guard | M4, L6 |
| `1f5f218` | exec-hl-svc's image builds from the repository root and installs `tradesync_core` | M4, L6 |
| `2f4bda9` | signer-svc refuses `/sign` without `SIGNER_CALLER_TOKEN` and reports the token's state | M4 |
| `f7afb09` | signer-svc joins only the internal `signer` network, with exec-hl-svc and state-api | M4 |
| `e782a77` | exec-hl-svc's signer client sends that token, or makes no call at all | M4 |
| `9da8585` | exec-hl-svc's order route requires `EXEC_HL_CALLER_TOKEN`; state-api sends it | L6 |
| `ad10daf` | The webhook checks the TradingView source, believing `CF-Connecting-IP` only from the connector | L2 |
| `072c3ce` | state-api answers only known Host names; the tunnel hostname on the webhook path only | L1 |
| `12acf08` | Change bodies bounded at 1 MiB, with the webhook's 16 KB and two measured 4 MiB exceptions | L5 |
| `56308cb` | Server errors answer with a trace id and log the exception's type | L4 |
| `595cef7` | discord-reader redacts secret-shaped text before posting | L7 |

Documents changed with them: this record, the review's statuses and its L3 rule, the port and
tunnel consumers, the mutating routes, `ops/ingress/waf-allowlist.md` and the Cloudflare profile.

## What changes at deploy

### Networks (M3, M4)

| Container | Networks after | Before |
|---|---|---|
| cloudflared | `pine-ingress` (internal, fixed `172.29.53.10`), `pine-egress` | `default` |
| signer-svc | `signer` (internal) | `default` |
| state-api | `default`, `pine-ingress`, `signer` | `default` |
| exec-hl-svc | `default`, `signer` | `default` |
| every other service | `default` | `default` |

Compose creates `tradesync-full_pine-ingress` (172.29.53.0/28, with addresses handed out from
172.29.53.0/29 so the connector's stays free), `tradesync-full_pine-egress` and
`tradesync-full_signer`. On 15 September the engine used 172.17.0.0/16 and 172.18.0.0/16, and
the host 192.168.0.0/24, so that range is free. Published ports still go through `default`,
the only network of state-api's with a route out, so the loopback bindings do not move.

### state-api

- A request whose Host is not `127.0.0.1`, `localhost` or `state-api` gets 400; the tunnel
  hostname is served on `/webhook/tradingview` only (L1).
- `POST /webhook/tradingview` refuses every source but TradingView's four addresses with 403,
  before the secret, the database or the body. A local `curl` to that path now answers 403
  where it answered 401 (L2).
- A change body over 1 MiB gets 413 before routing; the webhook keeps 16 KB, and the fleet
  snapshot and StrikeZone ingest allow 4 MiB (L5).
- A 500 that used to repeat its exception answers `{"detail": "Internal error…", "trace_id"}`,
  and the log records the type under that id (L4).
- Orders routed to exec-hl-svc carry `X-Exec-Caller-Token` once it is configured (L6).
- uvicorn runs with `--no-proxy-headers`, so a forwarded address is never the client address.

### signer-svc and exec-hl-svc (M4, L6)

- `/sign` answers 503 while `SIGNER_CALLER_TOKEN` is unset and 401 without the header, and
  `caller_token` appears in `/healthz`, `/signer/status` and the state-api status route. No key
  is loaded and signing stays off.
- exec-hl-svc is not running (profile `paper-exec`). When it is next started its order route
  refuses everything until `EXEC_HL_CALLER_TOKEN` is set, and its image must be rebuilt.

### Unchanged

The Cockpit, market-data, fusion-engine and core-scorer are untouched; core-scorer installs the
shared library but nothing it uses changed. The host bridges, their schedules and what they post
are unchanged. None of the 200 newest stored Discord payloads would have been altered by the
redaction, so Intake keeps its current shape.

## New environment variables

| Variable | Read by | Unset means | Who sets it |
|---|---|---|---|
| `EXEC_HL_CALLER_TOKEN` | state-api, exec-hl-svc | exec-hl-svc refuses every order | operator, `tools\set-runtime-secret.ps1` |
| `SIGNER_CALLER_TOKEN` | exec-hl-svc, signer-svc | the signer refuses every signature | operator, `tools\set-runtime-secret.ps1` |
| `STATE_API_TUNNEL_HOSTS` | state-api | the tunnel hostname is not served | compose default: `tradesync-pine.chaseintech.com` |
| `TRADINGVIEW_INGRESS_PEERS` | state-api | no peer's `CF-Connecting-IP` is believed | compose default: `172.29.53.10` |
| `STATE_API_ALLOWED_HOSTS` | state-api | only the three local names | rollback only (`*` switches the check off) |
| `TRADINGVIEW_SOURCE_CHECK` | state-api | the source check is enforced | rollback only (`off`) |
| `STATE_API_MAX_BODY_BYTES` | state-api | 1 MiB | rollback only |

Both tokens must differ from each other and from `STATE_API_OPERATOR_TOKEN`, and each must be
at least 32 characters. Shorter is treated as a mistake: the service refuses everything and says so.

## Verification

Python suites through the project venv, `tools\run_tests.py`, at `595cef7`:

| Suite | Result |
|---|---|
| root | 1,053 passed, 17 deselected, 2 warnings, 49 subtests |
| state-api | 459 passed |
| market-data | 160 passed |
| exec-hl-svc | 11 passed |
| signer-svc | 14 passed |

The Cockpit is untouched, so it was not rebuilt. `docker compose config`, rendered against a
dummy env file rather than runtime.env, shows the networks and the fixed address above and each
caller token in only the two services on either side of its boundary.

## Deploy steps

1. Merge into `codex/2026-09-01-dashboard-overhaul` and update the main checkout,
   `E:\Projects\TradeSync\dashboard-overhaul-2026-09-01`: the scheduled bridges run from there.
2. Set the two caller tokens without displaying them (Windows PowerShell 5.1). Paste into each
   prompt as it opens, and never put either on a command line:

   ```powershell
   foreach ($name in 'EXEC_HL_CALLER_TOKEN', 'SIGNER_CALLER_TOKEN') {
     $bytes = New-Object byte[] 36
     [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
     Set-Clipboard -Value ([Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_'))
     powershell -ExecutionPolicy Bypass -File tools\set-runtime-secret.ps1 -Name $name
   }
   Set-Clipboard -Value ' '
   ```

3. Rebuild and recreate state-api and discord-reader. This also creates the new networks and
   puts state-api on them:

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml `
     up -d --build state-api discord-reader
   ```

   Do not add `--remove-orphans`: cloudflared and signer-svc are not in these two files.
4. Recreate cloudflared so it leaves `default`. Step 3 first, so state-api is already on
   `pine-ingress` when the connector moves; the tunnel is down only while it reconnects:

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml -f ops\compose.ingress.yml `
     up -d --no-deps cloudflared
   ```

5. Rebuild and recreate signer-svc:

   ```powershell
   docker compose `
     --env-file E:\Projects\TradeSync\dashboard-runtime\runtime.env `
     -f ops\compose.full.yml -f ops\compose.market-command.yml -f ops\compose.signer.yml `
     up -d --build --no-deps signer-svc
   ```

6. exec-hl-svc stays stopped. When the `paper-exec` profile is next used, build it
   (`up -d --build exec-hl-svc`): its image now installs the shared library.
7. Cloudflare: create the rate limiting rule written out as L3 in the review. Nothing else
   there changes.

## Post-deploy checks

In order. Checks 1 to 3 decide whether to roll the networks back.

1. **Networks.**

   ```powershell
   foreach ($c in 'cloudflared', 'state-api', 'signer-svc') {
     docker inspect "tradesync-full-$c-1" --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}'
   }
   ```

   cloudflared shows `tradesync-full_pine-egress` and `tradesync-full_pine-ingress=172.29.53.10`
   and no `default`; state-api shows `default`, `pine-ingress` and `signer`; signer-svc shows
   `signer` alone.
2. **Loopback unchanged.** `docker port tradesync-full-state-api-1` still shows
   `8000/tcp -> 127.0.0.1:8000`; `curl.exe -s http://127.0.0.1:8000/healthz` returns
   `{"ok":true}`; `curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:3000/api/state/health`
   returns `200`, and the Cockpit loads and draws.
3. **Host check.** Both return `400`:

   ```powershell
   curl.exe -s -o NUL -w "%{http_code}\n" -H "Host: rebind.example" http://127.0.0.1:8000/healthz
   curl.exe -s -o NUL -w "%{http_code}\n" -H "Host: tradesync-pine.chaseintech.com" http://127.0.0.1:8000/state/health
   ```

4. **Webhook source.** Both return `403` with `source_not_allowed`; the second shows a local
   caller cannot claim to be TradingView by setting the header:

   ```powershell
   curl.exe -s -X POST -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8000/webhook/tradingview
   curl.exe -s -X POST -H "CF-Connecting-IP: 52.89.214.238" -d "{}" http://127.0.0.1:8000/webhook/tradingview
   ```

5. **Body limit.** Returns `413`:

   ```powershell
   $probe = 'E:\Projects\TradeSync\dashboard-runtime\logs\body-probe.bin'
   [IO.File]::WriteAllBytes($probe, (New-Object byte[] (2MB)))
   curl.exe -s -o NUL -w "%{http_code}\n" -X POST --data-binary "@$probe" http://127.0.0.1:8000/state/access-probe
   Remove-Item $probe
   ```

6. **The signer, through its new network.**

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/state/execution/signer-status |
     Select-Object reachable, available, key_loaded, signing_enabled, caller_token
   ```

   `reachable True`, `available False`, `key_loaded False`, `signing_enabled False`,
   `caller_token required`. Reachable is the proof that state-api and the signer share `signer`.
7. **The fleet bridge still posts.** Within five minutes the snapshot time is later than the
   deploy and the log ends with `[FleetBridge] snapshot:`:

   ```powershell
   (Invoke-RestMethod http://127.0.0.1:8000/state/fleet/jobs).snapshot_at
   Get-Content E:\Projects\TradeSync\dashboard-runtime\logs\hermes_fleet_bridge.log -Tail 3
   ```

   `hermes_output_bridge.log` and `strikezone_quant_bridge.log` show passes with no HTTP error,
   and new `chaseos` items keep reaching Intake.
8. **Containers.** None of these shows a line newer than the deploy, apart from the probes above:

   ```powershell
   docker logs --since 30m tradesync-full-discord-reader-1 2>&1 | Select-String "submit failed"
   docker logs --since 30m tradesync-full-core-scorer-1 2>&1 | Select-String "ask HTTP"
   docker logs --since 30m tradesync-full-state-api-1 2>&1 | Select-String "host refused|body refused"
   ```

9. **Tunnel.** `docker logs --since 30m tradesync-full-cloudflared-1` shows registered
   connections and no `Unable to reach the origin`. A workstation request to
   `https://tradesync-pine.chaseintech.com/webhook/tradingview` still returns Cloudflare `403`.
10. **The webhook still answers through the tunnel path.** The next genuine TradingView alert,
    or one the operator triggers from TradingView, reaches Intake: in
    `GET /state/quarantine?source=tradingview&limit=1` the newest `received_at` is later than
    the deploy, and

    ```powershell
    docker logs --since 30m tradesync-full-state-api-1 2>&1 | Select-String "tradingview alert refused"
    ```

    shows no `via tunnel` line. Until an alert has landed, the Pine path is not accepted.

## Rollback

| What to undo | How |
|---|---|
| Host check | `STATE_API_ALLOWED_HOSTS=*` in runtime.env, then recreate state-api |
| Webhook source check | `TRADINGVIEW_SOURCE_CHECK=off`, then recreate state-api |
| Body limits | `STATE_API_MAX_BODY_BYTES` to a larger value, then recreate state-api |
| Tunnel network | revert `20323f5` and the compose part of `ad10daf`, then repeat deploy steps 3 and 4 |
| Signer network and token | revert `f7afb09` and `2f4bda9`, then rebuild signer-svc |
| Everything | revert the merge, then repeat steps 3 to 5 |

An alert refused `via tunnel` in check 10 means the connector's address is not the one compose
fixes: use the source-check lever, then compare check 1's address with
`TRADINGVIEW_INGRESS_PEERS`.

## Still open

1. L8, the harness client's proxy variables: the harness branch owns it.
2. The L3 rate limiting rule, to create in Cloudflare.
3. H3: switching on `STATE_API_OPERATOR_TOKEN`, with the procedure in the earlier record.
4. Status readouts that still carry exception text (`agent_connector.py`, `hermes_link.py` and
   the integration pipeline probes). They report why an optional connector is offline.
5. `run_dev.py:18` and `docs/RUNBOOKS.md:79` still start `app.main:app`, which has no guards.
   The container is unaffected.
6. `docs/README.md` is not updated here, to avoid colliding with the parallel branches; add the
   index line at merge.
