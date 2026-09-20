# Entry-evidence comparisons — declared before measuring, and nothing selected

Status: **research only.** No weight, rule, catalog entry or permission changed, and nothing
here is a strategy. Read it as a measurement report on evidence TradeSync already collects.

## The gap this closes

A managed paper entry freezes nine items of evidence and proves that none of them was observed
or received after the entry. Exactly one of those items has ever been measured against what
happened next: the Hyperliquid book-history sample, in the frozen
[book-alignment ablation](2026-09-14_source-comparison-v1.md). Resting liquidity, liquidations
received, the open-interest change, funding and the timeframe measurement were captured and
never asked to justify themselves.

## The comparisons, fixed before they were run

Six readings, each in both polarities, at every horizon: 36 cells in one family, declared in
`tradesync_core/entry_evidence_family.py` with a SHA-256 over the declaration
(`entry-evidence-ablation-v1`, `08b8c2f8…`). Both polarities are declared because a context can
be usefully contrarian, and testing for that costs an adjustment rather than a decision.

| Reading | Unit | Threshold | What passing it is supposed to mean |
|---|---|---|---|
| Resting liquidity balance near price | share of displayed notional | 0.2 | depth leaning the call's way has less resting supply to absorb it |
| Largest resting wall behind against in front | share of the two walls | 0.2 | a wall behind supports the entry; a larger one in front is what the move must clear |
| Liquidations received in the hour before | share of liquidated notional | 0.2 | forced exits push price the call's way — inverted, they mark exhaustion |
| Open-interest change over that hour | percent | 0.0 | positions being opened mark conviction — inverted, positions closing mark it ending |
| Funding the position would receive | bps an hour | 0.0 | being paid to hold marks the crowded side as the other one |
| Measured timeframe lean | −1, 0, +1 | 1.0 | a lean agreeing with the call trades with the timeframe, not against it |

The balance thresholds are the frozen v1 ablation's 0.2, carried over rather than chosen here;
where a reading has no natural scale the rule is its sign. A trade is kept when the reading times
the polarity is at least the threshold. **Missing context abstains and is counted separately; it
is never read as a zero.**

## What is tested, and what is only reported

Two numbers come out of each split and they answer different questions:

- the **paired difference per original opportunity** (the frozen v1 metric): both means divide by
  the same original count, and a skipped trade contributes zero to the filter;
- the **contrast**: the mean net result of kept trades minus the mean of skipped ones.

After costs the signal's mean result is negative. Any filter that skips enough trades therefore
raises the paired difference *for that reason alone*, with no selection whatsoever. Only the
contrast separates a context that sorts good calls from bad from one that merely trades less, so
**the contrast is the tested quantity** and the paired difference is reported beside it.

The contrast's error is measured, not assumed: a block bootstrap over whole time blocks one
horizon long, every symbol kept together inside a block, against a textbook difference-in-means
error whose counts are deflated to the measured share of non-overlapping windows with symbols
pooled. The larger of the two is used. Cells are corrected together with Holm
(`tradesync_core/multiple_testing.py`), the hold-out is the newest 30% chronologically, and costs
are the repository's stated round trip: 0.09% fees, 0.02% spread, 0.01% slippage, 0.12% in all.

Verdicts are kept apart and never collapsed: `detectable`, `selects` (Holm-adjusted, z ≥ 2),
`economic` (selects *and* the kept trades are positive after costs), `held_out`.

## The population: recorded calls, not paper positions

No managed paper position has ever been opened, so no frozen document exists to read. The
population is the calls the scorer recorded, with their evidence reconstructed **as of each call's
own entry time** from the history TradeSync had already recorded — the same predicates a live
entry uses (`app/entry_evidence_rows.py` mirrors `app/paper_entry_rows.py`, including the
3-significant-figure book, the hour of liquidations with its 500-row cap, and the open-interest
reading from an hour earlier).

Two readings cannot be reconstructed honestly and are therefore absent rather than approximated:

