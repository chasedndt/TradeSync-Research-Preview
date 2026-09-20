# Bring your own provider credentials

TradeSync does not ship, share, broker or generate provider credentials for
downstream users. Every operator must create their own provider account where
one is required, accept the provider's current terms, choose the minimum
permissions needed, and store secrets outside the repository.

## Public research-preview profile

| Source | Account or key | Runtime setting | Authority |
|---|---|---|---|
| Hyperliquid public market API | None for the public read endpoints currently used | `HYPERLIQUID_INFO_URL` only when overriding the official endpoint | Authoritative market data; never approval authority |
| CoinGecko context feed | None for the current public endpoint | `COINGECKO_CONTEXT_ENABLED=true` | Context only |
| DefiLlama context feed | None for the current public endpoint | `DEFILLAMA_CONTEXT_ENABLED=true` | Context only |
| Binance public reference endpoints | None for the current public endpoints | No secret variable | Context only |
| FRED | Create your own free key at `fred.stlouisfed.org` | `FRED_CONTEXT_ENABLED=true`, `FRED_API_KEY=<your key>` | Context only |
| TradingView webhook | Create your own TradingView access where needed and generate a unique local secret | `TRADINGVIEW_WEBHOOK_SECRET=<new random secret>` | Untrusted intake; never a signal or approval |
| ChaseOS, Strike Zone, Hermes/Ollama | Operator-owned local systems | Connector-specific local settings; `CHASEOS_HOME` for a private ChaseOS root | Optional advisory evidence only |

## Secret rules

1. Copy the documented variable names into a private runtime environment under
   your control. Do not create a tracked `.env` file.
2. Generate a new webhook secret for each installation. Do not copy the example
   placeholders or another operator's value.
3. Never place a wallet private key, seed phrase, exchange trading key, or
   signing token in this repository. The public profile is paper-only with
   `EXECUTION_ENABLED=false` and `DRY_RUN=true`.
4. Use read-only provider scopes when a provider supports them. Do not grant
   withdrawal, transfer, signing, or live-order permissions to research feeds.
5. Review the provider's current licence, attribution, rate-limit, caching and
   redistribution terms before enabling an adapter.
6. Rotate a key immediately if it appears in a terminal capture, screenshot,
   log, issue, commit, build artifact or shared support message.

## What the repository intentionally does not contain

- API keys, OAuth tokens, session cookies or provider accounts;
- TradingView Pine source or paid/member-only content;
- wallet addresses tied to an operator, private keys or signing authority;
- private ChaseOS graph snapshots, Hermes prompts/jobs, or local vault paths;
- captured provider datasets, account history, database dumps or live logs.

The provider matrix in [`MARKET_PROVIDER_MATRIX.md`](MARKET_PROVIDER_MATRIX.md)
records the current role of each source. A configured feed never inherits
scoring, approval or execution authority merely because it is healthy.
