"""The opportunity builder's side of the regime-backed paper path: it preserves regime evidence, not re-scores it.

Moved out of test_regime_paper_pipeline.py unchanged.
"""

import asyncio
import sys
import types
import unittest
from datetime import datetime, timezone

from regime_paper_pipeline_support import FUSION_PACKAGE, _decision, _load_fusion_worker, producer


class FusionPassThroughTests(unittest.TestCase):
    """The opportunity builder must preserve regime evidence, not re-score it."""

    @classmethod
    def setUpClass(cls):
        cls.worker = _load_fusion_worker()

    def _envelope(self, decision, signal_id="signal-1"):
        return producer.build_stream_payload(
            decision, signal_id, datetime.now(timezone.utc)
        )

    def test_regime_envelope_is_recognised(self):
        envelope = self._envelope(_decision())
        self.assertTrue(self.worker.is_paper_signal_envelope(envelope))

    def test_legacy_envelope_is_not_treated_as_a_paper_signal(self):
        legacy = {
            "id": "legacy-1",
            "symbol": "BTC-PERP",
            "score": 3.0,
            "event_ids": ["11111111-1111-1111-1111-111111111111"],
        }
        self.assertFalse(self.worker.is_paper_signal_envelope(legacy))

    def test_envelope_without_a_digest_is_rejected(self):
        envelope = self._envelope(_decision())
        envelope["evidence_digest"] = ""
        self.assertFalse(self.worker.is_paper_signal_envelope(envelope))

    def test_opportunity_carries_the_directional_score_as_bias(self):
        """bias is a directional strength, so it must not carry suitability."""
        decision = _decision(score=0.42, coverage=0.55)
        envelope = self._envelope(decision)
        recorded = self._run_builder(envelope, insert_result="opp-1")
        self.assertEqual(recorded["bias"], decision.directional_score)
        self.assertAlmostEqual(recorded["quality"], decision.data_coverage * 100)
        self.assertEqual(recorded["dir"], "LONG")
        self.assertEqual(
            recorded["links"]["evidence_digest"], decision.evidence_digest
        )
        self.assertEqual(recorded["confluence"], decision.to_dict())

    def test_a_refusal_envelope_never_becomes_an_opportunity(self):
        decision = _decision(coverage=0.06)
        envelope = producer.build_stream_payload(
            decision, "signal-3", datetime.now(timezone.utc)
        )
        envelope["paper_signal"] = decision.to_dict()
        self.assertIsNone(self._run_builder(envelope, insert_result="opp-2"))

    def test_an_envelope_claiming_execution_authority_is_refused(self):
        decision = _decision()
        envelope = self._envelope(decision)
        envelope["paper_signal"]["execution_authority"] = True
        self.assertIsNone(self._run_builder(envelope, insert_result="opp-3"))

    def test_duplicate_delivery_does_not_double_count(self):
        envelope = self._envelope(_decision())
        before = self.worker.stats["opps_created"]
        self._run_builder(envelope, insert_result="opp-4")
        self._run_builder(envelope, insert_result=None)  # UNIQUE(signal_id) hit
        self.assertEqual(self.worker.stats["opps_created"], before + 1)

    def _run_builder(self, envelope, insert_result):
        """Run the builder against recording stand-ins and return the row."""
        worker = self.worker
        recorded = {}
        acked = []

        class FakeDb:
            async def insert_opportunity(self, data):
                recorded.update(data)
                return insert_result

        class FakeRedisClient:
            class client:
                @staticmethod
                async def xack(stream, group, msg_id):
                    acked.append(msg_id)

        db_module = sys.modules.setdefault(
            f"{FUSION_PACKAGE}.db", types.ModuleType(f"{FUSION_PACKAGE}.db")
        )
        db_module.db = FakeDb()
        original_redis = worker.redis_client
        worker.redis_client = FakeRedisClient
        try:
            asyncio.run(
                worker.build_paper_signal_opportunity(
                    envelope, "msg-1", envelope["symbol"], envelope["id"]
                )
            )
        finally:
            worker.redis_client = original_redis

        self.assertEqual(acked, ["msg-1"], "every message must be acknowledged")
        return recorded or None


if __name__ == "__main__":
    unittest.main()
