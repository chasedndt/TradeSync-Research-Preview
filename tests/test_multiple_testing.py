"""Holm's step-down bar: what it costs to look at a whole family at once."""

import pytest

from tradesync_core.multiple_testing import ALPHA_ONE_SIDED, holm_bar, holm_passes


def test_the_bar_tightens_with_the_size_of_the_family():
    """One cell is unadjusted; the same p-value in a family of ten is not."""
    assert holm_passes([0.02]) == [True]
    assert holm_passes([0.02] + [0.9] * 9)[0] is False
    assert holm_bar([0.02]) == ALPHA_ONE_SIDED
    assert holm_bar([0.02] + [0.9] * 9) == pytest.approx(ALPHA_ONE_SIDED / 10)


def test_the_first_failure_stops_every_larger_p_value():
    # 0.002 clears 0.025/4; 0.02 does not clear 0.025/3, so 0.021 fails with it
    # even though it would clear the last rank's 0.025.
    assert holm_passes([0.002, 0.02, 0.021, 0.5]) == [True, False, False, False]


def test_an_untested_cell_never_passes_and_never_lowers_the_bar():
    """``None`` is "could not be tested", not "passed" and not a free slot."""
    assert holm_passes([None, 0.02]) == [False, True]
    assert holm_bar([None, None, 0.02]) == ALPHA_ONE_SIDED
    assert holm_passes([None]) == [False]
    assert holm_bar([None]) is None


def test_ties_are_not_rounded_in_anybody_s_favour():
    # Exactly at the bar passes; a hair above it does not.
    assert holm_passes([ALPHA_ONE_SIDED / 2, ALPHA_ONE_SIDED]) == [True, True]
    assert holm_passes([ALPHA_ONE_SIDED / 2 + 1e-12, ALPHA_ONE_SIDED]) == [False, False]


def test_an_impossible_allowance_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        holm_passes([0.01], alpha=0)
