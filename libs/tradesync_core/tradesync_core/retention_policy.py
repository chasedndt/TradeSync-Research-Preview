"""How long TradeSync keeps what it records, declared from the code that does the deleting.

Settings shows retention so an operator knows how far back a record goes before
asking a question of it. Written out by hand in the Cockpit, it would drift the
first time a window changed, so each window here is read from the constant the
deleting code itself uses:

- market history (order books, open interest, received liquidations):
  ``tradesync_core.market_history``, applied by state-api's market recorder;
- scorer refusals: ``tradesync_core.retention``, applied by core-scorer, which
  rolls each refusal up into a permanent daily record before deleting it;
- paper correlation measurements and reconciliation runs: the defaults of the
  state-api store functions that delete them, passed in by the route.

Every other table is kept. ``tests/test_retention_policy.py`` scans the service
code for deletions and fails when a table is deleted from that this policy
neither declares nor explains, so that sentence cannot quietly become false.
"""

from __future__ import annotations

from typing import Any

from . import market_history as history
from .retention import DEFAULT_REFUSAL_RETENTION_DAYS, ROLLUP_TABLE

SCHEMA_VERSION = "retention_policy_v1"

# Deletions that are not retention: a row replaced or removed by a deliberate act, never aged out.
NOT_RETENTION = {
    "graph_snapshots": "a knowledge-graph snapshot is replaced when the graph is rebuilt",
    "operator_public_settings": "a public setting is removed only when an operator clears it",
    "mobile_web_push_subscriptions": (
        "a browser's push subscription is removed only when the operator removes that browser; "
        "one a push service reports gone is marked expired and kept"
    ),
}

KEPT = ("Every other table is kept: nothing else in the service code deletes rows by age. "
        + "; ".join(f"{table}: {why}" for table, why in NOT_RETENTION.items()) + ".")
NOTE = ("Read from the constants the deleting code uses. The refusal window can be overridden per deployment in "
        "core-scorer, which this reading cannot see; the value shown is the declared default. Live streams in Redis "
        "are short and bounded, and are not covered here.")


def _window(table: str, what: str, *, kept_days: int, run_by: str, detail: str, full_detail_days: int | None = None,
            downsampled_to_minutes: int | None = None, override: str | None = None) -> dict[str, Any]:
    return {"table": table, "what": what, "kept_days": kept_days, "full_detail_days": full_detail_days,
            "downsampled_to_minutes": downsampled_to_minutes, "run_by": run_by, "override": override, "detail": detail}


def retention_policy(*, correlation_keep_days: int, reconciliation_keep_days: int, recorder_every_s: int) -> dict[str, Any]:
    """Every age-based deletion, with how long its rows are kept, in what detail, and which process applies it."""
    minutes = history.DOWNSAMPLED_MINUTES
    recorder = f"state-api market recorder, every {recorder_every_s // 60} minutes"
    return {
        "schema_version": SCHEMA_VERSION,
        "windows": [
            _window(
                "market_depth_snapshots", "Aggregated Hyperliquid order books",
                kept_days=history.DEPTH_KEEP_DAYS, full_detail_days=history.DEPTH_FULL_DAYS,
                downsampled_to_minutes=minutes, run_by=recorder,
                detail=(f"Every minute for {history.DEPTH_FULL_DAYS} days, then one book per {minutes} minutes, "
                        f"deleted after {history.DEPTH_KEEP_DAYS} days."),
            ),
            _window(
                "market_open_interest", "Hyperliquid open interest, with the mark and funding read beside it",
                kept_days=history.OI_KEEP_DAYS, full_detail_days=history.OI_FULL_DAYS,
                downsampled_to_minutes=minutes, run_by=recorder,
                detail=(f"Every minute for {history.OI_FULL_DAYS} days, then one reading per {minutes} minutes, "
                        f"deleted after {history.OI_KEEP_DAYS} days."),
            ),
            _window(
                "market_liquidation_events", "Liquidations received from Bybit and Binance",
                kept_days=history.LIQUIDATIONS_KEEP_DAYS, run_by=recorder,
                detail=f"Each event is kept {history.LIQUIDATIONS_KEEP_DAYS} days.",
            ),
            _window(
                "signals", "Scorer refusals; admitted signals are never deleted",
                kept_days=DEFAULT_REFUSAL_RETENTION_DAYS, run_by="core-scorer retention pass",
                override="REFUSAL_RETENTION_DAYS in core-scorer",
                detail=(f"Full refusal rows are kept {DEFAULT_REFUSAL_RETENTION_DAYS} days by default. Each is rolled "
                        f"up into {ROLLUP_TABLE} in the same transaction that deletes it, and the rollup is kept "
                        "permanently, so refusal counts never shrink."),
            ),
            _window(
                "paper_correlation_measurements", "Paper correlation measurements",
                kept_days=correlation_keep_days, run_by="state-api paper correlation job",
                detail=f"Each measurement is kept {correlation_keep_days} days.",
            ),
            _window(
                "paper_reconciliation_runs", "Paper reconciliation runs",
                kept_days=reconciliation_keep_days, run_by="state-api paper reconciliation runner",
                detail=f"Each run is kept {reconciliation_keep_days} days.",
            ),
        ],
        "kept": KEPT,
        "not_retention": dict(NOT_RETENTION),
        "note": NOTE,
    }
