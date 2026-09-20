# Thesis horizon story and evidence probabilities — 17 September 2026

## Repo-truth delta

The first interactive player changed charts with the narration, but the edition archive crowded the thesis header, playback stopped at four intervals, captions were not navigable, and there was no explicit up/range/down historical outcome mix. The optional regeneration reason was stored but did not influence Hermes. Phantom absence looked like a broken connect control because the fallback opened a website without explaining that the browser extension was missing.

## Implemented

- Market Thesis now keeps up to 50 frozen editions in a collapsed, scrollable archive. Mission Control no longer duplicates that archive.
- The real chart story sits immediately after the current thesis summary, before calendar, briefing and market cards.
- Playback covers `1w`, `1d`, `12h`, `8h`, `4h`, `2h` and `1h` Hyperliquid candles.
- Audio timing drives clickable captions, keyword jumps, market chapters and timeframe changes.
- The chart displays deterministic structure candidates and an optional price-aligned entry/target/invalidation overlay. Both are explanatory only and create no order, drawing or score.
- Each chapter has a live horizon lens. It reports matching-state historical up/range/down frequencies and the number of non-overlapping windows. Range is explicitly defined as an absolute return within half the comparable sample's median absolute return.
- Mission Control surfaces weekly and monthly BTC structure plus the same historical outcome mix when available.
- The optional regeneration field is now a focus question. It is passed to Hermes with measured facts; the prompt requires Hermes to say when those facts cannot answer it and forbids invented web research.
- Phantom's missing-extension state now explains why no popup appeared, uses the canonical mark at useful size, and offers separate official-install and re-detect actions. TradeSync still never accepts wallet secrets.

## Research boundary

The structure labels are systematic descriptions, following the principle that chart patterns need algorithmic definitions before they can be tested. They remain candidates until registered forward tests establish conditional performance. The outcome mix is historical-state evidence, not a calibrated forecast. Forecast calibration and Brier scoring remain a later evidence gate; backtest-overfitting controls remain mandatory before any strategy promotion.

Research note: [deterministic structure, calibration and overfitting controls](../research/2026-09-17_thesis-evidence-and-calibration.md).

## Verification

- `python -m pytest tests/test_horizon_outlook.py services/market-data/tests/test_candles.py -q` — 24 passed.
- `npm test -- --run` — 254 passed.
- `npm run build` — passed.
- Docker rebuilt and recreated `market-data`, `state-api` and `cockpit-ui`; State API returned healthy with PostgreSQL answering.
- Live BTC one-week matching-state outcome mix returned the new explicit rule and non-null up/range/down shares.
- Hyperliquid returned real `2h` and `1w` candles through the local market-data route.
- Desktop and 390 px rendered evidence: `E:\Visual QA\TradeSync Visual QA\Current Reviews\2026-09-17-thesis-horizon-playback`.

## Untouched boundaries and remaining acceptance

- No wallet secret, signature, live order, DNS, provider account or external deployment was changed.
- The probability mix is not a promise of direction and does not affect scoring.
- A physical Phantom extension must be installed/unlocked in the launcher-selected Chrome profile before its native popup can be accepted.
- Real speaker playback and an end-to-end click-through remain operator-visible browser acceptance; source and render QA cannot prove audible hardware output.
- Profitability remains unproven. Strategy promotion still requires registered forward evidence after costs.
