"""Reading a whole import file before its rows (IT-7AA1): the date order is a fact about the file, not about a row.

Pure: no database. ``profile_dates`` looks at every date cell once and returns a ``DateProfile``; ``read_date`` then
parses each cell with that decision, so ``10/02/2026`` is never a 10 February in one row and an October in the next.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from lightning.core.dates import parse_date
from lightning.core.errors import ValidationError
from lightning.core.money import ascii_digits

_MONTHS = {name: i for i, names in enumerate(
    ("jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august",
     "sep sept september", "oct october", "nov november", "dec december"), start=1) for name in names.split()}
_TIME_TAIL = re.compile(
    r"[T\s]+\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:[ap]\.?m\.?)?\s*(?:Z|[+-]\d{2}:?\d{2})?$", re.I)
_NUMERIC = re.compile(r"^(\d{1,4})([/.\-])(\d{1,2})\2(\d{1,4})$")
_NAMED = re.compile(r"^(\d{1,2})[\s\-/.]+([A-Za-z]{3,9})\.?[\s\-/.,]+(\d{2}|\d{4})$")
_NAMED_FIRST = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{2}|\d{4})$")


@dataclass(frozen=True)
class DateProfile:
    """``order`` is ``dmy``, ``mdy`` or ``ymd``. ``ambiguous``: every numeric date fits both day-first and
    month-first, so ``order`` is the day-first default and the review may ask once."""
    order: str
    ambiguous: bool
    day_first_only: int
    month_first_only: int
    both: int


def _clean(value: object) -> str:
    return _TIME_TAIL.sub("", ascii_digits(str(value or "")).strip()).strip()


def _year(text: str) -> int:
    return 2000 + int(text) if len(text) == 2 else int(text)


def profile_dates(values) -> DateProfile:
    dmy_only = mdy_only = both = ymd = 0
    for raw in values:
        match = _NUMERIC.fullmatch(_clean(raw))
        if not match:
            continue
        a, b = match.group(1), match.group(3)
        if len(a) == 4:
            ymd += 1
        elif int(a) > 12 and int(b) <= 12:
            dmy_only += 1
        elif int(b) > 12 and int(a) <= 12:
            mdy_only += 1
        elif int(a) <= 12 and int(b) <= 12:
            both += 1
    if ymd and not dmy_only and not mdy_only:
        return DateProfile("ymd", False, 0, 0, both)
    if mdy_only > dmy_only:
        return DateProfile("mdy", False, dmy_only, mdy_only, both)
    return DateProfile("dmy", bool(both) and not dmy_only and not mdy_only, dmy_only, mdy_only, both)


def read_date(value: object, profile: DateProfile | None = None) -> date:
    """One cell to a date, honouring the file's order, a trailing time and month names."""
    text = _clean(value)
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
        # CSV has no workbook epoch: numeric dates use Excel's 1900 system.
        try:
            serial = Decimal(text)
            if not serial.is_finite() or not 1 <= serial < 2958466:
                raise ValueError
            whole = int(serial)
            if whole == 60:
                raise ValueError
            return date(1899, 12, 31) + timedelta(days=whole - int(whole > 60))
        except (InvalidOperation, ValueError, OverflowError):
            raise ValidationError(f"{text} is not a real calendar date.", "date") from None
    named = _NAMED.fullmatch(text)
    if named and named.group(2).lower() in _MONTHS:
        return _make(_year(named.group(3)), _MONTHS[named.group(2).lower()], int(named.group(1)), text)
    named = _NAMED_FIRST.fullmatch(text)
    if named and named.group(1).lower() in _MONTHS:
        return _make(_year(named.group(3)), _MONTHS[named.group(1).lower()], int(named.group(2)), text)
    numeric = _NUMERIC.fullmatch(text)
    if numeric and len(numeric.group(1)) <= 2 and len(numeric.group(4)) in (2, 4):
        a, b = int(numeric.group(1)), int(numeric.group(3))
        day, month = (b, a) if profile and profile.order == "mdy" else (a, b)
        return _make(_year(numeric.group(4)), month, day, text)
    if numeric and len(numeric.group(1)) == 4:  # yyyy-mm-dd, yyyy/mm/dd, yyyy.mm.dd
        return _make(int(numeric.group(1)), int(numeric.group(3)), int(numeric.group(4)), text)
    return parse_date(text)


def _make(year: int, month: int, day: int, text: str) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise ValidationError(f"{text} is not a real calendar date.", "date") from None
