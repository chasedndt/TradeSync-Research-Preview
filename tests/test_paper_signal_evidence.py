"""What a paper signal decision binds: its digest, the evidence it records, and the inputs it refuses.

Identical evidence must produce an identical digest so a replay cannot create a
second opportunity. Moved out of test_paper_signal.py unchanged.
"""

import unittest

from tradesync_core.paper_signal import AdmissionPolicy, PaperSignalError, decide_paper_signal

from paper_signal_support import CATALOG, NOW_MS, _decide, _directional, _evaluation, _feature


class PaperSignalReplayTests(unittest.TestCase):
    def test_identical_evidence_produces_an_identical_digest(self):
        first = _decide()
        second = _decide()
        self.assertEqual(first.evidence_digest, second.evidence_digest)

    def test_a_changed_observation_time_changes_the_digest(self):
        first = _decide()
        second = _decide(features=[_feature(observed_at_ms=NOW_MS - 2_000)])
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_a_changed_policy_changes_the_digest(self):
        first = _decide()
        second = _decide(policy=AdmissionPolicy(minimum_coverage_to_emit=0.4))
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_changed_directional_evidence_changes_the_digest(self):
        first = _decide()
        second = _decide(directional=_directional(0.41))
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_feature_order_does_not_change_the_digest(self):
        a = _feature("hl_return_1h_pct")
        b = _feature("hl_depth_25bp_usd", block="liquidity")
        first = _decide(features=[a, b])
        second = _decide(features=[b, a])
        self.assertEqual(first.evidence_digest, second.evidence_digest)


class PaperSignalEvidenceTests(unittest.TestCase):
    def test_evidence_records_both_configuration_versions_and_the_policy(self):
        evidence = _decide().evidence
        self.assertEqual(evidence["catalog_version"], "1.2.0")
        self.assertEqual(evidence["catalog_digest"], "catalogdigest")
        self.assertEqual(evidence["rulebook_digest"], "rulebookdigest")
        self.assertEqual(evidence["rulebook_version"], "1.0.0")
        self.assertEqual(evidence["evaluated_at_ms"], NOW_MS)
        self.assertEqual(evidence["policy"]["minimum_coverage_to_emit"], 0.30)

    def test_evidence_keeps_the_block_contributions_and_risk_caps(self):
        evidence = _decide().evidence
        self.assertIn("liquidity", evidence["contributions"])
        self.assertEqual(evidence["risk_caps_applied"][0]["flag"], "low_data_coverage")
        self.assertIn("sum(weight * quality * score)", evidence["calculation"])


class PaperSignalInputTests(unittest.TestCase):
    def test_missing_symbol_is_a_programming_error_not_a_refusal(self):
        with self.assertRaises(PaperSignalError):
            decide_paper_signal(
                symbol="",
                evaluation=_evaluation(),
                feature_results=[],
                catalog_summary=CATALOG,
                evaluated_at_ms=NOW_MS,
            )

    def test_non_numeric_evaluation_is_rejected(self):
        broken = _evaluation()
        broken["weighted_score"] = "high"
        with self.assertRaises(PaperSignalError):
            _decide(broken)


if __name__ == "__main__":
    unittest.main()
