# Third-party notices and provider boundary

TradeSync's [FSL-1.1-MIT licence](LICENSE.md) applies only to first-party
TradeSync source and documentation. It does not replace, extend or sublicense
the licences and terms that apply to dependencies, services, data, trademarks
or operator-owned integrations.

## Software dependencies

TradeSync uses third-party packages through the Python, npm and Cargo package
managers. Their names and pinned versions are recorded in the repository's
dependency and lock files. Each package remains under its own upstream
licence. Preserve the notices supplied by those packages when redistributing a
build that contains them.

The repository does not intentionally vendor a third-party provider SDK or
copy provider source under the TradeSync licence. The official Hyperliquid
Python SDK is MIT-licensed, but that licence covers the SDK implementation; it
does not grant rights to redistribute every dataset obtained through a
service.

## External services and data

TradeSync interoperates with external services through bounded adapters. No
provider account, API entitlement or data licence is transferred with this
repository.

| Provider or project | Upstream terms or licence | TradeSync distribution boundary |
| --- | --- | --- |
| Hyperliquid | <https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/LICENSE.md> | Public adapters and synthetic fixtures only; no captured market-data archive is bundled. |
| TradingView | <https://www.tradingview.com/policies/> | Synthetic webhook examples only; no TradingView chart, market dataset, Pine source or paid content is redistributed. |
| FRED | <https://fred.stlouisfed.org/legal/terms/> | Optional operator-supplied key; no cached FRED dataset is bundled. Series-owner restrictions still apply. |
| CoinGecko | <https://www.coingecko.com/en/api/enterprise/data-license> | Context adapter only; no raw-data resale or redistribution right is granted here. |
| DefiLlama | <https://defillama.com/terms> | Context adapter only; downstream users must comply with the current service terms. |
| Bybit | <https://www.bybit.com/en/help-center/article/API-Terms> | Optional context integration only; no API service data is packaged for redistribution. |

Provider terms can change. An operator must review the current terms,
attribution rules, plan limits, caching limits and redistribution rights before
enabling an adapter, publishing a hosted demo or distributing generated data.

## Bring your own access

Where an account, key or webhook secret is required, each operator must create
their own provider access and store it outside the repository. TradeSync does
not ship, broker or generate credentials. See
[`docs/providers/BRING_YOUR_OWN_CREDENTIALS.md`](docs/providers/BRING_YOUR_OWN_CREDENTIALS.md).

## Trademarks and private integrations

Provider names are used only to identify interoperability. No endorsement or
trademark licence is implied. Private ChaseOS materials, Hermes prompts and
outputs, operator research, browser sessions, wallet material, credentials and
runtime databases are not part of the public research preview.

This notice is a conservative engineering boundary, not legal advice.
