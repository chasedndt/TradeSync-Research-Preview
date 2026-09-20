from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from app.mobile_policy import OPT_IN_BY_KEY_PREFIX, Preferences, opt_in_field, quiet


def clock(hour, month=9):
    return datetime(2026, month, 14, hour, tzinfo=timezone.utc)


def test_defaults_are_opt_out_with_overnight_quiet():
    p = Preferences()
    assert not p.paper_events
    assert not p.control_events
    assert quiet(p, clock(21))  # 22:00 BST
    assert not quiet(p, clock(7))  # 08:00 BST
    assert not quiet(p, clock(21, 1))  # 21:00 GMT


def test_daytime_and_all_day_intervals():
    p = Preferences(timezone='UTC', quiet_start=9, quiet_end=17)
    assert quiet(p, clock(9)) and not quiet(p, clock(17))
    assert quiet(Preferences(quiet_start=8, quiet_end=8), clock(12))
    assert not quiet(Preferences(quiet_enabled=False), clock(23))


@pytest.mark.parametrize('values', [{'timezone':'not/a/timezone'}, {'timezone':'../etc/passwd'}, {'daily_budget':0}, {'daily_budget':51}, {'quiet_start':24}])
def test_invalid_preferences_are_rejected(values):
    with pytest.raises(ValidationError): Preferences(**values)


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError): quiet(Preferences(), datetime(2026,9,14))


def test_each_kind_of_automatic_message_needs_its_own_opt_in():
    assert opt_in_field('paper:0f0e2a') == 'paper_events'
    assert opt_in_field('control:paper_kill_switch:0f0e2a') == 'control_events'
    assert opt_in_field('test:29374') is None
    assert all(hasattr(Preferences(), field) for _, field in OPT_IN_BY_KEY_PREFIX)


def test_preferences_saved_before_control_events_existed_read_as_opted_out():
    assert Preferences(**{'paper_events': True, 'timezone': 'UTC'}).control_events is False
