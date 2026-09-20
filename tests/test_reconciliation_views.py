"""The five reconciliation views: read-only comparisons that never guess which side is right.

Two properties are asserted throughout, because both have been got wrong before
in this repository: a counterpart outside the query window is not a finding, and
a view that compared nothing is not a clean reconciliation.
"""

from tradesync_core import reconciliation_views as views

NOW = 10_000_000.0
WINDOW = "the last 24 hours"


def kinds(view):
    return [finding["kind"] for finding in view.to_dict()["findings"]]


# --- orphaned events -------------------------------------------------------

def event(identity, **over):
    return {"id": identity, "source": "hyperliquid", "kind": "trade", "symbol": "BTC-PERP", "ts": NOW, **over}


def test_an_event_no_signal_referenced_is_an_orphan():
    view = views.orphaned_events([event("e1"), event("e2")], [{"id": "s1", "event_ids": ["e1"]}], window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["orphaned_event"]
    assert body["findings"][0]["subject_id"] == "e2"
    assert body["considered"] == 2 and body["clean"] is False
    assert body["compared"] and body["window"] == WINDOW


def test_a_signal_referencing_an_event_outside_the_window_is_not_a_missing_event():
    """Otherwise the query bound manufactures a finding, exactly as it once did for orders."""
    view = views.orphaned_events([event("e1")], [{"id": "s1", "event_ids": ["e1", "older"]}], window=WINDOW)
    body = view.to_dict()
    assert body["clean"] is True
    assert body["outside_window"] == ["older"]


def test_a_view_that_compared_nothing_says_so_rather_than_reading_as_clean():
    body = views.orphaned_events([], [], window=WINDOW).to_dict()
    assert body["considered"] == 0
    assert "nothing to compare" in body["summary"]


# --- duplicate candidates --------------------------------------------------

def opportunity(identity, at, digest=None, symbol="BTC-PERP", direction="LONG"):
    return {"id": identity, "symbol": symbol, "timeframe": "1m", "dir": direction,
            "snapshot_ts_s": at, "evidence_digest": digest}


def test_two_opportunities_from_one_evidence_digest_are_the_certain_duplicate():
    """The digest exists to make a replay idempotent rather than create a second call."""
    view = views.duplicate_candidates(
        [opportunity("o1", NOW, "d" * 64), opportunity("o2", NOW + 5, "d" * 64)], window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["duplicate_evidence_digest"]
    assert body["findings"][0]["observed"]["opportunity_ids"] == ["o1", "o2"]
    # Reported once, as the stronger finding, not also as a repeat.
    assert "repeated_call" not in kinds(view)


def test_a_second_call_on_one_market_inside_the_repeat_window_is_a_candidate():
    view = views.duplicate_candidates(
        [opportunity("o1", NOW, "a" * 64), opportunity("o2", NOW + 30, "b" * 64)], window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["repeated_call"]
    assert body["findings"][0]["observed"]["seconds_apart"] == 30.0
    assert body["findings"][0]["observed"]["previous_opportunity_id"] == "o1"


def test_calls_further_apart_than_the_repeat_window_are_not_reported():
    view = views.duplicate_candidates(
        [opportunity("o1", NOW, "a" * 64), opportunity("o2", NOW + 120, "b" * 64)], window=WINDOW)
    assert view.to_dict()["clean"] is True


def test_the_same_moment_on_different_markets_is_not_a_duplicate():
    view = views.duplicate_candidates(
        [opportunity("o1", NOW, "a" * 64), opportunity("o2", NOW, "b" * 64, symbol="ETH-PERP")], window=WINDOW)
    assert view.to_dict()["clean"] is True


def test_opposite_sides_on_one_market_are_not_a_duplicate():
    view = views.duplicate_candidates(
        [opportunity("o1", NOW, "a" * 64), opportunity("o2", NOW + 5, "b" * 64, direction="SHORT")], window=WINDOW)
    assert view.to_dict()["clean"] is True


# --- stale approvals -------------------------------------------------------

def envelope(identity, created, consumed=None):
    return {"envelope_id": identity, "approval_id": f"a-{identity}", "candidate_id": f"c-{identity}",
            "created_at_s": created, "consumed_at_s": consumed}


def test_an_approval_never_consumed_past_its_validity_is_stale():
    view = views.stale_approvals([envelope("e1", NOW - 5 * 3600)], NOW, window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["stale_approval"]
    assert body["findings"][0]["observed"]["age_s"] == 18000.0


def test_an_approval_inside_its_validity_or_already_consumed_is_not_stale():
    view = views.stale_approvals(
        [envelope("e1", NOW - 3600), envelope("e2", NOW - 5 * 3600, consumed=NOW - 4 * 3600)], NOW, window=WINDOW)
    body = view.to_dict()
    assert body["clean"] is True and body["considered"] == 2


def test_an_approval_without_a_creation_time_is_reported_rather_than_skipped():
    view = views.stale_approvals([envelope("e1", None)], NOW, window=WINDOW)
    assert kinds(view) == ["approval_without_a_time"]


# --- partial orders --------------------------------------------------------

def order(identity, status, created, request=None, response=None):
    return {"id": identity, "decision_id": f"d-{identity}", "status": status, "created_at_s": created,
            "request": request or {}, "response": response or {}, "dry_run": True}


def test_an_order_still_in_flight_past_the_settle_window_is_reported():
    view = views.partial_orders([order("o1", "placed", NOW - 600)], NOW, window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["order_not_terminal"]
    assert body["findings"][0]["observed"]["age_s"] == 600.0


def test_a_terminal_order_and_one_still_settling_are_both_clean():
    view = views.partial_orders(
        [order("o1", "filled", NOW - 600), order("o2", "placed", NOW - 60)], NOW, window=WINDOW)
    assert view.to_dict()["clean"] is True


def test_a_fill_smaller_than_the_request_is_a_partial_fill():
    view = views.partial_orders(
        [order("o1", "filled", NOW - 600, {"size_usd": 100.0}, {"filled_usd": 60.0})], NOW, window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["partial_fill"]
    assert body["findings"][0]["observed"] == {"decision_id": "d-o1", "requested_usd": 100.0, "filled_usd": 60.0}


def test_a_fill_short_by_less_than_a_cent_is_rounding_not_a_partial_fill():
    view = views.partial_orders(
        [order("o1", "filled", NOW - 600, {"size_usd": 100.0}, {"filled_usd": 99.995})], NOW, window=WINDOW)
    assert view.to_dict()["clean"] is True


def test_no_order_has_ever_been_placed_so_the_view_considers_nothing():
    """The honest reading of an empty order table, which is the live state."""
    body = views.partial_orders([], NOW, window=WINDOW).to_dict()
    assert body["considered"] == 0 and "nothing to compare" in body["summary"]


# --- missing outcomes ------------------------------------------------------

HORIZONS = (15, 60, 240)


def call(identity, opened, outcomes=()):
    return {"id": identity, "symbol": "BTC-PERP", "opened_at_s": opened, "outcomes": list(outcomes)}


def test_only_horizons_that_have_actually_closed_are_reported_missing():
    """Opened 200 minutes ago: the 15 and 60 minute windows have closed, the 240 has not."""
    view = views.missing_outcomes([call("o1", NOW - 200 * 60)], NOW, HORIZONS, window=WINDOW)
    body = view.to_dict()
    assert kinds(view) == ["missing_outcome", "missing_outcome"]
    assert [f["observed"]["horizon_minutes"] for f in body["findings"]] == [15, 60]


def test_a_verdict_still_pending_after_its_window_closed_is_a_separate_finding():
    view = views.missing_outcomes(
        [call("o1", NOW - 200 * 60, [{"horizon_minutes": 15, "status": "measured"},
                                     {"horizon_minutes": 60, "status": "pending"}])],
        NOW, HORIZONS, window=WINDOW)
    assert kinds(view) == ["outcome_still_pending"]


def test_a_horizon_that_could_not_be_measured_is_not_reported_as_missing():
    """``insufficient_candles`` is a recorded verdict: the gap was reported, not skipped."""
    view = views.missing_outcomes(
        [call("o1", NOW - 200 * 60, [{"horizon_minutes": 15, "status": "insufficient_candles"},
                                     {"horizon_minutes": 60, "status": "measured"}])],
        NOW, HORIZONS, window=WINDOW)
    assert view.to_dict()["clean"] is True


def test_an_opportunity_without_a_time_cannot_have_a_closed_horizon():
    view = views.missing_outcomes([call("o1", None)], NOW, HORIZONS, window=WINDOW)
    assert kinds(view) == ["opportunity_without_a_time"]


# --- combined --------------------------------------------------------------

def test_the_combined_reading_sums_the_views_and_states_one_verdict():
    combined = views.combine([
        views.orphaned_events([event("e1")], [{"id": "s1", "event_ids": ["e1"]}], window=WINDOW),
        views.partial_orders([order("o1", "placed", NOW - 600)], NOW, window=WINDOW),
    ])
    assert combined["findings"] == 1 and combined["records_compared"] == 2
    assert combined["clean"] is False
    assert len(combined["views"]) == 2
    assert all(view["compared"] and view["window"] for view in combined["views"])


def test_a_clean_combined_reading_is_stated_as_a_result():
    combined = views.combine([views.orphaned_events([event("e1")], [{"id": "s1", "event_ids": ["e1"]}], window=WINDOW)])
    assert combined["clean"] is True and "no divergence" in combined["summary"]


def test_the_combined_reading_can_change_nothing():
    """Asserted structurally: the shape carries findings and counts, no instruction."""
    combined = views.combine([])
    assert set(combined) == {"schema_version", "views", "findings", "records_compared", "clean", "summary", "note"}
    assert "can place, amend, cancel or consume" in combined["note"]
