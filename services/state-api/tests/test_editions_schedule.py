from datetime import datetime, timezone

from app import editions


def test_latest_due_today_catches_the_most_recent_slot(monkeypatch):
    monkeypatch.setattr(editions, "EDITION_TZ", timezone.utc)
    schedule = editions.parse_schedule("ny-premarket=12:00,ny-midday=17:30,session-handoff=23:30")
    due = editions.latest_due_today(datetime(2026, 9, 17, 14, 15, tzinfo=timezone.utc), schedule)
    assert due == ("ny-premarket", datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc))


def test_latest_due_today_returns_none_before_first_slot(monkeypatch):
    monkeypatch.setattr(editions, "EDITION_TZ", timezone.utc)
    schedule = editions.parse_schedule("ny-premarket=12:00,ny-midday=17:30,session-handoff=23:30")
    assert editions.latest_due_today(datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc), schedule) is None


def test_next_fire_still_selects_the_next_future_slot(monkeypatch):
    monkeypatch.setattr(editions, "EDITION_TZ", timezone.utc)
    schedule = editions.parse_schedule("ny-premarket=12:00,ny-midday=17:30,session-handoff=23:30")
    assert editions.next_fire(datetime(2026, 9, 17, 14, 15, tzinfo=timezone.utc), schedule) == (
        "ny-midday", datetime(2026, 9, 17, 17, 30, tzinfo=timezone.utc)
    )
