"""Research trial specification v2, and proof that v1 did not move."""

import hashlib
import json

import pytest

from tradesync_core import research_trial as v1
from tradesync_core import research_trial_v2 as v2
from tradesync_core import research_trials as registry
from tradesync_core.paper_lifecycle_rules import LIFECYCLE_VERSION, catalog

UNIVERSE = ["BTC-PERP", "ETH-PERP", "HYPE-PERP", "NEAR-PERP"]
REGISTERED = 1_700_000_000.0

# The fingerprints of the frozen v1 protocol, recorded here so that any edit to it,
# however small, fails this test rather than silently invalidating a registration.
V1_FINGERPRINTS = {
    "scalp": "106f31cad730013cf8813ab8709128f01bc74665231f519b93d0232ef086bc2a",
    "intraday": "c53b3f0f982bd6d75781b3565882e23a3b8366036f2676a6f87a08417c8fbfd8",
    "swing": "401c1b59211b9263a287ee85357f3c228536297393c946520033569297f0bd19",
}


def test_v1_is_frozen_byte_for_byte():
    for style, expected in V1_FINGERPRINTS.items():
        spec = v1.specification(style)
        assert v1.fingerprint(spec) == expected
        assert spec["schema"] == "research-trial-v1"
        assert spec["universe"] == ["BTC-PERP", "ETH-PERP", "SOL-PERP"]
        assert "scenario funding" in spec["costs"]


def position(*, symbol="BTC-PERP", style="scalp", status="closed", entry=REGISTERED + 10, exit_at=REGISTERED + 100,
             funding="complete", version=LIFECYCLE_VERSION, schema="managed-paper-entry-evidence-v2", identity="p1",
             digest=None):
    evidence = {"schema_version": schema, "entry_time": entry, "external_context": {"hyperliquid_book_history": {
        "status": "observed", "cutoff": entry - 5,
        "samples": [{"time": entry - 10, "levels": [{"side": "bids", "notional_usd": 70.0},
                                                    {"side": "asks", "notional_usd": 30.0}]}]}}}
    row = {"id": identity, "symbol": symbol, "entry_evidence": evidence, "position_state": {
        "version": version, "rules": {"version": version}, "style": style, "side": "long", "status": status,
        "entry_time": entry, "exit_time": exit_at, "observation_gap": False, "notional": 250.0,
        "net_estimate_usdc": 1.0, "funding": {"status": funding, "missing_hours": [] if funding == "complete" else [1]}}}
    if digest is not None:
        row["evidence_sha256"] = digest
    return row


def test_the_universe_comes_from_the_api_and_an_unreadable_one_registers_nothing():
    spec = v2.specification("scalp", ["eth-perp", "BTC-PERP", "BTC-PERP"])
    assert spec["universe"] == ["BTC-PERP", "ETH-PERP"]
    for unreadable in ([], None, "BTC-PERP", ["not a symbol"], [""]):
        with pytest.raises(ValueError):
            v2.specification("scalp", unreadable)


def test_the_specification_names_settled_funding_and_the_rules_it_admits():
    spec = v2.specification("intraday", UNIVERSE)
    assert spec["schema"] == "research-trial-v2"
    assert spec["lifecycle_rules"] == {"version": LIFECYCLE_VERSION,
                                       "sha256": v2.LIFECYCLE_RULES["sha256"]}
    assert spec["entry_evidence_schema"] == "managed-paper-entry-evidence-v2"
    assert spec["context_family"]["cells"] == 12
    assert "hyperliquid_settled_hourly_v1" in spec["costs"] and "scenario" not in spec["costs"]
    assert "settled" in spec["funding_policy"] and "no rate is ever estimated" in spec["funding_policy"]


