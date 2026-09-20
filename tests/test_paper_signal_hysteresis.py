"""Direction hysteresis: a held side must be easier to keep than a reversal is to establish.

Moved out of test_paper_signal.py unchanged, with the core-scorer hold window it
depends on.
"""

import unittest

from paper_signal_support import _decide, _directional


class DirectionHysteresisTests(unittest.TestCase):
    """A held side must be easier to keep than a reversal is to establish."""

    def test_a_new_direction_needs_the_entry_threshold(self):
        # 0.08 clears the 0.05 hold band but not the 0.15 entry band.
        decision = _decide(directional=_directional(0.08), previous=None)
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons if r["code"] == "score_inside_deadband"
        )
        self.assertIn("entry", reason["detail"])

    def test_the_same_score_is_admitted_when_that_side_is_already_held(self):
        decision = _decide(directional=_directional(0.08), previous="LONG")
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")

    def test_a_reversal_must_clear_the_entry_threshold(self):
        """Holding LONG must not flip to SHORT on a marginal negative score."""
        decision = _decide(directional=_directional(-0.08), previous="LONG")
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons if r["code"] == "score_inside_deadband"
        )
        self.assertIn("entry", reason["detail"])

    def test_a_decisive_reversal_is_still_admitted(self):
        decision = _decide(directional=_directional(-0.42), previous="LONG")
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "SHORT")

    def test_a_held_side_still_exits_below_the_hold_band(self):
        decision = _decide(directional=_directional(0.01), previous="LONG")
        self.assertFalse(decision.admitted)
        self.assertIn("hold", next(
            r["detail"] for r in decision.rejection_reasons
            if r["code"] == "score_inside_deadband"
        ))

    def test_previous_direction_is_bound_into_the_digest(self):
        a = _decide(directional=_directional(0.42), previous="LONG")
        b = _decide(directional=_directional(0.42), previous=None)
        self.assertNotEqual(a.evidence_digest, b.evidence_digest)


# --- direction hold window ---------------------------------------------------
#
# Loaded under the private alias: core-scorer packages its code as "app" like
# every other service.

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _service_import import load_service_module  # noqa: E402

_producer = load_service_module("core_scorer_app", "core-scorer", "paper_producer")


def test_the_hold_window_is_expressed_in_scoring_cycles() -> None:
    """A fixed duration would silently change stickiness when the cadence does.

    A held side is re-admitted every cycle for as long as it clears the hold
    threshold, so the bound that matters is "how many cycles of silence" — not
    "how many seconds".
    """
    assert _producer.direction_hold_max_age_seconds(60) == 60 * _producer.DIRECTION_HOLD_CYCLES
    assert _producer.direction_hold_max_age_seconds(15) == 15 * _producer.DIRECTION_HOLD_CYCLES
    # Halving the cadence halves the window; the cycle count is what is fixed.
    assert (
        _producer.direction_hold_max_age_seconds(30) * 2
        == _producer.direction_hold_max_age_seconds(60)
    )


def test_a_non_positive_cadence_is_refused() -> None:
    """It would make the hold window zero or negative, disabling hysteresis."""
    import pytest

    with pytest.raises(ValueError):
        _producer.direction_hold_max_age_seconds(0)
    with pytest.raises(ValueError):
        _producer.direction_hold_max_age_seconds(-60)
