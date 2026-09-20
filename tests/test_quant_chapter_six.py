"""Every worked example and exercise answer in docs/quant-learning/06, checked against the code it teaches."""

from __future__ import annotations

import itertools
import math
import statistics

import pytest

from tradesync_core.ablation_statistics import _Reading, analytic_contrast_se, bootstrap_contrast_se
from tradesync_core.independence import Observation, binomial_se, independent_counts, non_overlapping
from tradesync_core.multiple_testing import ALPHA_ONE_SIDED, holm_bar, holm_passes


def _exact_bootstrap_sd(blocks: list[tuple[float, int, float, int]]) -> float:
    """Every equally likely resample of the blocks, listed rather than drawn: (kept sum, kept n, skipped sum, skipped n)."""
    contrasts = []
    for resample in itertools.product(blocks, repeat=len(blocks)):
        kept_sum, kept_n, skipped_sum, skipped_n = (sum(block[i] for block in resample) for i in range(4))
        contrasts.append(kept_sum / kept_n - skipped_sum / skipped_n)
    return statistics.pstdev(contrasts)


def test_worked_example_one_overlap_makes_the_error_four_times_larger() -> None:
    n_eff = max(min(74, 3 * (336 / 240)), 1)
    assert n_eff == pytest.approx(4.2)
    assert binomial_se(n_eff) == pytest.approx(0.2440, abs=1e-4)
    assert binomial_se(74) == pytest.approx(0.0581, abs=1e-4)
    assert binomial_se(n_eff) / binomial_se(74) == pytest.approx(4.2, abs=0.01)


def test_worked_example_two_counts_windows_per_symbol_and_pooled() -> None:
    def call(symbol: str, minute: int) -> Observation:
        return Observation(symbol, minute * 60, "LONG", 0.1, 0.1)

    calls = [call("BTC-PERP", m) for m in (0, 60, 240, 480)] + [call("ETH-PERP", m) for m in (30, 300)]
    assert independent_counts(calls, 240) == {"per_symbol": 5, "pooled": 3}
    assert [o.opened_at_s // 60 for o in non_overlapping(calls, 240, pool_symbols=True)] == [0, 240, 480]


def test_the_noise_arithmetic_for_a_36_cell_family() -> None:
    assert 36 * ALPHA_ONE_SIDED == pytest.approx(0.9)
    assert 1 - (1 - ALPHA_ONE_SIDED) ** 36 == pytest.approx(0.598, abs=1e-3)


def test_worked_example_three_holm_bonferroni_and_no_correction() -> None:
    family = [0.004, 0.030, 0.006, None, 0.012, 0.200]
    assert holm_passes(family) == [True, False, True, False, False, False]
    assert holm_bar(family) == pytest.approx(0.005)
    tested = [p for p in family if p is not None]
    assert sum(p <= ALPHA_ONE_SIDED / len(tested) for p in tested) == 1
    assert sum(p <= ALPHA_ONE_SIDED for p in tested) == 3


def test_worked_example_four_bootstrap_by_hand_and_by_the_code() -> None:
    assert _exact_bootstrap_sd([(0.6, 2, -0.1, 1), (0.0, 1, -0.4, 2)]) == pytest.approx(0.0782, abs=1e-4)
    readings = [
        _Reading("BTC-PERP", 0, 0.4, True), _Reading("BTC-PERP", 600, 0.2, True), _Reading("BTC-PERP", 900, -0.1, False),
        _Reading("BTC-PERP", 3600, 0.0, True), _Reading("BTC-PERP", 4200, -0.3, False), _Reading("BTC-PERP", 4500, -0.1, False),
    ]
    assert bootstrap_contrast_se(readings, 60, draws=20_000, seed=1) == pytest.approx(0.0783, abs=1e-4)
    assert bootstrap_contrast_se(readings[:3], 60, draws=400) is None  # one block: nothing to vary


def test_worked_example_five_analytic_error_with_deflated_counts() -> None:
    kept, skipped = [0.4, 0.2, 0.0], [-0.1, -0.3, -0.1]
    full = analytic_contrast_se(kept, skipped, 1.0)
    two_thirds = analytic_contrast_se(kept, skipped, 2 / 3)
    assert full == pytest.approx(0.1333, abs=1e-4)
    assert two_thirds == pytest.approx(0.1633, abs=1e-4)
    assert two_thirds / full == pytest.approx(math.sqrt(3 / 2))
    assert analytic_contrast_se(kept, skipped, 0.5) is None


def test_exercise_one_effective_sample() -> None:
    n_eff = min(120, 2 * (720 / 60))
    assert n_eff == 24
    assert binomial_se(n_eff) == pytest.approx(0.1021, abs=1e-4)
    assert binomial_se(120) == pytest.approx(0.0456, abs=1e-4)
    assert binomial_se(n_eff) / binomial_se(120) == pytest.approx(math.sqrt(5))


def test_exercise_two_holm_against_bonferroni() -> None:
    family = [0.005, 0.011, 0.020]
    assert holm_passes(family) == [True, True, True]
    assert sum(p <= ALPHA_ONE_SIDED / 3 for p in family) == 1
    assert sum(p <= ALPHA_ONE_SIDED for p in family) == 3


def test_exercise_three_exact_bootstrap() -> None:
    assert _exact_bootstrap_sd([(0.3, 1, 0.0, 1), (0.1, 1, -0.1, 1)]) == pytest.approx(0.0354, abs=1e-4)
    readings = [
        _Reading("ETH-PERP", 0, 0.3, True), _Reading("ETH-PERP", 60, 0.0, False),
        _Reading("ETH-PERP", 3600, 0.1, True), _Reading("ETH-PERP", 3660, -0.1, False),
    ]
    assert bootstrap_contrast_se(readings, 60, draws=20_000, seed=1) == pytest.approx(0.0355, abs=2e-4)


def test_exercise_four_noise_in_a_24_cell_family() -> None:
    assert 24 * ALPHA_ONE_SIDED == pytest.approx(0.6)
    assert 1 - (1 - ALPHA_ONE_SIDED) ** 24 == pytest.approx(0.455, abs=1e-3)
