"""The context variables read from evidence frozen at an entry.

The document these read is built by ``paper_entry_evidence.document`` itself, so
the tests fail if the frozen shape and the readings ever drift apart, and the
entry cut-off is exercised through the real one.
"""

from tradesync_core import entry_evidence_context as context
from tradesync_core.paper_entry_evidence import document

ENTRY = 1_700_000_000.0


def walls(bid_usd=70.0, ask_usd=30.0, below=60.0, above=40.0):
    total = bid_usd + ask_usd
    return {"below": {"price": 99.0, "usd": below, "distance_bps": -100.0},
            "above": {"price": 101.0, "usd": above, "distance_bps": 100.0},
            "bid_usd": bid_usd, "ask_usd": ask_usd,
            "imbalance": (bid_usd - ask_usd) / total, "within_pct": 5.0}


def gathered(*, liquidations=(("long", 100.0),), received=ENTRY - 10, lean="long"):
    """Items in the shape ``paper_entry_rows`` and ``paper_entry_sources`` produce."""
    stamped = {"observed_at": ENTRY - 30, "received_at": received}
    return {
        "resting_liquidity": {"source": "market_depth_snapshots",
                              "records": [{"id": "recorded_book", "walls": walls(), **stamped}]},
        "liquidations": {"source": "market_liquidation_events", "records": [
            {"id": f"bybit:{index}", "side": side, "notional_usd": usd, **stamped}
            for index, (side, usd) in enumerate(liquidations)]},
        "open_interest": {"source": "market_open_interest", "records": [
            {"id": "latest", "reading": "latest", "open_interest_usd": 110.0,
             "predicted_funding_rate": 0.0000125, **stamped},
            {"id": "an hour earlier", "reading": "an hour earlier", "open_interest_usd": 100.0,
             "predicted_funding_rate": 0.0000125, "observed_at": ENTRY - 3630, "received_at": ENTRY - 3600}]},
        "horizon_measurement": {"source": "/state/market/horizons", "records": [
            {"id": "short", "part": "short", "horizons": [{"key": "15m", "band": "short", "lean": lean}], **stamped}]},
    }


def test_each_variable_is_signed_by_the_call_it_was_frozen_beside():
    """Positive always means "this context pointed the way the call did"."""
    long_read = context.from_document(document(gathered(), ENTRY), "long")
    short_read = context.from_document(document(gathered(), ENTRY), "short")

    assert long_read["book_imbalance"] == 0.4 and short_read["book_imbalance"] == -0.4
    assert long_read["wall_asymmetry"] == 0.2 and short_read["wall_asymmetry"] == -0.2
    # Liquidated longs are forced selling: that points down, so it aligns with a short.
    assert long_read["liquidation_skew"] == -1.0 and short_read["liquidation_skew"] == 1.0
    # A positive funding rate is longs paying shorts.
    assert long_read["funding_received_bps_hour"] == -0.125 and short_read["funding_received_bps_hour"] == 0.125
    assert long_read["horizon_lean"] == 1.0 and short_read["horizon_lean"] == -1.0


def test_open_interest_change_has_no_direction_of_its_own():
    reading = context.from_document(document(gathered(), ENTRY), "long")
    assert reading["open_interest_change_1h_pct"] == 10.0
    assert context.from_document(document(gathered(), ENTRY), "short")["open_interest_change_1h_pct"] == 10.0


def test_a_record_received_after_the_entry_never_reaches_a_variable():
    """The entry cut-off is the document's; a variable can only read what it kept."""
    late = document(gathered(received=ENTRY + 1), ENTRY)
    assert late["items"]["liquidations"]["status"] == "missing"
    reading = context.from_document(late, "long")
    assert reading["liquidation_skew"] is None
    assert reading["book_imbalance"] is None and reading["horizon_lean"] is None


def test_a_missing_item_reads_as_no_value_never_as_zero():
    empty = document({}, ENTRY)
    assert context.from_document(empty, "long") == {
        "book_imbalance": None, "wall_asymmetry": None, "liquidation_skew": None,
        "open_interest_change_1h_pct": None, "funding_received_bps_hour": None, "horizon_lean": None}


def test_both_sides_liquidated_equally_is_a_measured_zero():
    reading = context.from_document(document(gathered(liquidations=(("long", 50.0), ("short", 50.0))), ENTRY), "long")
    assert reading["liquidation_skew"] == 0.0


def test_unusable_inputs_fail_closed_rather_than_guessing():
    assert context.book_imbalance(walls(), "sideways") is None
    assert context.book_imbalance(None, "long") is None
    assert context.wall_asymmetry({"below": None, "above": {"usd": 1.0}}, "long") is None
    assert context.liquidation_skew(0.0, 0.0, "long") is None
    assert context.open_interest_change_pct(110.0, 0.0) is None
    assert context.open_interest_change_pct(float("nan"), 100.0) is None
    assert context.funding_received_bps_hour(True, "long") is None
    assert context.horizon_lean_alignment("unavailable", "long") is None
    assert context.horizon_lean_alignment("flat", "long") == 0.0
