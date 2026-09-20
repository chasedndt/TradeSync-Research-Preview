from tradesync_core.exposure_snapshot import exposure_snapshot


def test_positions_become_absolute_notional_by_symbol():
    assert exposure_snapshot([
        {"symbol": "BTC-PERP", "size_usd": 1200},
        {"symbol": "btc-perp", "size_usd": -300},
        {"symbol": "ETH-PERP", "size_usd": "500.5"},
    ]) == {
        "by_symbol": {"BTC-PERP": 1500.0, "ETH-PERP": 500.5},
        "gross_exposure_usd": 2000.5,
    }


def test_unpublished_margin_utilization_is_not_invented():
    assert "margin_utilization" not in exposure_snapshot([])


def test_malformed_rows_do_not_become_zero_exposure_facts():
    assert exposure_snapshot([
        {"symbol": "", "size_usd": 10},
        {"symbol": "SOL-PERP", "size_usd": True},
        {"symbol": "HYPE-PERP", "size_usd": "not-a-number"},
        {"symbol": "XRP-PERP", "size_usd": float("inf")},
    ]) == {"by_symbol": {}, "gross_exposure_usd": 0}
