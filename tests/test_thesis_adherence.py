"""Thesis adherence: did a position follow its own plan, scored from stored evidence only.

Every expected number here is calculated by hand in the assertions or in the
module's docstring, so a change in the arithmetic fails rather than quietly
producing a different score.
"""

from tradesync_core import thesis_adherence as adherence


def plan(**over):
    """The long scalp from the module docstring's worked example."""
    base = {
        "side": "long",
        "stop": 98.50,
        "target": 103.00,
        "expiry": 4600.0,
        "rules": {"max_depth_bps": 5.0},
        "slippage": {"entry": {"mid": 100.00, "fill_price": 100.02, "half_spread_bps": 1.0}},
    }
    base.update(over)
    return base


def closed(rule="operator_close", price=98.20, at=5000.0, **over):
    base = {"side": "long", "status": "closed", "exit": {"rule": rule, "fill_price": price, "at": at}}
    base.update(over)
    return base


def verdicts(result):
    return {check["name"]: check["verdict"] for check in result["checks"]}


def test_the_worked_example_scores_exactly_three_of_five():
    """The docstring's example, by hand: entry 2.0 bps inside a 6.0 bps zone (pass),
    price past the stop under an operator close (fail), no target claimed (pass),
    400s past expiry under a rule that is not the time expiry (fail), rule declared (pass).
    """
    result = adherence.score(plan(), closed())
    assert result["passed"] == 3 and result["failed"] == 2 and result["abstained"] == 0
    assert result["adherence"] == 0.6
    assert result["departures"] == ["stop_respected", "time_respected"]
    assert verdicts(result) == {
        "entry_in_zone": "pass", "stop_respected": "fail", "target_respected": "pass",
        "time_respected": "fail", "exit_rule_declared": "pass",
    }


def test_the_entry_zone_is_the_half_spread_plus_the_depth_bound():
    """1.0 bps of half spread plus a 5.0 bps bound is 6.0 bps either side of the mid."""
    result = adherence.score(plan(), closed())
    entry = result["checks"][0]
    assert entry["allowed"] == 6.0 and round(entry["observed"], 3) == 2.0
    assert entry["verdict"] == "pass"

    outside = adherence.score(plan(slippage={"entry": {"mid": 100.0, "fill_price": 100.07, "half_spread_bps": 1.0}}),
                              closed())
    assert verdicts(outside)["entry_in_zone"] == "fail"
    assert round(outside["checks"][0]["observed"], 3) == 7.0


def test_an_entry_exactly_on_the_edge_of_the_zone_is_inside_it():
    """The edge belongs to the zone, so a fill at the bound is not a departure.

    The bound here is the deviation itself rather than a round decimal: 100.06
    against a mid of 100.00 is 6.000000000000227 bps in binary floating point,
    not 6.0, and a test written on the decimal would be measuring the
    representation instead of the rule.
    """
    mid, fill = 100.0, 100.06
    deviation = (fill - mid) / mid * 10000.0

    def scored(bound):
        return adherence.score(
            plan(rules={"max_depth_bps": bound},
                 slippage={"entry": {"mid": mid, "fill_price": fill, "half_spread_bps": 0.0}}),
            closed())

    on_edge = scored(deviation)
    assert verdicts(on_edge)["entry_in_zone"] == "pass"
    assert on_edge["checks"][0]["observed"] == on_edge["checks"][0]["allowed"]
    assert verdicts(scored(deviation - 0.01))["entry_in_zone"] == "fail"


def test_a_position_opened_without_a_depth_bound_abstains_rather_than_being_judged_by_todays_rule():
    """Lifecycle v2 declared no bound. Judging it by today's would score an entry
    against a rule it was never opened under, so the check is absent and counted."""
    result = adherence.score(plan(rules={}), closed())
    assert verdicts(result)["entry_in_zone"] == "absent"
    assert result["abstained"] == 1 and result["checks_judged"] == 4
    # Two passes of the four judged; the abstention is not scored as a zero.
    assert result["adherence"] == 0.5


def test_an_open_position_abstains_on_every_exit_check():
    result = adherence.score(plan(), {"side": "long", "status": "open"})
    assert result["abstained"] == 4 and result["checks_judged"] == 1
    assert result["adherence"] == 1.0
    assert set(verdicts(result).values()) == {"pass", "absent"}


