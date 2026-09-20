# Thesis evidence, pattern and calibration research — 17 September 2026

## Product decisions applied now

1. **Chart structure must be algorithmic and testable.** Lo, Mamaysky and Wang formalised technical pattern recognition with non-parametric methods rather than relying on visual anecdotes. TradeSync therefore labels breakout, breakdown, compression and range direction with deterministic candle rules, and calls each one a *candidate* until its conditional forward record is measured.
2. **Historical frequencies are not automatically forecast probabilities.** The player reports matching-state outcome frequencies with an explicit range threshold and independent-window count. It does not rename the existing weighted score as a probability.
3. **Probability claims require time-gated calibration.** The planned promotion gate uses unseen later periods, Brier score/reliability plots and prediction intervals. The interface already separates descriptive history from calibrated forecasts.
4. **Search breadth creates overfitting risk.** Adding more patterns, sources and parameter variants increases the probability of selecting a lucky backtest. Candidate families therefore need a registered specification, held-out result and later forward evidence before they can affect scoring.
5. **News is context, not direction by assertion.** Research finds that returns around news depend on content and context. TradeSync keeps calendar/news evidence attributable and measures event reactions rather than assigning a geopolitical headline an arbitrary directional weight.

## Current deterministic rules

- Breakout candidate: latest close above the preceding 24-bar high.
- Breakdown candidate: latest close below the preceding 24-bar low.
- Compression candidate: latest 12-bar high-low width is at most 65% of the preceding 24-bar width.
- Otherwise: report the sign and size of the latest 12-bar move while stating that price remains inside the prior range.
- Three-state historical outcome: *range* when absolute forward return is at most half the comparable sample's median absolute return; otherwise up or down by threshold sign.

These are display-only in this release. A future registered experiment must test each family by symbol and horizon, after estimated costs, against an unconditional/base-rate comparator.

## Primary sources

- Hyperliquid, Info endpoint (official supported candle intervals and limits): https://hyperliquid.gitbook.io/Hyperliquid-docs/for-developers/api/info-endpoint
- Lo, Mamaysky and Wang, *Foundations of Technical Analysis* (NBER Working Paper 7613): https://www.nber.org/papers/w7613
- Bailey et al., *The Probability of Backtest Overfitting*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- FinBench 2026, time-gated probability calibration and prediction intervals: https://arxiv.org/abs/2607.16229
- Baker, Bloom, Davis and Sammon, *What Triggers Stock Market Jumps?* (NBER Working Paper 24430): https://www.nber.org/papers/w24430
