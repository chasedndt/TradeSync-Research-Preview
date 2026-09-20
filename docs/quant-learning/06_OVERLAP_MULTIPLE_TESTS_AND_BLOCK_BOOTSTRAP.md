# Chapter 6 — Overlapping Windows, Many Tests at Once, and the Block Bootstrap

TradeSync keeps asking one question: did a call, or a filter on its context, beat doing nothing? Three
traps make the honest answer smaller than the first reading suggests. Each has a guard in the code, and
this chapter works each one by hand first.

| Trap | Guard | Code |
|---|---|---|
| Overlapping windows counted as separate evidence | effective sample size | `tradesync_core/independence.py`, the outcomes-by-regime route |
| Many comparisons, one lucky pass | Holm's step-down correction | `tradesync_core/multiple_testing.py` |
| Errors computed as if observations were independent | block bootstrap, and deflated analytic errors | `tradesync_core/ablation_statistics.py` |

Every number below is reproduced by `tests/test_quant_chapter_six.py`.

## 1. Overlapping windows

**Horizon, `H`.** How long after a call its outcome is measured. Unit: minutes; positive. Example:
`H = 240` for a four-hour outcome.

**Observations, `n`.** How many calls were measured. Unit: a count; zero or more. Example: `n = 74`.

**Span, `S`.** Minutes from the first measured call to the last. Example: 5.6 hours is `S = 336`.

**Symbols, `k`.** How many markets the calls cover. Example: `k = 3` for BTC, ETH and SOL.

**Windows per symbol, `W`.** How many non-overlapping horizons fit in the span: `W = S / H`. Unit: a count
that can be fractional. Example: `336 / 240 = 1.4`.

**Effective sample, `n_eff`.** What the sample is worth as independent evidence. It can never exceed the
calls made, and never fall below one:

```text
n_eff = max(min(n, k · W), 1)
```

A verdict recorded every 60 seconds over a 240-minute horizon produces calls whose windows share almost all
of their price path. Two calls four minutes apart share 98% of their window: they are very nearly the same
trade, counted twice.

**Standard error, `SE`.** How far a measured hit rate could sit from the truth by chance alone. The
code uses the worst case, a true rate of one half, so a sample near 0% or 100% is never flattered:

```text
SE = √(0.25 / n_eff)
```

### Worked example 1 — the sample that looked significant

A sample of `n = 74` calls spanned 5.6 hours on three symbols, measured at `H = 240`.

- `W = 336 / 240 = 1.4` windows per symbol, and `k · W = 3 × 1.4 = 4.2`.
- `n_eff = max(min(74, 4.2), 1) = 4.2`.
- `SE = √(0.25 / 4.2) = 0.2440`, against the naive `√(0.25 / 74) = 0.0581`.

The honest error is **4.2 times** the naive one. A skill of +12 points is two naive errors, which looks
significant. It is half of one honest error. Symbols are still counted as independent here, which is
generous (BTC, ETH and SOL move together), so even this is a floor on the uncertainty.

### Worked example 2 — counting the windows themselves

`non_overlapping` keeps the earliest remaining call, then the next one that starts at least `H` later. All
windows have the same length, so this greedy choice keeps as many as any selection could.

Take `H = 240`, with BTC calls at minutes 0, 60, 240 and 480, and ETH calls at minutes 30 and 300.

- **Per symbol (the generous count).** BTC keeps 0, 240 and 480; ETH keeps 30 and 300. **5** windows.
- **Pooled (the conservative count).** One timeline: 0, 30, 60, 240, 300, 480. It keeps 0, then 240, then 480. **3** windows.

`independent_counts` reports both. The truth lies between them, and a result has to survive the
conservative one.

## 2. Many tests at once

**Family, `m`.** How many comparisons were actually tested together. A cell with no sample or no error
cannot be tested; it is left out of `m` and never passes.

**Significance level, `α`.** The chance of a false pass the procedure allows. TradeSync uses
`α = 0.025`, one-sided, because the question is always "better than nothing", never merely "different".

**p-value, `p`.** The chance of a result at least this good if the true effect were zero. Unit: a
probability in [0, 1]. Example: `p = 0.004`.

**Why a family needs a correction.** The ablation family tests six context variables, in two polarities, at three
horizons: 36 cells. With nothing real in the data and no correction, each cell passes 2.5% of the time:

- expected false passes: `36 × 0.025 = 0.9`, so about one, every time;
- if the cells were independent, the chance of at least one false pass is `1 − 0.975^36 = 59.8%`.

**Holm's step-down procedure.** Sort the `m` tested p-values from smallest to largest, and number them with
rank `r = 0, 1, …`. The cell of rank `r` must clear

```text
bar_r = α / (m − r)
```

The first cell that fails stops the procedure, and every larger p-value fails with it. The chance of any
false pass in the family stays at most `α`, with no independence assumption; overlapping windows make
these tests strongly dependent, so that matters. Bonferroni asks every cell to clear `α / m`, and Holm is
never less powerful than that.

### Worked example 3 — one family, three rules

p-values `[0.004, 0.030, 0.006, untestable, 0.012, 0.200]`.

- **Tested.** Five cells, so `m = 5`. The untestable cell does not lower anyone's bar.
- **Sorted.** 0.004, 0.006, 0.012, 0.030, 0.200.
- **Holm.** 0.004 ≤ 0.025/5 = 0.005 passes. 0.006 ≤ 0.025/4 = 0.00625 passes. 0.012 > 0.025/3 =
  0.00833 fails and stops the procedure. **Two cells pass**: the first and the third as listed.