- **the timeframe measurement**: nothing stores one. `horizon_readings` holds Hermes's readings of
  the outlook and there are none. Recomputing it now from candles fetched now would be a fact
  received after the entry, which is exactly what the cut-off exists to exclude;
- **settled funding rows**: the venue's history is fetched over HTTP and would likewise arrive
  after the entry. The funding reading used is the rate recorded minute by minute with open
  interest, which TradeSync held before the call.

## Live reading, 16 September 2026 (read-only)

4,451 measured calls over 1,509 opportunities, ten markets, at 15, 60 and 240 minutes. Market
history begins 14 September 11:38:44 UTC (books and open interest) and 11:52:12 UTC
(liquidations), so the sample is a little over a day, not the 14-day window it was asked for.

Coverage: every call had a recorded book; 29 had no open-interest pair; 86 had no liquidation
received in the hour before them; all 1,509 lacked a timeframe measurement.

**No cell selects.** 18 of the 36 cells could be tested at all; the first-ranked Holm bar was
0.00139 (2.5% over 18). The strongest cells, in basis points net of costs:

| Reading | Polarity | Horizon | Kept / skipped | Kept mean | Skipped mean | Contrast | z |
|---|---|---|---:|---:|---:|---:|---:|
| Funding received | as read | 15 min | 767 / 742 | −5.0 | −20.1 | +15.2 | +1.45 |
| Funding received | as read | 1 h | 767 / 742 | +6.7 | −42.1 | +48.8 | +1.39 |
| Largest wall behind | as read | 1 h | 77 / 1,432 | −11.3 | −17.6 | +6.3 | +0.62 |
| Liquidations received | inverted | 15 min | 652 / 771 | −9.2 | −14.8 | +5.5 | +0.52 |
| Largest wall behind | as read | 15 min | 77 / 1,432 | −5.3 | −12.8 | +7.5 | +0.37 |

Every 240-minute cell is unmeasured: four-hour windows over a day of history leave too few
non-overlapping windows on one side of the split (the declared floor is 20 per side, symbols
pooled — an operational floor, not a power calculation). Fifteen cells have a positive hold-out
contrast, which decides nothing on its own: the hold-out only matters for a cell that cleared the
bar, and none did.

The largest reading in the table is worth stating plainly: taking only the side that is *paid*
funding shows kept trades 48.8 bps better than skipped ones at one hour, and that is 1.39 standard
errors from zero. In a family of 18 tested cells it is what a family of 18 produces from noise.
It is not evidence, it is a reason to keep collecting.

Every mean above is negative or barely positive because these are the signal's own calls net of a
0.12% round trip; the exercise asks which calls were *less bad*, not whether the signal makes money.

## Limitations

- Barely more than a day of recorded history, so the four-hour horizon cannot be measured at all
  and the others rest on few independent windows.
- The calls are the scorer's, not an operator's selections, and they overlap heavily in time.
- Displayed depth can be cancelled; it is not executable depth. Liquidation coverage is other
  venues' feeds, so an empty hour means nothing was received, not that nothing happened.
- The reconstruction uses books aggregated to three significant figures, as a live entry does.
- Reported thresholds were fixed in advance, but the *choice* of six readings was not blind: they
  are the items the entry evidence already freezes.

## What would change the reading

Time, mostly: the same family re-run as history accumulates, and the same family over managed
paper positions once any exist, where the timeframe measurement is frozen at the entry and can
finally be tested. A forward registration of this family is what
[research trial v2](../changes/2026-09-15_research-evidence-and-postgres.md) exists for: it
freezes the universe, the lifecycle rules and this family's digest at registration, so a later
reading cannot quietly become a different experiment.

## Reproducing it

```powershell
E:\Projects\TradeSync\dashboard-overhaul-2026-09-01\.venv\Scripts\python.exe `
  tools\run_in_state_api.py tools\qa_entry_evidence_comparison.py
```

Read-only: SELECTs and the two `SET LOCAL` settings each bounded read runs under. The endpoint is
`GET /state/research/entry-evidence-comparison`, served from the statistics cache and measured in
a worker thread.
