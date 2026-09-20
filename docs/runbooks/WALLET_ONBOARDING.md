# Wallet onboarding and authority boundaries

TradeSync's wallet manager is an **address connector**, not a key vault. It is
designed to make adding a Hyperliquid account feel familiar while keeping the
credential boundary in the wallet application that was built to protect it.

## Add an account

1. Start TradeSync from the desktop shortcut. It opens the normal Chrome
   `Default` profile until Phantom is installed; on later launches it selects
   the standard Chrome profile where Phantom is present. It never borrows the
   automated StrikeZone browser profile.
2. Select **Connect wallet** in TradeSync's header. If Phantom is not detected,
   use the official install link shown in the modal, install and unlock Phantom,
   then reopen the wallet menu. If an existing account must be recovered, enter
   its 12/24-word recovery phrase or private key **inside Phantom only**.
3. Approve the request to share the selected public EVM address. TradeSync asks
   for `eth_requestAccounts`; it does not request a signature or transaction.
4. TradeSync records the public address, a label, connector type, operator name,
   timestamps, and an audit event. The account can then be selected for
   Hyperliquid balance, position, order, and fill visibility.

The database schema has no column for a recovery phrase, private key, signature,
or wallet session. A registered address is not proof of ownership and grants no
execution authority.

## Why there is no TradeSync phrase/key field

A recovery phrase or main-wallet private key controls the funds. Asking for it
inside a local dashboard would unnecessarily turn every browser dependency,
log, screenshot, database backup, and application bug into a custody risk.
Hyperliquid's own safety guidance says not to share a seed phrase or private key
with a website. Import belongs inside the trusted wallet; TradeSync receives the
public address afterwards.

## Later automation

Hyperliquid automation uses a separate agent/API wallet approved by the main
account. The intended flow is:

`main wallet -> approve revocable agent wallet -> isolated signer -> single-use approval -> risk recheck -> order intent -> venue receipt -> reconciliation`

Use one agent wallet per process. TradeSync must never provision the main wallet
into the signer. The current signer remains disabled; no live order can be sent.

Primary references:

- [Hyperliquid API wallets and nonces](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- [Hyperliquid exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
- [Hyperliquid signing guidance](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/signing)

## Router token is unrelated to a wallet

`ALERT_ROUTER_PRODUCER_TOKEN` is a random local bearer credential used only by
approved TradeSync services that submit notification envelopes to the Rust
alert router. It cannot sign, withdraw, bridge, approve, or place a trade. It is
kept in the runtime environment and is never shown by the Cockpit.
