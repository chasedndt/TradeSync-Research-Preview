"""The declared family: fixed before it was measured, and provably so."""

import pytest

from tradesync_core import entry_evidence_context as context
from tradesync_core import entry_evidence_family as family
from tradesync_core.source_comparison import THRESHOLD


def test_every_declared_variable_is_one_the_evidence_can_actually_produce():
    """A declaration naming a variable nothing computes would never be measured."""
    produced = set(context.from_parts(walls=None, liquidations=None, open_interest_latest=None,
                                      open_interest_earlier=None, funding_rate=None, lean=None, side="long"))
    assert {declaration.variable for declaration in family.DECLARATIONS} == produced


def test_both_polarities_of_every_variable_are_declared_together():
    cells = family.cells()
    assert len(cells) == len(family.DECLARATIONS) * 2 == 12
    assert {cell["polarity"] for cell in cells} == {"as_read", "inverted"}
    for cell in cells:
        assert cell["hypothesis"] and cell["label"] and cell["item"]


def test_the_balance_thresholds_are_the_frozen_v1_threshold_not_a_new_choice():
    thresholds = {d.variable: d.threshold for d in family.DECLARATIONS}
    assert thresholds["book_imbalance"] == thresholds["wall_asymmetry"] == THRESHOLD
    assert thresholds["liquidation_skew"] == THRESHOLD
    # Sign rules where the variable has no natural scale.
    assert thresholds["open_interest_change_1h_pct"] == thresholds["funding_received_bps_hour"] == 0.0
    assert thresholds["horizon_lean"] == 1.0


def test_the_digest_covers_every_threshold_and_polarity():
    """Changing any declared number must change the digest, or freezing proves nothing."""
    before = family.digest()
    assert family.to_dict()["sha256"] == before == family.digest()
    original = family.DECLARATIONS[0]
    changed = type(original)(**{**original.to_dict(), "threshold": 0.9})
    try:
        family.DECLARATIONS = (changed,) + family.DECLARATIONS[1:]
        assert family.digest() != before
    finally:
        family.DECLARATIONS = (original,) + family.DECLARATIONS[1:]
    assert family.digest() == before


def test_the_declaration_carries_its_rule_and_grants_nothing():
    declared = family.to_dict()
    assert "abstains" in declared["rule"] and "never read as a zero" in declared["rule"]
    assert declared["authority"] == "research_only" and declared["promotion_allowed"] is False
    assert declared["version"] == family.FAMILY_VERSION == "entry-evidence-ablation-v1"


def test_a_declaration_is_frozen_data_not_a_mutable_record():
    with pytest.raises(Exception):
        family.DECLARATIONS[0].threshold = 0.5
