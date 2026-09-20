"""The regime summary names its evidence, its disagreements, and why confidence is not higher.

The property that matters most is the last test in this file: an ``unknown``
condition always arrives with something that explains it, whichever way it came
about — a missing input, a proxy, a stale reading, a disagreement, or a
combination no rule matches.
"""

import unittest

from tradesync_core.regime_summary import (
    REQUIRED_INPUTS,
    components,
    conflicts,
    summarize,
    transitions,
)

NOW_MS = 1_700_000_000_000


def metric(name, status="REAL", age_ms=1_000):
    return {"metric": name, "status": status, "source": f"hyperliquid {name}", "last_updated": NOW_MS - age_ms}


def snapshot(**over):
    """A healthy reading: every required input read from the venue, fresh, and agreeing."""
    base = {
        "venue": "hyperliquid",
        "symbol": "BTC-PERP",
        "ts": NOW_MS - 1_000,
        "snapshot_age_ms": 1_000,
        "data_age_ms": 1_000,
        "regimes": {
            "funding": "neutral", "oi": "build", "volume": "high", "trend": "strong_trend",
            "market_condition": "trending_healthy", "confidence": "high", "confidence_note": None,
        },
        "funding": {"regime": "neutral"},
        "oi": {"regime": "build"},
        "volume": {"regime": "high"},
        "available_metrics": [metric("funding"), metric("oi"), metric("volume")],
    }
    base.update(over)
    return base


def summary(**over):
    return summarize(symbol="BTC-PERP", snapshot=snapshot(**over), history=(), now_ms=NOW_MS)


class ComponentTests(unittest.TestCase):
    def test_every_required_input_is_listed_with_its_source_and_age(self):
        rows = components(snapshot(), NOW_MS)
        self.assertEqual([r["input"] for r in rows], list(REQUIRED_INPUTS))
        self.assertTrue(all(r["usable"] and r["reason"] is None for r in rows))
        self.assertTrue(all(r["age_ms"] == 1_000 for r in rows))
        self.assertTrue(all(r["source"] for r in rows))

    def test_a_proxy_counts_as_present_but_is_never_classified_from(self):
        rows = components(snapshot(available_metrics=[metric("funding", "PROXY"), metric("oi"), metric("volume")]), NOW_MS)
        funding = next(r for r in rows if r["input"] == "funding")
        self.assertTrue(funding["present"])
        self.assertFalse(funding["usable"])
        self.assertIn("proxy", funding["reason"].lower())

    def test_a_reading_past_the_freshness_limit_is_not_usable_and_says_how_old(self):
        rows = components(snapshot(available_metrics=[metric("funding", age_ms=300_000), metric("oi"), metric("volume")]), NOW_MS)
        funding = next(r for r in rows if r["input"] == "funding")
        self.assertFalse(funding["usable"])
        self.assertIn("300s ago", funding["reason"])

    def test_an_absent_block_is_named_rather_than_silently_dropped(self):
        reading = snapshot(available_metrics=[metric("oi"), metric("volume")])
        reading.pop("funding")
        rows = components(reading, NOW_MS)
        funding = next(r for r in rows if r["input"] == "funding")
        self.assertFalse(funding["usable"])
        self.assertIn("Funding", funding["reason"])


class ConflictTests(unittest.TestCase):
    def test_paying_longs_leaving_the_trade_is_a_conflict(self):
        found = conflicts({"funding": "extreme_positive", "oi": "unwind", "volume": "high", "trend": "range"})
        self.assertEqual([c["inputs"] for c in found], [["funding", "oi"]])

    def test_a_trend_without_volume_is_a_conflict(self):
        found = conflicts({"funding": "neutral", "oi": "flat", "volume": "low", "trend": "strong_trend"})
        self.assertIn(["trend", "volume"], [c["inputs"] for c in found])

    def test_agreeing_readings_produce_no_conflict(self):
        self.assertEqual(conflicts(snapshot()["regimes"]), [])


class TransitionTests(unittest.TestCase):
    def test_consecutive_identical_labels_are_one_stretch(self):
        """A transition is dated to the reading that first carried the new label.

        Readings c and b both say "rising"; b is where the label actually
        changed and c merely continues it. Dating the change to c would report
        the regime as having turned later than it did, and would disagree with
        the held stretch below, which counts back to the same reading.
        """
        history = [
            {"regime": "rising", "computed_at_ms": 300, "opportunity_id": "c"},
            {"regime": "rising", "computed_at_ms": 200, "opportunity_id": "b"},
            {"regime": "falling", "computed_at_ms": 100, "opportunity_id": "a"},
        ]
        self.assertEqual(transitions(history), [
            {"from": "falling", "to": "rising", "at_ms": 200, "opportunity_id": "b", "trailing_return_pct": None},
        ])

    def test_the_label_now_in_force_counts_its_consecutive_readings(self):
        history = [
            {"regime": "rising", "computed_at_ms": 300},
            {"regime": "rising", "computed_at_ms": 200},
            {"regime": "falling", "computed_at_ms": 100},
        ]
        held = summarize(symbol="BTC-PERP", snapshot=snapshot(), history=history, now_ms=NOW_MS)["history"]["held"]
        self.assertEqual((held["regime"], held["readings"], held["since_ms"]), ("rising", 2, 200))


