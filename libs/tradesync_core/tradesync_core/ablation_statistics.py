"""The error on an ablation contrast, measured two ways.

Moved out of ``ablation_evidence.py`` unchanged. The block bootstrap resamples
whole time blocks one horizon long, so overlapping windows and symbols that move
together count as the single pieces of evidence they nearly are; the analytic
error deflates both group sizes to independent windows. ``ablation_evidence``
takes the larger of the two and re-exports every public name here.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from .independence import time_blocks

DEFAULT_DRAWS = 400


@dataclass(frozen=True)
class _Reading:
    """A case reduced to the split: net result, and which side of the filter it fell."""

    symbol: str
    opened_at_s: int
    net: float
    retained: bool


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _variance(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _normal_upper_tail(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _block_aggregates(readings: Sequence[_Reading], horizon_minutes: int) -> list[tuple[float, int, float, int]]:
    """Per time block one horizon long: the kept sum and count, then the skipped sum and count."""
    return [
        (
            math.fsum(r.net for r in block if r.retained),
            sum(1 for r in block if r.retained),
            math.fsum(r.net for r in block if not r.retained),
            sum(1 for r in block if not r.retained),
        )
        for block in time_blocks(readings, horizon_minutes)
    ]


def bootstrap_contrast_se(
    readings: Sequence[_Reading], horizon_minutes: int, *, draws: int = DEFAULT_DRAWS, seed: int = 0
) -> float | None:
    """Standard error of the contrast, resampling whole time blocks.

    A block is one horizon long and carries every symbol observed inside it, so
    overlapping windows and symbols that move together are resampled as the
    single pieces of evidence they nearly are. ``None`` with fewer than two
    blocks: one block resampled against itself has no variation to measure, and
    reporting zero would claim a certainty the sample does not have.
    """
    aggregates = _block_aggregates(readings, horizon_minutes)
    if len(aggregates) < 2:
        return None
    rng = random.Random(seed)
    contrasts: list[float] = []
    count = len(aggregates)
    for _ in range(draws):
        kept_sum = skipped_sum = 0.0
        kept_n = skipped_n = 0
        for _ in range(count):
            block = aggregates[rng.randrange(count)]
            kept_sum += block[0]
            kept_n += block[1]
            skipped_sum += block[2]
            skipped_n += block[3]
        if kept_n and skipped_n:
            contrasts.append(kept_sum / kept_n - skipped_sum / skipped_n)
    if len(contrasts) < 2:
        return None
    mean = sum(contrasts) / len(contrasts)
    return math.sqrt(sum((c - mean) ** 2 for c in contrasts) / (len(contrasts) - 1))


def analytic_contrast_se(kept: Sequence[float], skipped: Sequence[float], independent_share: float) -> float | None:
    """The textbook error of a difference in means, with both counts deflated to independent windows.

    ``independent_share`` is the measured fraction of observations whose windows
    do not overlap, symbols pooled. Treating every overlapping observation as its
    own fact is how a sample of a few hundred once reported a significant result.
    """
    if not 0 < independent_share <= 1:
        return None
    kept_var, skipped_var = _variance(kept), _variance(skipped)
    kept_n, skipped_n = len(kept) * independent_share, len(skipped) * independent_share
    if kept_var is None or skipped_var is None or kept_n < 2 or skipped_n < 2:
        return None
    return math.sqrt(kept_var / kept_n + skipped_var / skipped_n)
