"""Lenient date/time parsing, because agents and humans both type shorthand.

Accepted forms::

    now                          this instant
    today / tomorrow / yesterday midnight of that day (local)
    mon..sun                     the next occurrence of that weekday
    +3d  -2h  +90m  +1w          offsets from now
    2026-09-01                   a bare date (midnight local)
    2026-09-01 14:00             bare datetime, interpreted in the local zone
    2026-09-01T14:00:00+10:00    full ISO 8601, honoured as given
    1 Sep 2026 2pm               anything dateutil can manage

Everything returns a timezone-aware ``datetime``. Naive input is localised to
the configured zone rather than silently treated as UTC, which is the classic
source of "my meeting is 10 hours out" bugs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import config
from .errors import UsageError

_OFFSET_RE = re.compile(r"^([+-])(\d+(?:\.\d+)?)\s*([smhdwSMHDW])$")
_BARE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tuesday": 1, "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def tzinfo() -> ZoneInfo:
    name = config.default_timezone()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def now() -> datetime:
    return datetime.now(tz=tzinfo())


def localise(dt: datetime) -> datetime:
    """Attach the local zone to a naive datetime; leave aware ones alone."""
    return dt if dt.tzinfo else dt.replace(tzinfo=tzinfo())


def is_date_only(text: str) -> bool:
    """True for inputs that name a day rather than an instant.

    Range bounds use this to expand ``today`` into the whole of today instead
    of the single instant of midnight.
    """
    token = text.strip().lower()
    return (
        token in {"today", "tomorrow", "yesterday"}
        or token in _WEEKDAYS
        or bool(_BARE_DATE_RE.match(token))
    )


def parse(text: str) -> datetime:
    """Parse one datetime expression into an aware datetime."""
    if isinstance(text, datetime):
        return localise(text)
    token = str(text).strip()
    if not token:
        raise UsageError("Empty date/time value")
    low = token.lower()
    tz = tzinfo()
    reference = datetime.now(tz=tz)

    if low == "now":
        return reference
    if low in {"today", "tomorrow", "yesterday"}:
        delta = {"today": 0, "tomorrow": 1, "yesterday": -1}[low]
        return (reference + timedelta(days=delta)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    if low in _WEEKDAYS:
        target = _WEEKDAYS[low]
        ahead = (target - reference.weekday()) % 7 or 7
        return (reference + timedelta(days=ahead)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    offset = _OFFSET_RE.match(low)
    if offset:
        sign, amount, unit = offset.groups()
        seconds = timedelta(**{_UNITS[unit.lower()]: float(amount)})
        return reference + (seconds if sign == "+" else -seconds)

    if _BARE_DATE_RE.match(low):
        return datetime.strptime(low, "%Y-%m-%d").replace(tzinfo=tz)

    # ISO 8601, including the trailing "Z" that fromisoformat rejects on <3.11.
    try:
        return localise(datetime.fromisoformat(token.replace("Z", "+00:00")))
    except ValueError:
        pass

    try:
        from dateutil import parser as dateutil_parser

        return localise(dateutil_parser.parse(token, default=reference))
    except (ImportError, ValueError, OverflowError) as exc:
        raise UsageError(f"Could not understand date/time: {text!r}") from exc


def parse_range(start: str | None, end: str | None, *, default_days: int = 7
                ) -> tuple[datetime, datetime]:
    """Parse an inclusive-ish range, expanding day-only bounds sensibly.

    ``--from today --to today`` becomes midnight today → midnight tomorrow, so
    "today" means the whole day. Omitted bounds default to now → now+N days.
    """
    lower = parse(start) if start else now()
    if end:
        upper = parse(end)
        if is_date_only(end):
            upper += timedelta(days=1)
    else:
        upper = lower + timedelta(days=default_days)
    if upper < lower:
        raise UsageError(f"Range end ({upper.isoformat()}) precedes start ({lower.isoformat()})")
    return lower, upper


def to_rfc3339(dt: datetime) -> str:
    return localise(dt).isoformat()


def humanise(value: str | None) -> str:
    """Render a Google API timestamp compactly in the local zone."""
    if not value:
        return "?"
    try:
        dt = localise(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return value
    local = dt.astimezone(tzinfo())
    if len(value) == 10:  # all-day event: Google sends a bare date
        return local.strftime("%a %d %b")
    return local.strftime("%a %d %b %H:%M")