def test_a_stop_that_fires_passes_even_though_a_gap_fills_worse_than_the_stop():
    """The lifecycle prices a gap at the first observed price past the stop, on
    purpose. That is the stop doing its job, not a departure from the plan."""
    result = adherence.score(plan(), closed(rule="stop", price=98.10, at=2000.0))
    assert verdicts(result)["stop_respected"] == "pass"
    assert result["adherence"] == 1.0 and result["departures"] == []


def test_a_target_exit_that_never_reached_the_target_is_the_departure_caught():
    result = adherence.score(plan(), closed(rule="target", price=102.00, at=2000.0))
    assert verdicts(result)["target_respected"] == "fail"
    assert "never reached" in result["checks"][2]["detail"]
    assert result["adherence"] == 0.8


def test_a_target_exit_that_reached_the_target_passes():
    result = adherence.score(plan(), closed(rule="target", price=103.10, at=2000.0))
    assert verdicts(result)["target_respected"] == "pass"
    assert result["adherence"] == 1.0


def test_an_exit_rule_the_lifecycle_never_declared_is_a_departure():
    result = adherence.score(plan(), closed(rule="manual_override", price=101.0, at=2000.0))
    assert verdicts(result)["exit_rule_declared"] == "fail"
    assert result["departures"] == ["exit_rule_declared"]


def test_the_kill_switch_is_a_declared_exit():
    """It is an operator control, not an unplanned exit."""
    result = adherence.score(plan(), closed(rule="kill_switch", price=99.0, at=2000.0))
    assert verdicts(result)["exit_rule_declared"] == "pass"


def test_a_time_expiry_that_fires_late_is_not_a_departure():
    result = adherence.score(plan(), closed(rule="time_expiry", price=99.0, at=4600.5))
    assert verdicts(result)["time_respected"] == "pass"


def test_a_short_is_mirrored_and_its_stop_is_above_the_entry():
    short = plan(side="short", stop=101.50, target=97.00,
                 slippage={"entry": {"mid": 100.0, "fill_price": 99.98, "half_spread_bps": 1.0}})
    result = adherence.score(short, {"side": "short", "status": "closed",
                                     "exit": {"rule": "operator_close", "fill_price": 101.80, "at": 2000.0}})
    assert verdicts(result)["stop_respected"] == "fail"
    assert verdicts(result)["entry_in_zone"] == "pass"


def test_a_position_with_no_side_abstains_on_everything_and_scores_nothing():
    """No side means no level has a direction. A zero would read as "broke every rule"."""
    result = adherence.score({}, {})
    assert result["adherence"] is None and result["abstained"] == 5 and result["checks_judged"] == 0
    assert "no check could be evaluated" in result["reason"]


def test_missing_levels_abstain_rather_than_failing():
    result = adherence.score(plan(stop=None, target=None, expiry=None), closed(at=2000.0))
    marks = verdicts(result)
    assert marks["stop_respected"] == marks["target_respected"] == marks["time_respected"] == "absent"
    assert result["abstained"] == 3


def test_the_summary_keeps_abstentions_out_of_the_mean_and_counts_the_unscored():
    rows = [
        adherence.score(plan(), closed()),                                   # 0.6
        adherence.score(plan(), closed(rule="stop", price=98.10, at=2000.0)),  # 1.0
        adherence.score({}, {}),                                             # unscored
    ]
    summary = adherence.summarise(rows)
    assert summary["positions"] == 3 and summary["positions_scored"] == 2 and summary["unscored"] == 1
    assert summary["mean_adherence"] == 0.8  # (0.6 + 1.0) / 2, the unscored row excluded
    assert summary["checks_passed"] == 8 and summary["checks_failed"] == 2
    assert summary["checks_abstained"] == 5
    assert summary["by_check"]["stop_respected"] == {"pass": 1, "fail": 1, "absent": 1}


def test_an_empty_cohort_has_no_mean_rather_than_a_zero():
    summary = adherence.summarise([])
    assert summary["mean_adherence"] is None and summary["positions"] == 0


def test_nothing_here_reads_a_market():
    """Asserted structurally: the result carries only stored-evidence findings."""
    result = adherence.score(plan(), closed())
    assert "no market was re-read" in result["basis"]
    assert set(result) == {
        "schema_version", "adherence", "passed", "failed", "abstained", "checks_judged",
        "checks", "departures", "reason", "basis",
    }
