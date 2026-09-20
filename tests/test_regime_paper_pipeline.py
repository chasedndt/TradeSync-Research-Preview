"""End-to-end contract tests for the regime-backed paper path.

These cover the two seams that carry evidence between services: what the
producer publishes, and what the opportunity builder does with it. The
builder's side is in test_regime_paper_pipeline_fusion.py.

Every service package in this repository is named ``app``, so importing one by
that name would shadow the others for the rest of the test session. Each is
loaded under a private name instead, in regime_paper_pipeline_support.py.
"""

import asyncio
import json
import unittest
from datetime import datetime, timezone

from regime_paper_pipeline_support import ROOT, RecordingRedis, _decision, _load_module, producer


class ProducerPublishTests(unittest.TestCase):
    def test_admitted_signal_is_published_with_its_evidence(self):
        decision = _decision()
        self.assertTrue(decision.admitted)
        redis = RecordingRedis()
        created = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        published = asyncio.run(
            producer.publish_decision(redis, decision, "signal-1", created)
        )
        self.assertTrue(published)
        stream, fields = redis.published[0]
        self.assertEqual(stream, producer.SIGNAL_STREAM)
        envelope = json.loads(fields["data"])
        self.assertEqual(envelope["schema_version"], "paper_signal_v1")
        self.assertEqual(envelope["evidence_digest"], decision.evidence_digest)
        self.assertEqual(envelope["paper_signal"]["direction"], "LONG")
        self.assertFalse(envelope["paper_signal"]["execution_authority"])

    def test_refusal_is_never_published(self):
        decision = _decision(coverage=0.06)
        self.assertFalse(decision.admitted)
        redis = RecordingRedis()
        published = asyncio.run(
            producer.publish_decision(
                redis, decision, "signal-2", datetime.now(timezone.utc)
            )
        )
        self.assertFalse(published)
        self.assertEqual(redis.published, [])

    def test_refusal_note_lists_every_reason_code(self):
        decision = _decision(score=0.0, coverage=0.0)
        note = producer._refusal_note(decision)
        self.assertIn("No paper opportunity produced", note)
        for reason in decision.rejection_reasons:
            self.assertIn(reason["code"], note)


class RegimeSourceTests(unittest.TestCase):
    """The producer must ask for the symbol it intends to record."""

    @classmethod
    def setUpClass(cls):
        cls.source = _load_module(
            "core_scorer_regime_source",
            ROOT / "services" / "core-scorer" / "app" / "regime_source.py",
        )

    def _fetch(self, payload, status=200):
        recorded = {}

        class FakeResponse:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise self.source.httpx.HTTPError("boom")

            def json(self):
                return payload

        class FakeClient:
            async def get(_self, url, params=None, timeout=None):
                recorded["url"] = url
                recorded["params"] = params
                return FakeResponse()

            async def aclose(_self):
                pass

        evidence = asyncio.run(
            self.source.fetch_regime_evidence(
                "ETH-PERP", state_api_url="http://state-api:8000", client=FakeClient()
            )
        )
        return evidence, recorded

    def test_the_requested_symbol_is_sent_to_the_state_api(self):
        payload = {
            "baseline_evaluation": {"weighted_score": 0.1},
            "feature_results": [],
            "catalog": {"version": "1.1.0"},
            "source_status": {"status": "live", "symbol": "ETH-PERP"},
        }
        evidence, recorded = self._fetch(payload)
        self.assertTrue(evidence.available)
        self.assertEqual(
            recorded["params"], {"venue": "hyperliquid", "symbol": "ETH-PERP"}
        )
        self.assertTrue(recorded["url"].endswith("/state/regime-lab/overview"))

    def test_non_live_observations_are_not_treated_as_evidence(self):
        payload = {
            "baseline_evaluation": {"weighted_score": 0.1},
            "source_status": {"status": "unavailable"},
        }
        evidence, _ = self._fetch(payload)
        self.assertFalse(evidence.available)
        self.assertIn("unavailable", evidence.reason)

    def test_a_missing_baseline_evaluation_is_not_a_zero_score(self):
        evidence, _ = self._fetch({"source_status": {"status": "live"}})
        self.assertFalse(evidence.available)
        self.assertEqual(evidence.evaluation, {})
        self.assertIn("no baseline evaluation", evidence.reason)
