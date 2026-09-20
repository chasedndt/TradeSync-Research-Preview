"""Opportunity briefs state each field from a stored record, and agree with the gate that admitted them.

The entry conditions restate the paper-signal gate's own comparisons on the values
it stored. The first tests hold that to decisions the gate itself produced, built
with the same fixtures the gate's own tests use, so a brief can never show an
admitted opportunity failing a condition, or a refused decision passing the
condition that refused it.
"""

import unittest

from paper_signal_support import NOW_MS, _decide, _directional, _evaluation, _feature
from tradesync_core.opportunity_brief import build_brief, compact, paper_state
from tradesync_core.opportunity_entry import entry_conditions, entry_view, regime_fit, stored_decision
from tradesync_core.opportunity_plan import NO_PLAN, net_reward_risk, plan_view

NOW_S = NOW_MS / 1000


class EntryConditionsAgreeWithTheGate(unittest.TestCase):
    def test_an_admitted_decision_meets_every_condition(self):
        decision = _decide()
        self.assertTrue(decision.admitted)
        view = entry_view(decision.to_dict())
        self.assertIs(view["admitted"], True)
        self.assertEqual((view["conditions_met"], view["conditions_checked"]), (4, 4))
        self.assertEqual(view["rejection_reasons"], [])

    def test_a_held_side_is_judged_against_the_hold_threshold(self):
        decision = _decide(directional=_directional(0.08), previous="LONG")
        self.assertTrue(decision.admitted)
        strength = next(c for c in entry_conditions(decision.to_dict()) if c["code"] == "direction_strength")
        self.assertEqual((strength["measured"], strength["required"], strength["met"]), (0.08, 0.05, True))
        self.assertIn("hold threshold", strength["basis"])

    def test_the_condition_that_refused_a_decision_is_the_one_shown_unmet(self):
        cases = {
            "direction_strength": _decide(directional=_directional(0.08), previous=None),
            "evidence_coverage": _decide(evaluation=_evaluation(coverage=0.1)),
            "directional_coverage": _decide(directional=_directional(0.42, coverage=0.2)),
            "evidence_age": _decide(features=[_feature(observed_at_ms=NOW_MS - 600_000)]),
        }
        for code, decision in cases.items():
            with self.subTest(condition=code):
                self.assertFalse(decision.admitted)
                condition = next(c for c in entry_conditions(decision.to_dict()) if c["code"] == code)
                self.assertIs(condition["met"], False)

    def test_an_opportunity_from_before_the_schema_says_nothing_was_stored(self):
        self.assertIsNone(stored_decision({"score_breakdown": {}, "warnings": []}))
        view = entry_view({"score_breakdown": {}})
        self.assertEqual((view["schema"], view["conditions"]), ("legacy", []))
        self.assertIn("not stored", view["detail"])


class RegimeFitTests(unittest.TestCase):
    def test_the_side_is_compared_with_the_move_before_entry(self):
        self.assertEqual(regime_fit("LONG", {"regime": "rising"})["fit"], "with")
        self.assertEqual(regime_fit("SHORT", {"regime": "falling"})["fit"], "with")
        self.assertEqual(regime_fit("LONG", {"regime": "falling"})["fit"], "against")
        self.assertEqual(regime_fit("SHORT", {"regime": "flat"})["fit"], "flat")

    def test_an_unlabelled_regime_names_why(self):
        unknown = regime_fit("LONG", {"regime": "unknown", "reason": "a gap in venue candles"})
        self.assertEqual(unknown["fit"], "unlabelled")
        self.assertIn("a gap in venue candles", unknown["detail"])
        self.assertEqual(regime_fit("LONG", None)["fit"], "unlabelled")

    def test_the_fit_is_a_description_and_says_so(self):
        self.assertIn("not a forecast", regime_fit("LONG", {"regime": "rising"})["basis"])


class PlanTests(unittest.TestCase):
    # distance 2, cost budget 0.2 per unit, quantity 2, reward-to-risk rule 2.
    PLAN = {
        "side": "long", "style": "intraday", "rules": {"version": "managed-paper-lifecycle-v3", "reward_risk": 2.0},
        "entry_price": 100.0, "quantity": 2.0, "notional": 200.0, "stop": 98.0, "target": 104.0,
        "expiry": 1_767_384_000, "atr": 1.2, "planned_risk_usdc": 4.4,
        "planning": {"reward_usdc": 8.0, "cost_budget_usdc": 0.4, "stop_distance": 2.0},
    }

    def position(self, state):
        return {"id": "p1", "opened_at_s": NOW_S, "evidence_sha256": "abc", "initial_plan": self.PLAN, "position_state": state}

    def test_no_position_means_no_levels_and_the_reason_is_stated(self):
        view = plan_view(None)
        self.assertEqual((view["status"], view["detail"]), ("none", NO_PLAN))
        self.assertNotIn("stop", view)
        self.assertIn("intraday", view["rules_at_entry"]["styles"])

    def test_the_frozen_plan_supplies_every_level(self):
        view = plan_view(self.position({"status": "open", "current_stop": 99.0, "current_stop_rule": "trailing_stop"}))
        self.assertEqual((view["stop"], view["targets"][0]["level"], view["invalidation"]["level"]), (98.0, 104.0, 98.0))
        self.assertEqual((view["invalidation"]["current_stop"], view["invalidation"]["current_stop_rule"]), (99.0, "trailing_stop"))
        self.assertEqual((view["estimated_risk_usdc"], view["estimated_reward_usdc"]), (4.4, 8.0))
        self.assertIsNone(view["exit"])

    def test_net_reward_to_risk_is_the_ratio_the_entry_gate_admitted(self):
        # The gate admits on (reward - budget) / (distance + budget) per unit; on the stored totals
        # that is (reward_usdc - cost_budget_usdc) / planned_risk_usdc, the same number.
        per_unit = (4.0 - 0.2) / (2.0 + 0.2)
        self.assertAlmostEqual(net_reward_risk(self.PLAN), round(per_unit, 4))
        self.assertIsNone(net_reward_risk({"planning": {}}))

    def test_a_closed_position_carries_its_exit(self):
        view = plan_view(self.position({"status": "closed", "exit": {"rule": "target", "fill_price": 104.0, "at": NOW_S},
                                         "net_estimate_usdc": 7.1}))
        self.assertEqual(view["exit"], {"rule": "target", "price": 104.0, "at_s": NOW_S, "net_estimate_usdc": 7.1})