class SummaryTests(unittest.TestCase):
    def test_a_complete_fresh_agreeing_reading_is_at_the_highest_confidence(self):
        result = summary()
        self.assertEqual(result["confidence"]["level"], "high")
        self.assertEqual(result["missing_inputs"], [])
        self.assertEqual(result["why_not_higher"], [])
        self.assertTrue(result["at_highest_confidence"])
        self.assertTrue(result["current"]["known"])

    def test_a_proxy_lowers_confidence_and_is_named_as_the_reason(self):
        result = summary(available_metrics=[metric("funding", "PROXY"), metric("oi"), metric("volume")])
        self.assertEqual(result["confidence"]["level"], "medium")
        self.assertEqual([m["input"] for m in result["missing_inputs"]], ["funding"])
        self.assertTrue(any("proxy" in reason.lower() for reason in result["why_not_higher"]))
        self.assertFalse(result["at_highest_confidence"])

    def test_a_disagreement_holds_confidence_below_the_top_and_is_stated(self):
        result = summary(regimes={"funding": "extreme_positive", "oi": "unwind", "volume": "high",
                                  "trend": "range", "market_condition": "squeeze_risk", "confidence": "high"})
        self.assertEqual(result["confidence"]["level"], "medium")
        self.assertEqual(result["missing_inputs"], [])
        self.assertTrue(result["conflicts"])
        self.assertTrue(any("paying" in reason for reason in result["why_not_higher"]))

    def test_a_market_data_outage_names_every_input_rather_than_answering_unknown(self):
        result = summarize(symbol="BTC-PERP", snapshot=None, history=(), now_ms=NOW_MS)
        self.assertFalse(result["source_read"])
        self.assertEqual(result["current"]["condition"], "unknown")
        self.assertEqual([m["input"] for m in result["missing_inputs"]], list(REQUIRED_INPUTS))
        self.assertEqual(len(result["why_not_higher"]), len(REQUIRED_INPUTS))
        self.assertEqual(result["confidence"]["level"], "low")

    def test_an_unknown_condition_is_never_left_unexplained(self):
        """The guarantee the module exists for, over every way unknown can arise."""
        cases = {
            "nothing read": dict(snapshot=None),
            "one input missing": dict(snapshot=snapshot(
                regimes={**snapshot()["regimes"], "market_condition": "unknown"},
                available_metrics=[metric("oi"), metric("volume")])),
            "all present, no rule matches": dict(snapshot=snapshot(
                regimes={"funding": "neutral", "oi": "flat", "volume": "normal",
                         "trend": "range", "market_condition": "unknown", "confidence": "high"})),
        }
        for name, over in cases.items():
            with self.subTest(case=name):
                result = summarize(symbol="BTC-PERP", history=(), now_ms=NOW_MS, **over)
                self.assertEqual(result["current"]["condition"], "unknown")
                self.assertTrue(result["why_not_higher"], f"{name} left unknown unexplained")
                self.assertTrue(all(isinstance(reason, str) and reason.strip() for reason in result["why_not_higher"]))

    def test_the_condition_carries_a_readable_label_and_the_reading_time(self):
        result = summary()
        self.assertEqual(result["current"]["label"], "Trending, healthy")
        self.assertEqual(result["read_at_ms"], NOW_MS)
        self.assertEqual(result["observed_at_ms"], NOW_MS - 1_000)
        self.assertEqual(result["authority"], "context_only")


    def test_the_market_reading_has_an_age_even_when_the_snapshot_does_not_state_one(self):
        # The single-market snapshot carries only its observation time.
        without = snapshot()
        without.pop("snapshot_age_ms")
        result = summarize(symbol="BTC-PERP", snapshot=without, history=(), now_ms=NOW_MS)
        self.assertEqual(result["snapshot_age_ms"], 1_000)

    def test_a_stated_age_is_kept_and_a_missing_time_leaves_the_age_unknown(self):
        self.assertEqual(summary()["snapshot_age_ms"], 1_000)
        timeless = snapshot()
        timeless.pop("snapshot_age_ms")
        timeless.pop("ts")
        self.assertIsNone(summarize(symbol="BTC-PERP", snapshot=timeless, history=(), now_ms=NOW_MS)["snapshot_age_ms"])
        self.assertIsNone(summarize(symbol="BTC-PERP", snapshot=None, history=(), now_ms=NOW_MS)["snapshot_age_ms"])

if __name__ == "__main__":
    unittest.main()
