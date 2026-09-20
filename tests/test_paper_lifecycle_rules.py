"""Lifecycle rules: every style declares its stop, target, time expiry and trailing stop in one versioned place."""

from tradesync_core import paper_lifecycle_rules as rules


def test_every_style_declares_stop_target_expiry_and_trail_under_one_version():
    assert set(rules.RULES) == {'scalp', 'intraday', 'swing'}
    for style, declared in rules.RULES.items():
        described = declared.to_dict()
        assert described['version'] == rules.LIFECYCLE_VERSION and described['style'] == style
        assert declared.stop_atr > 0 and declared.reward_risk >= 1 and declared.min_target_pct > 0
        assert declared.max_hold_s > 0 and declared.atr_period >= 2 and declared.atr_seconds > 0
        assert declared.trail_activate_r > 0 and declared.trail_atr > 0
        assert declared.max_depth_bps > 0


def test_longer_styles_hold_longer_on_slower_candles():
    scalp, intraday, swing = (rules.RULES[s] for s in ('scalp', 'intraday', 'swing'))
    assert scalp.max_hold_s < intraday.max_hold_s < swing.max_hold_s
    assert scalp.atr_seconds < intraday.atr_seconds < swing.atr_seconds
    assert scalp.min_target_pct < intraday.min_target_pct < swing.min_target_pct


def test_a_shorter_style_lets_a_fill_walk_less_deep_than_a_longer_one():
    scalp, intraday, swing = (rules.RULES[s] for s in ('scalp', 'intraday', 'swing'))
    assert scalp.max_depth_bps < intraday.max_depth_bps < swing.max_depth_bps
    # The half spread every taker pays is bounded separately; this bounds how deep the size goes.
    assert swing.max_depth_bps <= rules.COMMON.max_spread_bps
    assert rules.LIFECYCLE_VERSION == 'managed-paper-lifecycle-v3'
    assert rules.catalog()['styles']['scalp']['max_depth_bps'] == scalp.max_depth_bps


def test_catalog_serves_styles_and_common_gates_with_the_version():
    catalog = rules.catalog()
    assert catalog['version'] == rules.LIFECYCLE_VERSION
    assert catalog['styles']['swing']['trail_atr'] == rules.RULES['swing'].trail_atr
    assert catalog['common']['max_notional_usdc'] == rules.COMMON.max_notional_usdc
    assert catalog['common']['planning_funding_floor_bps_hour'] > 0
