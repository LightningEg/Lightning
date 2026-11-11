"""Dates as people say them on screens (guideline A06.1, owner 2026-11-08, IV-3BK): Today, Yesterday, 8 Nov,
8 Nov 2025, November 2026, 1–8 Nov. Fields, files and exports keep yyyy-mm-dd; only what is read on a screen goes
through here. Arabic uses the Egyptian month names and Arabic-Indic digits: النهارده، امبارح، ٨ نوفمبر، نوفمبر ٢٠٢٦."""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from lightning.core.dates import today as _today
from lightning.ui.i18n_system import FULL_MONTHS

_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_ISO = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
_FULL = list(FULL_MONTHS)                  # January … December
_AR = [FULL_MONTHS[name] for name in _FULL]  # يناير … ديسمبر
_WORDS = {"en": ("Today", "Yesterday"), "ar": ("النهارده", "امبارح")}


def _arabic(locale: str) -> bool:
    return str(locale or "en").lower().startswith("ar")


def _digits(text: str, locale: str) -> str:
    return text.translate(_ARABIC_DIGITS) if _arabic(locale) else text


def _short(month: int, locale: str) -> str:
    return _AR[month - 1] if _arabic(locale) else calendar.month_abbr[month]


def _full(month: int, locale: str) -> str:
    return _AR[month - 1] if _arabic(locale) else _FULL[month - 1]


def _as_date(value) -> date | None:
    """A date, or a yyyy-mm-dd string; anything else is not a day."""
    if isinstance(value, date):
        return value
    found = _ISO.fullmatch(str(value or "").strip())
    if not found or not found.group(3):
        return None
    try:
        return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    except ValueError:
        return None


def _as_month(value) -> tuple[int, int] | None:
    if isinstance(value, date):
        return value.year, value.month
    found = _ISO.fullmatch(str(value or "").strip())
    if not found or not 1 <= int(found.group(2)) <= 12:
        return None
    return int(found.group(1)), int(found.group(2))


def day_text(value, locale: str = "en", today: date | None = None) -> str:
    """Today, Yesterday, 8 Nov (this year), 8 Nov 2025 (another year). Text that is not a date comes back as it is."""
    day = _as_date(value)
    if day is None:
        return "" if value is None else str(value)
    now = today or _today()
    words = _WORDS["ar" if _arabic(locale) else "en"]
    if day == now:
        return words[0]
    if day == now - timedelta(days=1):
        return words[1]
    text = f"{day.day} {_short(day.month, locale)}" + ("" if day.year == now.year else f" {day.year}")
    return _digits(text, locale)


def month_text(value, locale: str = "en") -> str:
    """November 2026 for 2026-11 (or any day in it)."""
    month = _as_month(value)
    if month is None:
        return "" if value is None else str(value)
    return _digits(f"{_full(month[1], locale)} {month[0]}", locale)


def _whole_months(start: date, end: date) -> bool:
    return start.day == 1 and end.day == calendar.monthrange(end.year, end.month)[1]


def range_text(start, end, locale: str = "en", today: date | None = None) -> str:
    """1–8 Nov, 28 Oct – 8 Nov, 28 Dec 2025 – 3 Jan 2026; whole months read as months: November 2026,
    Sep – Nov 2026, Dec 2025 – Jan 2026. yyyy-mm ends count as whole months."""
    if _as_date(start) is None and (m := _as_month(start)):
        start = date(m[0], m[1], 1)
    if _as_date(end) is None and (m := _as_month(end)):
        end = date(m[0], m[1], calendar.monthrange(m[0], m[1])[1])
    first, last = _as_date(start), _as_date(end)
    if first is None or last is None:
        return f"{start} – {end}"
    now = today or _today()
    if first == last:
        return day_text(first, locale, now)
    if _whole_months(first, last):
        if (first.year, first.month) == (last.year, last.month):
            return month_text(first, locale)
        if first.year == last.year:
            text = f"{_short(first.month, locale)} – {_short(last.month, locale)} {last.year}"
        else:
            text = f"{_short(first.month, locale)} {first.year} – {_short(last.month, locale)} {last.year}"
        return _digits(text, locale)
    year = "" if last.year == now.year else f" {last.year}"
    if (first.year, first.month) == (last.year, last.month):
        text = f"{first.day}–{last.day} {_short(last.month, locale)}{year}"
    elif first.year == last.year:
        text = f"{first.day} {_short(first.month, locale)} – {last.day} {_short(last.month, locale)}{year}"
    else:
        text = f"{first.day} {_short(first.month, locale)} {first.year} – {last.day} {_short(last.month, locale)} {last.year}"
    return _digits(text, locale)


# -- the page's date pass ---------------------------------------------------------------------------------------------
# Every screen goes through `human_dates` once it is rendered (web.render), so a date written by a template or by a
# Python sentence ("until 2026-12-01", "Due 2026-10-03") reads the same way. Only visible text and the tooltip
# attributes change: field values, links, scripts, styles, typed notes and chart drawings (SVG axes stay short, A12)
# keep yyyy-mm-dd. A reference that holds a date (OUT-2026-08-12-001, lightning-2026-11-08.csv) is not a date.
_PIECE = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>|<textarea\b.*?</textarea>|<svg\b.*?</svg>|"
                    r"<!--.*?-->|<[^>]+>|[^<]+)", re.S | re.I)
_TIP = re.compile(r"""(\s(?:title|aria-label|data-tip)=)(["'])(.*?)\2""", re.S | re.I)
_STAMP = r"(?<![\w./-])(\d{4}-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)(?![\w/]|-\d|\.\d)"
_RANGE = re.compile(_STAMP + r"( to | لحد | – |–| - )" + _STAMP)
_ONE = re.compile(_STAMP)
_ON_DAY = re.compile(r"\bon (today|yesterday)\b")
_SENTENCE_START = re.compile(r"(?:^|[.:·؟?!\n]\s*|[(«“\"]\s*)$")


def _one(match: re.Match, text: str, locale: str, now: date) -> str:
    stamp = match.group(1)
    if len(stamp) == 7:
        return month_text(stamp, locale)
    said = day_text(stamp, locale, now)
    if said in _WORDS["en"] and not _SENTENCE_START.search(text[:match.start()]):
        said = said.lower()  # "until today", not "until Today"
    return said


def human_text(text: str, locale: str = "en", today: date | None = None) -> str:
    """One run of visible text with its dates (and ranges of dates) as people say them."""
    if not text or not any(ch.isdigit() for ch in text):
        return text
    now = today or _today()
    text = _RANGE.sub(lambda m: range_text(m.group(1), m.group(3), locale, now), text)
    text = _ONE.sub(lambda m: _one(m, text, locale, now), text)
    return _ON_DAY.sub(r"\1", text)  # "reached your account on today" -> "... today"


def human_dates(page: str, locale: str = "en", today: date | None = None) -> str:
    now = today or _today()
    out = []
    typed = False  # inside <bdi translate="no">: what the person typed stays as typed
    for piece in _PIECE.findall(page):
        if piece.startswith("<"):
            lower = piece[:5].lower()
            if lower.startswith("<bdi") and 'translate="no"' in piece:
                typed = True
            elif lower == "</bdi":
                typed = False
            if not piece.startswith(("<!", "</")) and lower not in ("<scri", "<styl", "<text", "<svg ", "<svg>"):
                piece = _TIP.sub(lambda m: m.group(1) + m.group(2) + human_text(m.group(3), locale, now) + m.group(2), piece)
            out.append(piece)
        else:
            out.append(piece if typed else human_text(piece, locale, now))
    return "".join(out)
