"""Admission tests for the paper signal decision.

Every case here asserts a deterministic verdict from fixed evidence. A refusal
must explain itself, and identical evidence must produce an identical digest so
a replay cannot create a second opportunity.

The digest, evidence and input tests are in test_paper_signal_evidence.py and
direction hysteresis in test_paper_signal_hysteresis.py; the fixed evidence all
of them decide from is in paper_signal_support.py.
"""

import unittest

from paper_signal_support import NOW_MS, _decide, _directional, _evaluation, _feature


class PaperSignalAdmissionTests(unittest.TestCase):
    def test_sufficient_evidence_is_admitted_with_a_direction(self):
        decision = _decide()
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")
        self.assertEqual(decision.rejection_reasons, [])
        self.assertEqual(len(decision.contributing_features), 1)

    def test_direction_follows_directional_evidence_not_the_blended_score(self):
        """A negative suitability score must not imply SHORT."""
        decision = _decide(_evaluation(score=-0.42), directional=_directional(0.42))
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "LONG")

    def test_negative_directional_evidence_is_admitted_as_short(self):
        decision = _decide(directional=_directional(-0.42))
        self.assertTrue(decision.admitted)
        self.assertEqual(decision.direction, "SHORT")

    def test_suitability_alone_can_never_set_a_direction(self):
        """Deep books make a market tradeable; they do not make it a buy."""
        decision = _decide(directional=None)
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.direction, "NONE")
        self.assertIn(
            "no_directional_evidence",
            [r["code"] for r in decision.rejection_reasons],
        )

    def test_thin_directional_coverage_is_refused(self):
        decision = _decide(directional=_directional(0.42, coverage=0.2))
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons
            if r["code"] == "directional_coverage_below_floor"
        )
        self.assertIn("hl_return_1h_pct", reason["detail"])

    def test_admitted_decision_never_claims_execution_authority(self):
        payload = _decide().to_dict()
        self.assertFalse(payload["execution_authority"])
        self.assertEqual(payload["mode"], "paper_shadow")

    def test_coverage_below_the_floor_refuses_and_names_missing_blocks(self):
        decision = _decide(
            _evaluation(coverage=0.0627875, missing=["positioning", "macro_flows"])
        )
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.direction, "NONE")
        codes = [reason["code"] for reason in decision.rejection_reasons]
        self.assertIn("coverage_below_emit_floor", codes)
        detail = next(
            r["detail"]
            for r in decision.rejection_reasons
            if r["code"] == "coverage_below_emit_floor"
        )
        self.assertIn("positioning", detail)
        self.assertIn("macro_flows", detail)

    def test_missing_source_produces_an_explained_refusal_not_an_error(self):
        decision = _decide(_evaluation(score=0.0, coverage=0.0), features=[],
                           directional=None)
        self.assertFalse(decision.admitted)
        codes = [reason["code"] for reason in decision.rejection_reasons]
        self.assertIn("no_admitted_evidence", codes)
        self.assertIn("coverage_below_emit_floor", codes)

    def test_score_inside_the_deadband_is_not_a_weak_direction(self):
        decision = _decide(directional=_directional(0.01))
        self.assertFalse(decision.admitted)
        self.assertEqual(decision.direction, "NONE")
        self.assertIn(
            "score_inside_deadband",
            [reason["code"] for reason in decision.rejection_reasons],
        )

    def test_stale_evidence_is_rejected_with_its_measured_age(self):
        stale = _feature(observed_at_ms=NOW_MS - 600_000)
        decision = _decide(features=[stale])
        self.assertFalse(decision.admitted)
        reason = next(
            r for r in decision.rejection_reasons if r["code"] == "evidence_stale"
        )
        self.assertIn("600000 ms old", reason["detail"])
        self.assertEqual(reason["feature_id"], "hl_return_1h_pct")

    def test_future_timestamped_evidence_is_rejected(self):
        ahead = _feature(observed_at_ms=NOW_MS + 5_000)
        decision = _decide(features=[ahead])
        self.assertFalse(decision.admitted)
        self.assertIn(
            "evidence_timestamped_in_future",
            [reason["code"] for reason in decision.rejection_reasons],
        )

    def test_proxy_and_context_only_provenance_cannot_score(self):
        for provenance in ("proxy", "context_only", "unavailable"):
            with self.subTest(provenance=provenance):
                decision = _decide(features=[_feature(provenance=provenance)])
                self.assertFalse(decision.admitted)
                self.assertIn(
                    "inadmissible_provenance",
                    [r["code"] for r in decision.rejection_reasons],
                )

    def test_features_not_allowed_to_score_are_excluded_from_evidence(self):
        decision = _decide(features=[_feature(scoring_allowed=False)])
        self.assertEqual(decision.contributing_features, [])
        self.assertIn(
            "no_admitted_evidence",
            [reason["code"] for reason in decision.rejection_reasons],
        )

    def test_fully_capped_paper_risk_refuses_to_emit(self):
        decision = _decide(_evaluation(risk=0.0))
        self.assertFalse(decision.admitted)
        self.assertIn(
            "paper_risk_fully_capped",
            [reason["code"] for reason in decision.rejection_reasons],
        )
