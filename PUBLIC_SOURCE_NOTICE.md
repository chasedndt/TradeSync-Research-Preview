# TradeSync public-source notice

TradeSync is visible on GitHub so its architecture, safety boundaries and research workflow can be inspected. First-party TradeSync software is licensed under [FSL-1.1-MIT](LICENSE.md), a Fair Source, source-available licence. It is **not an OSI-approved open-source licence**. Each version becomes available under MIT on the second anniversary of the date that version is made available.

The software licence covers first-party TradeSync code and documentation only. It does not grant rights to third-party data, provider content, trademarks, private connectors, credentials or operator-owned artifacts. See [third-party notices](THIRD_PARTY_NOTICES.md) for the upstream boundaries and official terms links.

## What may be shown publicly

- first-party TradeSync source and documentation;
- synthetic fixtures and schemas;
- first-party screenshots of the TradeSync interface that do not contain credentials, private research text, wallet secrets or operator-only identifiers;
- high-level architecture and local verification results with their scope stated accurately;
- links to the upstream providers and open-source packages TradeSync interoperates with.

## What is not granted or redistributed

- market data, screenshots, charts or article text owned or licensed by a provider;
- private ChaseOS graph snapshots, vault material, prompts or governed writebacks;
- Hermes job definitions, prompts, outputs or usage records beyond deliberately sanitized UI proof;
- Discord messages, channel content, TradingView content, Pine source, webhook secrets or member-only research;
- credentials, API keys, wallet material, signing authority, runtime environments, database dumps or logs;
- any right to use a provider's API, trademarks or data beyond that provider's own terms.

## Provider boundary

The source code can describe an adapter without redistributing the provider's data or granting downstream access rights.

| Provider or source | TradeSync role | Public-release rule |
|---|---|---|
| Hyperliquid | Authoritative public market source and sole future venue | Source adapters may be shown. Do not package captured market-data archives until the specific data rights are confirmed. The official Python SDK is MIT-licensed, but that licence covers the SDK, not every data use. |
| TradingView | Pine alerts and webhook ingress | Do not redistribute TradingView market data, chart captures, or provider content. Public material may describe the webhook contract using synthetic payloads. |
| FRED | Optional macro context, disabled by default | Keep keys private. Do not publish cached or archived FRED content. Any public application must carry the required FRED notice and comply with series-owner restrictions. |
| CoinGecko | Context-only spot reference | Do not resell or redistribute raw data. Public display requires the applicable plan, attribution and/or permission. |
| DefiLlama | Context-only protocol reference | Do not republish or commercially exploit data without permission under the current terms. |
| Binance and Bybit | Context-only cross-venue/liquidation observations | Do not repackage, resell or commercially exploit API service data. Keep these feeds optional and outside distributable datasets. |
| GDELT and other research sources | Context-only evidence | Publish only derived first-party analysis with required attribution and links; do not mirror source content. |

Provider terms change. Review the official terms again before a public hosted demo, downloadable data bundle, paid product, or open-source licence is released.

## Current release decision

The first-party source and documentation may be presented publicly as a
**source-available research preview** under FSL-1.1-MIT. Operator-captured replay
data and reports are excluded from the current tree and ignored by default.
Only synthetic fixtures may be committed to the public repository.

TradeSync must not be called fully open source. A release is publishable only
after all of the following pass for the exact revision:

1. first-party code is separated from provider data and private connectors;
2. all third-party licences and notices are inventoried;
3. real captured datasets and derived real-data reports are absent;
4. the FSL-1.1-MIT licence and exclusions are included; and
5. a fresh history-aware secret scan and release-package review pass.

Because earlier public Git history may still contain files removed from the
current tree, a clean current revision does not prove that all historical
objects are clear. Do not advertise the repository as history-sanitized until
an explicit history review or approved history rewrite is complete.

This notice records a conservative engineering boundary, not legal advice.