- **Bonferroni.** Only 0.004 clears 0.005. **One cell passes.**
- **No correction.** 0.004, 0.006 and 0.012 all clear 0.025. **Three cells pass**, and one of them is
  exactly the kind of pass a family this size produces from noise.

`holm_bar` reports the strictest bar, `α / m = 0.005`, so a reading that finds nothing still says how
high the bar was.

## 3. Resampling whole blocks

A context filter splits calls into those it **kept** and those it **skipped**.

**Contrast, `c`.** The mean net result of the kept calls, minus that of the skipped calls. Unit:
percentage points. Example: `0.20 − (−0.17) = 0.37`.

**Block.** Every call opened within one horizon-long slice of time, all symbols together
(`time_blocks`). Calls in one block share their price path, so they are resampled together or not at
all.

**Block bootstrap standard error, `SE_boot`.** Resample `B` blocks, with replacement, from the `B` observed
blocks. Compute the contrast of that resample, and repeat. The standard deviation of those contrasts is
the error. With fewer than two blocks there is nothing to vary, so the code reports no error rather than
zero.

### Worked example 4 — every possible resample, by hand

Two blocks one hour apart, `H = 60`:

| Block | Kept results | Skipped results |
|---|---|---|
| A | +0.4, +0.2 | −0.1 |
| B | 0.0 | −0.3, −0.1 |

With two blocks there are four equally likely resamples:

| Resample | Kept mean | Skipped mean | Contrast |
|---|---:|---:|---:|
| A A | 1.2 / 4 = 0.300 | −0.2 / 2 = −0.100 | 0.4000 |
| A B | 0.6 / 3 = 0.200 | −0.5 / 3 = −0.167 | 0.3667 |
| B A | same as A B | | 0.3667 |
| B B | 0.0 / 2 = 0.000 | −0.8 / 4 = −0.200 | 0.2000 |

- **Mean contrast.** 0.3333.
- **Squared deviations.** 0.00444, 0.00111, 0.00111 and 0.01778, which sum to 0.02444.
- **Result.** `SE_boot = √(0.02444 / 4) = 0.0782`.

The code draws resamples at random instead of listing them. With 20,000 seeded draws it reports 0.0783.

### Worked example 5 — the analytic error, with deflated counts

The textbook error of a difference in means is

```text
SE = √(var_kept / n_kept + var_skipped / n_skipped)
```

TradeSync multiplies both counts by the **independent share**: the measured fraction of calls whose windows
do not overlap. It never uses the raw counts.

Take kept results +0.4, +0.2 and 0.0, and skipped results −0.1, −0.3 and −0.1. Then `var_kept = 0.0400`
and `var_skipped = 0.0133`, both with the `n − 1` denominator.

- **Share 1.** Counts 3 and 3, so `SE = √(0.0400/3 + 0.0133/3) = 0.1333`.
- **Share 2/3.** Counts 2 and 2, so `SE = √(0.0400/2 + 0.0133/2) = 0.1633`. That is √(3/2) larger, as a
  count shrunk by two thirds should be.
- **Share 1/2.** Counts 1.5 and 1.5, below the minimum of two, so the code reports **no error**. A
  variance from fewer than two independent observations is not a measurement.

The ablation report computes both errors and uses **the larger** (`ablation_evidence.py`). Each guards
against a different way of being overconfident.

## 4. Exercises

1. **Effective sample.** 120 calls over 12 hours on 2 symbols, at `H = 60`. Find `n_eff`, the honest
   `SE`, the naive `SE`, and their ratio.
2. **Holm against Bonferroni.** The family `[0.005, 0.011, 0.020]` at `α = 0.025`. How many cells pass
   under Holm, under Bonferroni, and with no correction?
3. **Exact bootstrap.** Block C kept +0.3 and skipped 0.0. Block D kept +0.1 and skipped −0.1. List the
   four resamples' contrasts and compute `SE_boot`.
4. **Noise.** A family of 24 one-sided tests on pure noise at an unadjusted 2.5%. Give the expected
   number of false passes, and the chance of at least one if the tests were independent. What does Holm
   hold that chance to?

## 5. Answers

1. `W = 720/60 = 12`, `k · W = 24`, `n_eff = min(120, 24) = 24`. Honest `SE = √(0.25/24) = 0.1021`, naive
   `SE = √(0.25/120) = 0.0456`, ratio `√5 = 2.236`.
2. **Holm, 3:** 0.005 ≤ 0.00833, 0.011 ≤ 0.0125 and 0.020 ≤ 0.025. **Bonferroni, 1:** only 0.005 ≤
   0.00833. **No correction, 3.**
3. CC gives 0.3000, CD and DC give 0.2500, DD gives 0.2000. The mean is 0.25, the squared deviations sum to
   0.005, and `SE_boot = √(0.005/4) = 0.0354`.
4. Expected false passes `24 × 0.025 = 0.6`. Chance of at least one `1 − 0.975^24 = 45.5%`. Holm holds it
   to at most 2.5%.

## Mapping to the Year 2 syllabus

- **Standard errors.** Sampling distributions and standard errors (§1, §3).
- **Multiple testing.** Hypothesis testing and family-wise error (§2).
- **Resampling.** Resampling methods (§3).

Match these to your own module handbook's chapter titles when you have it; the mapping in
[chapter 4](04_YEAR2_MODULE_MAP_AND_PRACTICE.md) is the place to record them.
