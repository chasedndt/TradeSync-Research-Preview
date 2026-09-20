from datetime import datetime, timezone

from tradesync_core.paper_style_alignment import assess_style_alignment

NOW = datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc)


def page(*, lean="down", sigma=1.2, measured=NOW):
    stamp = measured.isoformat() if measured is not None else None
    return {
        "computed_at": {"short": stamp, "long": stamp},
        "outlook": {"available": True, "horizons": [
            {"key": "8h", "band": "short", "available": True, "lean": lean,
             "implied_range": {"sigma_pct": sigma}},
        ]},
    }


def test_intraday_short_needs_fresh_down_8h_with_enough_range():
    result = assess_style_alignment(page(), style="intraday", direction="short",
                                    minimum_move_pct=0.8, now_s=NOW.timestamp())
    assert result["eligible"] is True
    assert result["horizon"] == "8h" and result["implied_move_pct"] == 1.2
    assert all(check["passed"] for check in result["checks"])


def test_mixed_or_opposite_horizon_is_not_a_trade_candidate():
    result = assess_style_alignment(page(lean="mixed"), style="intraday", direction="long",
                                    minimum_move_pct=0.8, now_s=NOW.timestamp())
    assert result["eligible"] is False
    assert any("not up" in reason for reason in result["reasons"])


def test_target_larger_than_ordinary_move_is_refused():
    result = assess_style_alignment(page(sigma=0.5), style="intraday", direction="short",
                                    minimum_move_pct=0.8, now_s=NOW.timestamp())
    assert result["eligible"] is False
    assert any("below" in reason for reason in result["reasons"])


def test_missing_or_stale_measurement_fails_closed():
    missing = assess_style_alignment({}, style="intraday", direction="short",
                                     minimum_move_pct=0.8, now_s=NOW.timestamp())
    stale_at = datetime(2026, 9, 17, 10, 30, tzinfo=timezone.utc)
    stale = assess_style_alignment(page(measured=stale_at), style="intraday", direction="short",
                                   minimum_move_pct=0.8, now_s=NOW.timestamp())
    assert missing["eligible"] is False and stale["eligible"] is False
    assert any(check["code"] == "measurement_fresh" and not check["passed"] for check in stale["checks"])
