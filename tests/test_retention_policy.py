"""The retention policy states the windows the deleting code uses, and declares every deletion there is."""

import re
import unittest
from pathlib import Path

from tradesync_core import market_history
from tradesync_core.retention import DEFAULT_REFUSAL_RETENTION_DAYS, ROLLUP_TABLE
from tradesync_core.retention_policy import NOT_RETENTION, retention_policy

ROOT = Path(__file__).resolve().parents[1]


def policy():
    return retention_policy(correlation_keep_days=30, reconciliation_keep_days=14, recorder_every_s=3600)


class RetentionPolicyTests(unittest.TestCase):
    def test_market_history_windows_are_the_recorders_own_constants(self):
        windows = {w["table"]: w for w in policy()["windows"]}
        depth = windows["market_depth_snapshots"]
        self.assertEqual((depth["full_detail_days"], depth["downsampled_to_minutes"], depth["kept_days"]),
                         (market_history.DEPTH_FULL_DAYS, market_history.DOWNSAMPLED_MINUTES, market_history.DEPTH_KEEP_DAYS))
        oi = windows["market_open_interest"]
        self.assertEqual((oi["full_detail_days"], oi["kept_days"]), (market_history.OI_FULL_DAYS, market_history.OI_KEEP_DAYS))
        self.assertEqual(windows["market_liquidation_events"]["kept_days"], market_history.LIQUIDATIONS_KEEP_DAYS)
        self.assertIn("every 60 minutes", windows["market_liquidation_events"]["run_by"])

    def test_refusals_name_their_permanent_rollup_and_their_override(self):
        refusals = next(w for w in policy()["windows"] if w["table"] == "signals")
        self.assertEqual(refusals["kept_days"], DEFAULT_REFUSAL_RETENTION_DAYS)
        self.assertIn(ROLLUP_TABLE, refusals["detail"])
        self.assertIn("kept permanently", refusals["detail"])
        self.assertEqual(refusals["override"], "REFUSAL_RETENTION_DAYS in core-scorer")
        self.assertIn("admitted signals are never deleted", refusals["what"])

    def test_every_window_says_how_long_and_who_applies_it(self):
        for window in policy()["windows"]:
            with self.subTest(table=window["table"]):
                self.assertGreater(window["kept_days"], 0)
                self.assertTrue(window["run_by"] and window["detail"] and window["what"])

    def test_every_table_the_services_delete_from_is_declared_or_explained(self):
        """"Everything else is kept" is only true while no undeclared deletion exists."""
        sources = [*ROOT.glob("services/*/app/**/*.py"), *ROOT.glob("libs/tradesync_core/tradesync_core/**/*.py")]
        deleted = set()
        for path in sources:
            deleted |= set(re.findall(r"DELETE FROM (\w+)", path.read_text(encoding="utf-8")))
        self.assertTrue(deleted, "the scan found no deletion at all, so it is not reading the code")
        declared = {w["table"] for w in policy()["windows"]}
        self.assertEqual(deleted - declared - set(NOT_RETENTION), set())
        self.assertIn("Every other table is kept", policy()["kept"])


if __name__ == "__main__":
    unittest.main()
