"""Holm's step-down correction over a family of pre-declared one-sided tests.

A verdict has to depend on how many comparisons were looked at. Testing six
context variables in two polarities at three horizons is thirty-six chances for
noise to clear an unadjusted 2.5% bar; roughly one in a family that size will,
every time, from data with nothing in it.

Holm sorts the family's p-values ascending and asks the k-th smallest to clear
``alpha / (m - k)``. The first that fails stops the procedure and every larger
p-value fails with it. It is uniformly more powerful than Bonferroni and makes
no independence assumption, which matters here: overlapping windows and
co-moving symbols make these tests strongly dependent.

The procedure lives in one place so every family in the repository is corrected
the same way and a reader can check it once.
"""

from __future__ import annotations

from typing import Sequence

# One-sided: the question is always "is this better than nothing", never "is it
# different from nothing". A two-sided reading of a one-sided question spends
# half its allowance on an outcome no one would act on.
ALPHA_ONE_SIDED = 0.025


def holm_passes(p_values: Sequence[float | None], alpha: float = ALPHA_ONE_SIDED) -> list[bool]:
    """Which cells clear Holm's bar, counting every cell in the family.

    ``None`` marks a cell that could not be tested (no sample, no error). It
    never passes, and it does not make the bar easier for the cells that could.
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    tested = sorted(
        (index for index, p in enumerate(p_values) if p is not None),
        key=lambda index: p_values[index],
    )
    passes = [False] * len(p_values)
    for rank, index in enumerate(tested):
        if p_values[index] > alpha / (len(tested) - rank):
            break
        passes[index] = True
    return passes


def holm_bar(p_values: Sequence[float | None], alpha: float = ALPHA_ONE_SIDED) -> float | None:
    """The bar the best-ranked cell had to clear: ``alpha / m`` over the tested cells.

    Reported so a reading that finds nothing still says how high the bar was.
    """
    tested = sum(1 for p in p_values if p is not None)
    return alpha / tested if tested else None
