# 2026-09-16 — market-data: `main.py` split into one responsibility per module

Integration branch `codex/2026-09-01-dashboard-overhaul`, commit `71a4219`. Source only:
**nothing deployed**, no migration, no container rebuilt, and no runtime behaviour changed.
Paper mode untouched (`DRY_RUN=true`, `EXECUTION_ENABLED=false`).

## Why

`services/market-data/app/main.py` had grown to 1,133 lines holding four unrelated jobs at once:
configuration and shared state, six polling loops, the enrichment applied before a snapshot is
stored, and the whole read surface. The repository rule is one responsibility per file, and
anything past ~300 lines is split as part of the current task.

## What moved

Every line was moved **unchanged** — same code, same comments, same docstrings. No behaviour was
edited in this commit.

| Module | Lines | Holds |
|---|---|---|
| `app/main.py` | 142 | composition root: the app, the lifespan, the routers |
| `app/runtime.py` | 84 | configuration and the state the loops and routes share |
| `app/pollers.py` | 188 | the venue loops: context, order book, funding history |
| `app/reference_pollers.py` | 171 | the Tier B references: Coinbase spot, Binance funding and OI, GDELT tone |
| `app/enrichment.py` | 132 | what is attached to a snapshot before it is stored |
| `app/health_routes.py` | 114 | liveness, readiness, service status |
| `app/market_routes.py` | 196 | snapshots, admitted features, history, alerts, timeseries |
| `app/chart_routes.py` | 278 | candles, canvas context, books, liquidations, open interest |

The venue loops and the external reference loops are separate files on purpose: their standing
differs. Hyperliquid is authoritative; every source in `reference_pollers.py` is context whose
failure is logged and skipped so it can never disturb venue observation.

## What was deliberately kept identical

- **The ASGI target.** `services/market-data/Dockerfile` still runs `app.main:app`; `app` is still
  created in `app/main.py`.
- **The log name.** `runtime.py` names its logger `app.main`, so existing log lines are unchanged.
- **The shared state is shared by reference.** `providers` and `background_tasks` are the same list
  objects the lifespan fills and the routes read; the three reference dictionaries likewise.
- **The one import surface tests use.** `FEATURE_HISTORY_WINDOWS_MS` and
  `DEFAULT_FEATURE_HISTORY_WINDOW_MS` are defined in `market_routes.py` and re-exported from
  `app.main`, which is where `tests/test_feature_extractor.py` reads them.

## Verification

- **Route table identical:** 24 routes before the split, 24 after, with the same paths and methods
  (`/healthz`, `/readyz`, `/status`, `/snapshots`, `/snapshot/{venue}/{symbol}`,
  `/features/…`, `/feature-histories/…`, `/feature-history/…`, `/alerts`,
  `/timeseries/…`, `/candles/…`, `/context/…`, `/depth/…`, `/book-history/{symbol}`,
  `/liquidation-context/{symbol}`, `/depth-books/{symbol}`, `/liquidation-events/{symbol}`,
  `/open-interest-history/binance/{symbol}`, `/funding-history/hyperliquid/{symbol}`,
  `/feeds/status`, plus the four FastAPI documentation routes).
- **market-data suite:** 160 passed.
- **Every Python suite** was run again on the merged tree after the split.

## Not done here

The equivalent split of `services/state-api/app/main.py` (3,433 lines) is still outstanding. It is
deliberately left until the parallel branches have merged, because splitting a file two active
branches are editing would turn every one of their commits into a conflict.
