"""Store dates as ISO ``yyyy-mm-dd`` while accepting helpful day-first user input."""

from __future__ import annotations

import calendar
import functools
import os
import re
from datetime import date, datetime, timedelta, tzinfo

from .errors import ValidationError
from .money import ascii_digits

WEEK_STARTS = 5  # Saturday, in Python's weekday() numbering (Monday is 0).

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_DAY_FIRST_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def parse_date(value: object, field: str = "date") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = ascii_digits(str(value or "")).strip()
    match = _ISO_DATE_RE.fullmatch(text)
    if match:
        year, month, day = map(int, match.groups())
    else:
        match = _DAY_FIRST_DATE_RE.fullmatch(text)
        if not match:
            raise ValidationError(
                "Enter a date like 2026-01-31, 31/01/2026, or 31/1 (current year).", field
            )
        day, month = map(int, match.groups()[:2])
        year_text = match.group(3)
        if year_text:
            year = 2000 + int(year_text) if len(year_text) == 2 else int(year_text)
        else:
            # This year, unless that would be more than a month ahead
            # (typing 20/12 in January means last December).
            current = today()
            month_ahead = date(current.year + (current.month == 12), current.month % 12 + 1,
                               min(current.day, 28))
            try:
                candidate = date(current.year, month, day)
            except ValueError:
                candidate = None
            year = current.year - (1 if candidate and candidate > month_ahead else 0)
    try:
        return date(year, month, day)
    except ValueError:
        raise ValidationError(f"{text} is not a real calendar date.", field) from None


def fmt_date(value: date) -> str:
    return value.isoformat()


def today() -> date:
    """The current date. Tests can pin it with the LIGHTNING_TODAY environment variable (yyyy-mm-dd)."""
    return now().date()


def wall_now(tz: tzinfo | None = None) -> datetime:
    """Real device time, unaffected by the profile's simulated date.

    Use for certificate validity, backup scheduling, network freshness and publication metadata.
    With no timezone it returns naive local time, matching datetime.now().
    """
    return datetime.now(tz)


def now() -> datetime:
    """Local application time; LIGHTNING_TODAY overrides only its date, keeping the clock time."""
    current = wall_now()
    pinned = os.environ.get("LIGHTNING_TODAY")
    if pinned:
        day = date.fromisoformat(pinned)
        current = current.replace(year=day.year, month=day.month, day=day.day)
    return current


def _local_now() -> datetime:
    return wall_now().astimezone()


def now_iso() -> str:
    """Real local audit timestamp with UTC offset; independent of LIGHTNING_TODAY."""
    return _local_now().isoformat(timespec="seconds")


def parse_month(value: str, field: str = "month") -> tuple[date, date]:
    """``2026-09`` -> (2026-09-01, 2026-09-30)."""
    return _parse_month(str(value or "").strip(), field)


@functools.lru_cache(maxsize=512)  # one Overview asks for the same few dozen months about nine hundred times
def _parse_month(text: str, field: str) -> tuple[date, date]:
    if not _MONTH_RE.match(text):
        raise ValidationError("Use the month format yyyy-mm, e.g. 2026-09.", field)
    year, month = int(text[:4]), int(text[5:7])
    if not 1900 <= year <= 9998:
        raise ValidationError("Choose a month from 1900 through 9998.", field)
    if not 1 <= month <= 12:
        raise ValidationError(f"{text} is not a valid month.", field)
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def month_of(value: date) -> str:
    return value.strftime("%Y-%m")


def previous_day(value: date) -> date:
    return value - timedelta(days=1)


def months_back(end: date, count: int, first_activity: str | None) -> list[str]:
    """Up to ``count`` months ending with ``end``'s month, never before the first recorded activity."""
    keys, cursor = [], end.replace(day=1)
    floor = parse_date(first_activity).replace(day=1) if first_activity else cursor
    while len(keys) < count and cursor >= floor:
        keys.append(month_of(cursor))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(keys))