def test_the_frozen_lifecycle_digest_is_the_rules_that_are_actually_in_force():
    """A parameter changed without a new version would keep the name and change the experiment."""
    current = hashlib.sha256(
        json.dumps(catalog(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert v2.LIFECYCLE_RULES["version"] == LIFECYCLE_VERSION
    assert v2.LIFECYCLE_RULES["sha256"] == current


def test_a_different_universe_or_style_is_a_different_trial():
    base = v2.fingerprint(v2.specification("scalp", UNIVERSE))
    assert base != v2.fingerprint(v2.specification("scalp", UNIVERSE + ["SOL-PERP"]))
    assert base != v2.fingerprint(v2.specification("swing", UNIVERSE))
    assert base == v2.fingerprint(v2.specification("scalp", list(reversed(UNIVERSE))))
    assert base not in V1_FINGERPRINTS.values()


def test_only_positions_under_the_frozen_rules_and_universe_enter_the_population():
    spec = v2.specification("scalp", UNIVERSE)
    rows = [
        position(identity="admitted"),
        position(identity="symbol", symbol="DOGE-PERP"),
        position(identity="style", style="swing"),
        position(identity="rules", version="managed-paper-lifecycle-v1"),
        position(identity="evidence", schema="managed-paper-entry-evidence-v1"),
        position(identity="early", entry=REGISTERED - 1),
    ]
    result = v2.evaluate(spec, REGISTERED, REGISTERED + 1000, rows)
    assert result["comparison"]["eligible"] == 1
    assert result["outside_reasons"] == {"outside_frozen_universe": 1, "other_holding_style": 1,
                                         "other_lifecycle_rules": 1, "other_entry_evidence_schema": 1,
                                         "outside_entry_window": 1}
    assert result["state"] == "collecting" and result["promotion_allowed"] is False


def test_funding_that_has_not_settled_keeps_a_position_pending_then_excludes_it():
    spec = v2.specification("scalp", UNIVERSE)
    unsettled = [position(funding="awaiting_rows")]
    pending = v2.evaluate(spec, REGISTERED, REGISTERED + 1000, unsettled)
    assert pending["pending_reasons"] == {"awaiting_settled_funding": 1}
    assert pending["comparison"]["eligible"] == 0

    later = v2.evaluate(spec, REGISTERED, REGISTERED + 100 + v2.FUNDING_SETTLEMENT_GRACE_S, unsettled)
    assert later["excluded"] == {"funding_never_settled": 1}
    assert later["pending_outcomes"] == 0


def test_an_open_position_and_a_future_exit_are_pending_not_absent():
    spec = v2.specification("scalp", UNIVERSE)
    result = v2.evaluate(spec, REGISTERED, REGISTERED + 1000, [
        position(identity="open", status="open"),
        position(identity="future", exit_at=REGISTERED + 5000),
    ])
    assert result["pending_reasons"] == {"open": 1, "unresolved_exit": 1}


def test_entry_evidence_that_does_not_match_its_stored_digest_is_excluded():
    spec = v2.specification("scalp", UNIVERSE)
    result = v2.evaluate(spec, REGISTERED, REGISTERED + 1000, [position(digest="0" * 64)])
    assert result["excluded"] == {"entry_evidence_digest_mismatch": 1}
    assert result["comparison"]["eligible"] == 0


def test_a_changed_specification_cannot_silently_reuse_the_evaluator():
    spec = v2.specification("scalp", UNIVERSE)
    with pytest.raises(ValueError):
        v2.evaluate({**spec, "threshold": 0.4}, REGISTERED, REGISTERED + 1, [])
    with pytest.raises(ValueError):
        v2.evaluate(spec, REGISTERED, REGISTERED - 1, [])


def test_the_registry_offers_v2_keeps_v1_evaluable_and_refuses_new_v1_registrations():
    spec = registry.specification("scalp", symbols=UNIVERSE)
    assert spec["schema"] == registry.LATEST == "research-trial-v2"
    assert registry.fingerprint(spec) == v2.fingerprint(spec)

    with pytest.raises(ValueError, match="frozen for the trials registered under it"):
        registry.specification("scalp", version="research-trial-v1", symbols=UNIVERSE)
    with pytest.raises(ValueError):
        registry.specification("scalp", version="research-trial-v3", symbols=UNIVERSE)

    old = registry.evaluate(v1.specification("scalp"), REGISTERED, REGISTERED + 1000, [])
    assert old["schema"] == "research-trial-v1" and old["state"] == "collecting"
    new = registry.evaluate(spec, REGISTERED, REGISTERED + 1000, [position()])
    assert new["schema"] == "research-trial-v2" and new["comparison"]["eligible"] == 1


def test_a_specification_with_no_known_version_is_refused_before_any_query():
    with pytest.raises(ValueError):
        registry.version_of({"schema": "research-trial-v9", "style": "scalp"})
    with pytest.raises(ValueError):
        registry.evaluate({"style": "scalp"}, REGISTERED, REGISTERED + 1, [])
