# Security policy

## Supported scope

TradeSync is a research-stage, paper-first workstation. The current supported security boundary is the repository's default local profile with:

- `DRY_RUN=true`;
- `EXECUTION_ENABLED=false`;
- loopback-bound application ports;
- no wallet private key or signer loaded;
- optional agents treated as advisory and quarantined;
- secrets supplied from the private runtime environment, never this repository.

Live trading, hosted multi-user operation and public internet exposure beyond the bounded TradingView webhook are not supported release states.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose credentials, wallets, private research or infrastructure. Use GitHub's private vulnerability reporting for `chasedndt/TradeSync` when available, or contact the repository owner privately through the verified contact route on `chaseintech.com`.

Include the affected revision, entrypoint, reproduction steps, impact, and whether the issue is reachable in the default paper-only profile. Do not place real keys, tokens, wallet material or private ChaseOS/Hermes content in the report.

## Public-release hygiene

Before any release or public proof package:

1. run `python tools/public_release_audit.py`;
2. create a history-free candidate with `python tools/export_public_preview.py <empty-E-drive-directory>` when the existing repository history is not approved for release;
3. verify GitHub secret-scanning alerts are clear;
4. review `PUBLIC_SOURCE_NOTICE.md` and current provider terms;
5. use only sanitized first-party screenshots;
6. keep execution disabled and state verification scope without profitability claims.

The public research preview never includes shared credentials. Every operator
must provision their own keys and secrets as described in
[`docs/providers/BRING_YOUR_OWN_CREDENTIALS.md`](docs/providers/BRING_YOUR_OWN_CREDENTIALS.md).
Do not request, post, or commit provider keys in an issue, discussion, screenshot,
sample configuration, or support exchange.