class PaperStateTests(unittest.TestCase):
    def state(self, age_s=30.0, position=None, paused=False, enabled=False):
        opportunity = {"dir": "LONG", "snapshot_ts_s": NOW_S - age_s}
        return paper_state(opportunity=opportunity, position=position, entries_paused=paused,
                           execution_enabled=enabled, now_s=NOW_S)

    def test_a_recent_directional_opportunity_with_entries_admitted(self):
        result = self.state()
        self.assertEqual((result["label"], result["mode"]), ("Open to a paper entry", "paper"))
        self.assertIs(result["execution_authority"], False)

    def test_paused_entries_are_named_and_never_guessed(self):
        self.assertEqual(self.state(paused=True)["label"], "Paper entries paused")
        self.assertEqual(self.state(paused=None)["label"], "Paper entry state unknown")

    def test_an_old_opportunity_is_research_only_and_says_why(self):
        result = self.state(age_s=900)
        self.assertEqual(result["label"], "Paper research only")
        self.assertIn("older than 5 minutes", result["entry_refusal"])

    def test_an_opened_position_leads_whatever_the_age(self):
        position = {"position_state": {"status": "open"}}
        self.assertEqual(self.state(age_s=9000, position=position)["label"], "Paper position open")


class BriefTests(unittest.TestCase):
    def parts(self, confluence):
        return {
            "opportunity": {"id": "o1", "symbol": "BTC-PERP", "timeframe": "1m", "dir": "LONG", "bias": 0.42,
                            "quality": 55.0, "status": "new", "snapshot_ts_s": NOW_S - 30, "expires_at_s": NOW_S + 870,
                            "links": {"signal_id": "s1", "evidence_digest": "d1"}, "confluence": confluence,
                            "signal_id": "s1"},
            "regime": {"regime": "rising", "trailing_return_pct": 0.4, "lookback_minutes": 60, "reason": "",
                       "computed_at_s": NOW_S - 20},
            "position": None,
            "entry_reference_price": 100.5,
        }

    def brief(self, confluence):
        return build_brief(**self.parts(confluence), entries_paused=True, execution_enabled=False, now_s=NOW_S)

    def test_every_field_the_operator_needs_is_read_from_a_stored_record(self):
        brief = self.brief(_decide().to_dict())
        self.assertEqual((brief["symbol"], brief["timeframe"], brief["side"], brief["age_s"]), ("BTC-PERP", "1m", "LONG", 30))
        self.assertEqual(brief["regime_fit"]["fit"], "with")
        self.assertEqual(brief["entry"]["conditions_met"], 4)
        self.assertEqual(brief["plan"]["status"], "none")
        self.assertEqual(brief["provenance"]["rulebook"]["digest"], "rulebookdigest")
        self.assertEqual(brief["provenance"]["catalog"]["version"], "1.2.0")
        self.assertEqual(brief["provenance"]["entry_reference_price"], 100.5)
        self.assertEqual(brief["provenance"]["scorer"], "regime_paper_scorer")
        self.assertEqual(brief["evidence"]["contributing_features"][0]["feature_id"], "hl_return_1h_pct")
        self.assertEqual(brief["state"]["label"], "Paper entries paused")
        self.assertEqual(brief["authority"], "paper_only")

    def test_the_stored_scores_are_passed_through_untransformed(self):
        scores = self.brief(_decide().to_dict())["stored_scores"]
        self.assertEqual((scores["directional_score"], scores["evidence_coverage_pct"]), (0.42, 55.0))
        self.assertIn("not a probability", scores["basis"].replace("Neither is a probability", "not a probability"))

    def test_a_legacy_opportunity_carries_no_invented_provenance(self):
        brief = self.brief({"score_breakdown": {}})
        self.assertEqual(brief["entry"]["schema"], "legacy")
        self.assertIsNone(brief["provenance"]["scorer"])
        self.assertEqual(brief["provenance"]["evidence_digest"], "d1")

    def test_the_list_form_keeps_what_a_card_shows_and_nothing_heavier(self):
        card = compact(self.brief(_decide().to_dict()))
        self.assertEqual(set(card["entry"]), {"schema", "admitted", "conditions_met", "conditions_checked"})
        self.assertNotIn("evidence", card)
        self.assertEqual((card["plan"]["status"], card["state"]["label"]), ("none", "Paper entries paused"))


if __name__ == "__main__":
    unittest.main()
