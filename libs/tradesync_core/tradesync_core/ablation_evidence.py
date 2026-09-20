"""Does the evidence frozen at entry pick the calls worth acting on?

One cell is one declared comparison at one horizon: the signal's own calls, split
by a context reading frozen before the entry, into the trades a filter would have
kept and the trades it would have skipped. Two numbers come out of that split and
they answer different questions, so they are never collapsed:

- **the paired difference per original opportunity**, the frozen v1 metric: both
  means divide by the same original count and a skipped trade contributes zero to
  the filter. It says what the filter would have done to the book.
- **the contrast**, the mean net result of the kept trades minus the mean of the
  skipped ones. It says whether the context *selected*.

The difference matters. After costs the signal's mean result is negative, and any
filter that skips enough trades raises the paired difference for that reason
alone, with no selection at all. Only the contrast can tell a context that sorts
good calls from bad apart from a context that simply trades less, so the contrast
is what is tested and the paired difference is reported beside it.

The error on the contrast is measured, not assumed. Verdicts every cell reports
separately:

- ``detectable``    the sample can tell the contrast from zero, either way;
- ``selects``       contrast > 0 at one-sided 2.5%, Holm-adjusted across every
                    cell in the family, and at least two standard errors;
- ``economic``      it selects *and* the kept trades' mean is positive after the
                    stated costs. A filter that loses less money is not an edge;
- ``held_out``      the contrast keeps its sign on the newest 30% of the sample,
                    which the earlier 70% never saw.

None of these is trading readiness and none of them promotes anything. Shadow
only: this module reads outcomes and reports on them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .ablation_statistics import (
    DEFAULT_DRAWS,
    _Reading,
    _block_aggregates,
    _mean,
    _normal_upper_tail,
    _variance,
    analytic_contrast_se,
    bootstrap_contrast_se,
)
from .edge_evidence import DETECTABLE_Z, CostAssumptions
from .entry_evidence_family import DECLARATIONS, POLARITIES, to_dict as family_declaration
from .independence import non_overlapping
from .multiple_testing import ALPHA_ONE_SIDED, holm_bar, holm_passes

SCHEMA_VERSION = "entry-evidence-ablation-v1"

# An operational floor for calling a cell measured, not a power calculation: with
# fewer non-overlapping windows than this on either side of the split, the
# reading says so instead of presenting a number as if it settled anything.
MIN_INDEPENDENT_PER_GROUP = 20
DEFAULT_HOLDOUT_FRACTION = 0.30


@dataclass(frozen=True)
class Case:
    """One measured call with the context frozen at its entry.

    ``signed_return_pct`` is the call's own result before costs: positive when
    the market moved the way the call pointed. ``context`` holds one reading per
    declared variable, ``None`` where the evidence held none.
    """

    key: str
    symbol: str
    opened_at_s: int
    horizon_minutes: int
    signed_return_pct: float
    context: Mapping[str, float | None]


@dataclass
class AblationCell:
    variable: str
    label: str
    polarity: str
    sign: int
    threshold: float
    horizon_minutes: int
    eligible: int
    context_available: int
    retained: int
    abstained: int
    independent_pooled: int
    independent_retained: int
    independent_abstained: int
    baseline_mean_net_pct: float | None
    filter_mean_net_pct: float | None
    paired_mean_difference_pct: float | None
    retained_mean_net_pct: float | None
    abstained_mean_net_pct: float | None
    contrast_pct: float | None
    se_bootstrap: float | None
    se_analytic: float | None
    standard_error: float | None
    z: float | None
    p_positive: float | None
    detectable: bool
    holdout_contrast_pct: float | None
    holdout_measured: int
    sample_state: str
    # Whether this cell entered the family's correction. A cell that could not be
    # measured still reports its numbers; they were never tested and are not evidence.
    tested: bool = False
    selects: bool = False
    economic: bool | None = None
    held_out: bool | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "readiness": "descriptive evidence only; not trading readiness"}


def _cell(declaration, polarity: str, sign: int, horizon: int, cases: Sequence[Case], costs: CostAssumptions,
          *, draws: int, seed: int, holdout_fraction: float) -> AblationCell:
    at_horizon = [case for case in cases if case.horizon_minutes == horizon]
    net = {case.key: case.signed_return_pct - costs.total_pct for case in at_horizon}
    covered = [case for case in at_horizon if case.context.get(declaration.variable) is not None]
    kept_cases = [case for case in covered if case.context[declaration.variable] * sign >= declaration.threshold]
    kept_keys = {case.key for case in kept_cases}
    skipped_cases = [case for case in covered if case.key not in kept_keys]

    kept = [net[case.key] for case in kept_cases]
    skipped = [net[case.key] for case in skipped_cases]
    baseline = [net[case.key] for case in at_horizon]
    # The v1 convention: the same original denominator, a skipped trade contributing zero.
    filtered = [net[case.key] if case.key in kept_keys else 0.0 for case in at_horizon]

    readings = [
        _Reading(symbol=case.symbol, opened_at_s=case.opened_at_s, net=net[case.key], retained=case.key in kept_keys)
        for case in covered
    ]
    pooled = len(non_overlapping(covered, horizon, pool_symbols=True)) if covered else 0
    share = pooled / len(covered) if covered else 0.0
    se_bootstrap = bootstrap_contrast_se(readings, horizon, draws=draws, seed=seed) if readings else None
    se_analytic = analytic_contrast_se(kept, skipped, share) if share else None
    available = [se for se in (se_bootstrap, se_analytic) if se is not None and se > 0]
    # The larger error is the one a decision uses: the conservative choice.
    se = max(available) if available else None

    kept_mean, skipped_mean = _mean(kept), _mean(skipped)
    contrast = None if kept_mean is None or skipped_mean is None else kept_mean - skipped_mean
    z = contrast / se if contrast is not None and se else None

    ordered = sorted(covered, key=lambda case: (case.opened_at_s, case.symbol, case.key))
    cut = len(ordered) - math.ceil(len(ordered) * holdout_fraction)
    holdout = ordered[cut:] if len(ordered) >= 2 else []
    holdout_kept = _mean([net[case.key] for case in holdout if case.key in kept_keys])
    holdout_skipped = _mean([net[case.key] for case in holdout if case.key not in kept_keys])
    holdout_contrast = None if holdout_kept is None or holdout_skipped is None else holdout_kept - holdout_skipped

    independent_kept = len(non_overlapping(kept_cases, horizon, pool_symbols=True)) if kept_cases else 0
    independent_skipped = len(non_overlapping(skipped_cases, horizon, pool_symbols=True)) if skipped_cases else 0
    if not covered:
        state = "no_context"
    elif not kept or not skipped:
        state = "one_sided"
    elif min(independent_kept, independent_skipped) < MIN_INDEPENDENT_PER_GROUP:
        state = "too_few_independent_windows"
    else:
        state = "measured"

    notes: list[str] = []
    if state == "no_context":
        notes.append("no case in this population carried this reading; nothing was measured")
    elif state == "one_sided":
        notes.append("every covered case fell on one side of the threshold, so there is nothing to contrast")
    elif state == "too_few_independent_windows":
        notes.append(
            f"fewer than {MIN_INDEPENDENT_PER_GROUP} non-overlapping windows on one side "
            f"({independent_kept} kept, {independent_skipped} skipped, symbols pooled)"
        )
    if covered and len(covered) < len(at_horizon):
        notes.append(f"{len(at_horizon) - len(covered)} of {len(at_horizon)} eligible calls had no reading and abstain")

    return AblationCell(
        variable=declaration.variable, label=declaration.label, polarity=polarity, sign=sign,
        threshold=declaration.threshold, horizon_minutes=horizon,
        eligible=len(at_horizon), context_available=len(covered), retained=len(kept), abstained=len(skipped),
        independent_pooled=pooled, independent_retained=independent_kept, independent_abstained=independent_skipped,
        baseline_mean_net_pct=_mean(baseline), filter_mean_net_pct=_mean(filtered),
        paired_mean_difference_pct=(None if not at_horizon else _mean(filtered) - _mean(baseline)),
        retained_mean_net_pct=kept_mean, abstained_mean_net_pct=skipped_mean, contrast_pct=contrast,
        se_bootstrap=se_bootstrap, se_analytic=se_analytic, standard_error=se, z=z,
        p_positive=None if z is None else _normal_upper_tail(z),
        detectable=z is not None and abs(z) >= DETECTABLE_Z,
        holdout_contrast_pct=holdout_contrast, holdout_measured=len(holdout),
        sample_state=state, notes=notes,
    )


def assess_family(
    cases: Sequence[Case],
    *,
    costs: CostAssumptions,
    horizons: Iterable[int] | None = None,
    draws: int = DEFAULT_DRAWS,
    seed: int = 0,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
) -> dict[str, Any]:
    """Every declared cell, assessed together so the correction sees the whole family."""
    wanted = sorted(set(horizons)) if horizons is not None else sorted({case.horizon_minutes for case in cases})
    cells = [
        _cell(declaration, polarity, sign, horizon, cases, costs,
              draws=draws, seed=seed, holdout_fraction=holdout_fraction)
        for declaration in DECLARATIONS
        for polarity, sign in POLARITIES
        for horizon in wanted
    ]
    # Together is the point: a bar computed from the promising cells alone is not a bar.
    p_values = [cell.p_positive if cell.sample_state == "measured" else None for cell in cells]
    for cell, passed, p_value in zip(cells, holm_passes(p_values), p_values):
        cell.tested = p_value is not None
        cell.selects = bool(passed) and cell.z is not None and cell.z >= DETECTABLE_Z
        cell.economic = None if cell.retained_mean_net_pct is None else (cell.selects and cell.retained_mean_net_pct > 0)
        cell.held_out = None if cell.holdout_contrast_pct is None else cell.holdout_contrast_pct > 0

    symbols = sorted({case.symbol for case in cases})
    opened = [case.opened_at_s for case in cases]
    coverage = {
        declaration.variable: sum(1 for case in cases if case.context.get(declaration.variable) is not None)
        for declaration in DECLARATIONS
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "family": family_declaration(),
        "costs": {"round_trip_fee_pct": costs.round_trip_fee_pct, "spread_pct": costs.spread_pct,
                  "slippage_pct": costs.slippage_pct, "total_pct": costs.total_pct, "source": costs.source},
        "population": {
            "cases": len(cases), "symbols": symbols, "horizons": wanted,
            "first_opened_at_s": min(opened) if opened else None, "last_opened_at_s": max(opened) if opened else None,
            "context_coverage": coverage,
        },
        "holm": {"cells": len(cells), "cells_tested": sum(1 for p in p_values if p is not None),
                 "alpha_one_sided": ALPHA_ONE_SIDED, "first_rank_bar": holm_bar(p_values)},
        "cells": [cell.to_dict() for cell in cells],
        "minimum_independent_windows": MIN_INDEPENDENT_PER_GROUP,
        "holdout_fraction": holdout_fraction,
        "authority": "research_only",
        "promotion_allowed": False,
        "note": (
            "Retrospective ablation of the signal's own calls, split by evidence frozen before each entry. "
            "The paired difference uses the same original denominator, so a filter that skips more trades raises it "
            "whenever the baseline is negative after costs; that is arithmetic, not selection. The contrast between "
            "kept and skipped trades is the tested quantity, with a block-bootstrap error and non-overlapping window "
            "counts. No confidence interval is a promotion, no cell changes a weight, and an operator-selected, "
            "overlapping sample is not a randomized experiment."
        ),
    }
