"""What the ablation says, and the two ways it refuses to flatter a filter."""

import pytest

from tradesync_core.ablation_evidence import MIN_INDEPENDENT_PER_GROUP, Case, assess_family
from tradesync_core.edge_evidence import CostAssumptions

COSTS = CostAssumptions(round_trip_fee_pct=0.09, spread_pct=0.02, slippage_pct=0.01, source="test fixture")
SYMBOLS = ("BTC-PERP", "ETH-PERP", "SOL-PERP", "XRP-PERP")
START = 1_700_000_000
STEP = 4_200  # longer than the 60-minute horizon, so every case is its own window


def spread(index: int) -> float:
    """A little variation inside each group, so the sample has an error to measure.

    Identical returns would give a standard error of exactly zero, which is not a
    certainty a real sample ever has; the reading refuses to report one.
    """
    return 0.1 if (index // 2) % 2 == 0 else -0.1


def case(index: int, *, value, signed, horizon=60, variable="book_imbalance"):
    return Case(key=f"case-{index}", symbol=SYMBOLS[index % len(SYMBOLS)], opened_at_s=START + index * STEP,
                horizon_minutes=horizon, signed_return_pct=signed, context={variable: value})


def sorting_cases(count=100, flip_from=None):
    """Even cases carry a positive reading and win; odd ones carry a negative reading and lose.

    Past ``flip_from`` the outcomes reverse while the readings do not, which is a
    context that stops working exactly where the hold-out begins.
    """
    cases = []
    for index in range(count):
        wins = index % 2 == 0 if flip_from is None or index < flip_from else index % 2 == 1
        cases.append(case(index, value=1.0 if index % 2 == 0 else -1.0,
                          signed=(1.0 if wins else -1.0) + spread(index)))
    return cases


def cell_of(report, variable="book_imbalance", polarity="as_read", horizon=60):
    return next(c for c in report["cells"]
                if c["variable"] == variable and c["polarity"] == polarity and c["horizon_minutes"] == horizon)


def test_a_context_that_sorts_winners_from_losers_is_measured_as_selection():
    cell = cell_of(assess_family(sorting_cases(), costs=COSTS, draws=80))
    assert cell["retained"] == cell["abstained"] == 50
    assert cell["retained_mean_net_pct"] == pytest.approx(0.88)
    assert cell["abstained_mean_net_pct"] == pytest.approx(-1.12)
    assert cell["contrast_pct"] == pytest.approx(2.0)
    assert cell["standard_error"] > 0 and cell["z"] > 2
    assert cell["sample_state"] == "measured" and cell["tested"] and cell["detectable"]
    assert cell["selects"] is True and cell["economic"] is True and cell["held_out"] is True


def test_abstaining_from_a_losing_book_raises_the_paired_difference_without_selecting_anything():
    """The arithmetic trap: a filter that simply trades less looks good on the paired metric.

    Context and outcome are laid out so the kept and skipped trades have exactly
    the same mean. The paired difference is positive anyway, because half the
    losses are no longer taken. Only the contrast says there was no selection.
    """
    cases = [case(i, value=1.0 if i % 2 == 0 else -1.0, signed=0.5 if (i // 2) % 2 == 0 else -0.9)
             for i in range(100)]
    cell = cell_of(assess_family(cases, costs=COSTS, draws=80))
    assert cell["baseline_mean_net_pct"] == pytest.approx(-0.32)
    assert cell["paired_mean_difference_pct"] == pytest.approx(0.16)
    assert cell["contrast_pct"] == pytest.approx(0.0)
    assert cell["retained_mean_net_pct"] == pytest.approx(-0.32)
    assert cell["tested"] is True and cell["selects"] is False and cell["economic"] is False


def test_costs_come_off_every_mean_before_any_verdict():
    cases = [case(i, value=1.0 if i % 2 == 0 else -1.0, signed=0.10 + spread(i) / 10) for i in range(100)]
    cell = cell_of(assess_family(cases, costs=COSTS, draws=40))
    # +0.10% gross is a loss after a 0.12% round trip, so nothing here is economic.
    assert cell["retained_mean_net_pct"] == pytest.approx(-0.02)
    assert cell["economic"] is False


def test_missing_context_abstains_and_is_counted_never_read_as_zero():
    cases = [case(i, value=None if i < 40 else 1.0, signed=1.0 + spread(i)) for i in range(100)]
    cell = cell_of(assess_family(cases, costs=COSTS, draws=40))
    assert cell["eligible"] == 100 and cell["context_available"] == 60
    assert cell["retained"] == 60 and cell["abstained"] == 0
    assert cell["sample_state"] == "one_sided" and cell["tested"] is False and cell["p_positive"] is None
    assert "40 of 100 eligible calls had no reading" in " ".join(cell["notes"])
    # The baseline still divides by every eligible call, missing context included.
    assert cell["baseline_mean_net_pct"] == pytest.approx(0.88)


def test_a_variable_no_case_carries_says_so_instead_of_reporting_a_number():
    cases = [case(i, value=1.0, signed=1.0) for i in range(10)]
    cell = cell_of(assess_family(cases, costs=COSTS, draws=20), variable="horizon_lean")
    assert cell["sample_state"] == "no_context" and cell["context_available"] == 0
    assert cell["contrast_pct"] is None and cell["selects"] is False and cell["economic"] is None
    assert cell["tested"] is False and "nothing was measured" in " ".join(cell["notes"])


def test_overlapping_windows_are_counted_once_and_can_leave_a_cell_unmeasured():
    """Ten minutes apart at a one-hour horizon is nearly the same trade over and over."""
    cases = [Case(key=f"o-{i}", symbol="BTC-PERP", opened_at_s=START + i * 600, horizon_minutes=60,
                  signed_return_pct=(1.0 if i % 2 == 0 else -1.0) + spread(i),
                  context={"book_imbalance": 1.0 if i % 2 == 0 else -1.0}) for i in range(100)]
    cell = cell_of(assess_family(cases, costs=COSTS, draws=40))
    assert cell["independent_pooled"] < cell["context_available"]
    assert min(cell["independent_retained"], cell["independent_abstained"]) < MIN_INDEPENDENT_PER_GROUP
    assert cell["sample_state"] == "too_few_independent_windows"
    assert cell["tested"] is False and cell["selects"] is False


def test_the_correction_sees_the_whole_family_and_the_reading_says_how_high_the_bar_was():
    report = assess_family(sorting_cases(), costs=COSTS, horizons=[60], draws=40)
    assert len(report["cells"]) == 12  # six variables in two polarities, one horizon
    assert report["holm"]["cells_tested"] == 2  # only book_imbalance carries a reading here
    assert report["holm"]["first_rank_bar"] == pytest.approx(0.025 / 2)
    assert report["family"]["version"] == "entry-evidence-ablation-v1"
    assert report["population"]["context_coverage"]["book_imbalance"] == 100
    assert report["authority"] == "research_only" and report["promotion_allowed"] is False
    assert report["costs"]["total_pct"] == pytest.approx(0.12)


def test_the_hold_out_is_the_newest_share_and_never_shuffled():
    """The last 30 of 100 cases, and a context that stops working in them is caught."""
    cell = cell_of(assess_family(sorting_cases(flip_from=70), costs=COSTS, draws=40))
    assert cell["holdout_measured"] == 30
    assert cell["holdout_contrast_pct"] < 0 and cell["held_out"] is False
    # In sample it still looks like selection; only the hold-out disagrees.
    assert cell["contrast_pct"] > 0


def test_every_horizon_is_a_separate_cell_of_the_same_family():
    cases = ([case(i, value=1.0, signed=1.0, horizon=15) for i in range(10)]
             + [case(i + 10, value=1.0, signed=1.0, horizon=240) for i in range(10)])
    report = assess_family(cases, costs=COSTS, draws=20)
    assert report["population"]["horizons"] == [15, 240]
    assert len(report["cells"]) == 24
    assert cell_of(report, horizon=15)["eligible"] == 10
