from datetime import datetime, timedelta

import pytest

from pa import timeparse
from pa.errors import UsageError


def test_now_is_timezone_aware(fixed_tz):
    assert timeparse.now().tzinfo is not None


def test_keywords_land_on_midnight(fixed_tz):
    today = timeparse.parse("today")
    assert (today.hour, today.minute, today.second) == (0, 0, 0)
    assert timeparse.parse("tomorrow").date() == today.date() + timedelta(days=1)
    assert timeparse.parse("yesterday").date() == today.date() - timedelta(days=1)


@pytest.mark.parametrize("text,unit,amount", [
    ("+2h", "hours", 2), ("-30m", "minutes", -30),
    ("+3d", "days", 3), ("+1w", "weeks", 1), ("-45s", "seconds", -45),
])
def test_offsets(fixed_tz, text, unit, amount):
    before = timeparse.now()
    got = timeparse.parse(text)
    expected = before + timedelta(**{unit: amount})
    assert abs((got - expected).total_seconds()) < 5


def test_bare_date_is_localised_not_utc(fixed_tz):
    got = timeparse.parse("2026-09-01")
    assert got.tzinfo is not None
    # Melbourne is UTC+10, so local midnight is NOT 00:00Z. Guards the classic
    # "my meeting is 10 hours out" bug.
    assert got.utcoffset().total_seconds() != 0
    assert (got.year, got.month, got.day) == (2026, 9, 1)


def test_full_iso_offset_is_honoured(fixed_tz):
    got = timeparse.parse("2026-09-01T14:00:00+00:00")
    assert got.utcoffset().total_seconds() == 0
    assert got.hour == 14


def test_iso_z_suffix(fixed_tz):
    assert timeparse.parse("2026-09-01T14:00:00Z").utcoffset().total_seconds() == 0


def test_bare_datetime_gets_local_zone(fixed_tz):
    got = timeparse.parse("2026-09-01 14:30")
    assert got.hour == 14 and got.minute == 30
    assert got.utcoffset().total_seconds() == 10 * 3600


def test_weekday_resolves_forward(fixed_tz):
    got = timeparse.parse("friday")
    assert got.weekday() == 4
    assert got > timeparse.now() - timedelta(days=1)


def test_garbage_raises_usage_error(fixed_tz):
    with pytest.raises(UsageError):
        timeparse.parse("not a date at all !!")
    with pytest.raises(UsageError):
        timeparse.parse("")


def test_is_date_only(fixed_tz):
    assert timeparse.is_date_only("today")
    assert timeparse.is_date_only("2026-09-01")
    assert timeparse.is_date_only("monday")
    assert not timeparse.is_date_only("2026-09-01 14:00")
    assert not timeparse.is_date_only("+2h")


def test_range_expands_a_day_only_upper_bound(fixed_tz):
    lower, upper = timeparse.parse_range("today", "today")
    # "today to today" must mean the whole day, not a zero-width window.
    assert (upper - lower) == timedelta(days=1)


def test_range_does_not_expand_a_timed_bound(fixed_tz):
    lower, upper = timeparse.parse_range("2026-09-01 09:00", "2026-09-01 17:00")
    assert (upper - lower) == timedelta(hours=8)


def test_range_default_window(fixed_tz):
    lower, upper = timeparse.parse_range(None, None, default_days=3)
    assert (upper - lower) == timedelta(days=3)


def test_range_rejects_inverted_bounds(fixed_tz):
    with pytest.raises(UsageError):
        timeparse.parse_range("2026-09-10", "2026-09-01 08:00")


def test_humanise_all_day_vs_timed(fixed_tz):
    assert ":" not in timeparse.humanise("2026-09-01")
    assert ":" in timeparse.humanise("2026-09-01T14:00:00+10:00")
    assert timeparse.humanise(None) == "?"
