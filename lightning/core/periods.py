"""NF-7AQ2: a typed question's period, read by a small fixed grammar (no AI service, offline).

``read_period("food last month", today)`` gives ``("food", Period(2026-10-01, 2026-10-31, "month"))``: the words that
name what is asked about, and the period they ask about. English and Egyptian Arabic; the text is folded first
(`core.matching.fold_search_text`: hamza, ta marbuta, Arabic-Indic digits), so spellings vary freely. Text it does not
understand keeps all its words and has no period, and the caller falls back to today's search.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

from .matching import fold_search_text


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    kind: str  # "month" or "year"

    def before(self) -> "Period":
        """The period just before this one, the same length: what an answer compares against."""
        if self.kind == "year":
            return year(self.start.year - 1)
        return month(self.start.year - (self.start.month == 1), 12 if self.start.month == 1 else self.start.month - 1)


def month(y: int, m: int) -> Period:
    return Period(date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1]), "month")


def year(y: int) -> Period:
    return Period(date(y, 1, 1), date(y, 12, 31), "year")


_MONTHS = {}
for _n, (_en, _ar) in enumerate(zip(
        ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
         "november", "december"),
        ("يناير", "فبراير", "مارس", "ابريل", "مايو", "يونيو", "يوليو", "اغسطس", "سبتمبر", "اكتوبر", "نوفمبر",
         "ديسمبر")), start=1):
    _MONTHS[_en] = _MONTHS[_en[:3]] = _MONTHS[fold_search_text(_ar)] = _n
_MONTHS["sept"] = 9
_MONTHS.pop("may", None)
_MONTHS["may"] = 5  # "may" is also a word; it only counts as a month next to a year or alone at the end

# Phrases, longest first, each folded the way the query is.
_RELATIVE = [(fold_search_text(text), which) for text, which in sorted((
    ("this month", "this_month"), ("current month", "this_month"), ("الشهر ده", "this_month"),
    ("الشهر دا", "this_month"), ("هذا الشهر", "this_month"), ("الشهر الحالي", "this_month"),
    ("last month", "last_month"), ("previous month", "last_month"), ("الشهر اللي فات", "last_month"),
    ("الشهر الي فات", "last_month"), ("الشهر الماضي", "last_month"), ("الشهر السابق", "last_month"),
    ("this year", "this_year"), ("السنة دي", "this_year"), ("السنه دي", "this_year"), ("هذا العام", "this_year"),
    ("هذه السنة", "this_year"), ("السنة الحالية", "this_year"), ("العام ده", "this_year"),
    ("last year", "last_year"), ("previous year", "last_year"), ("السنة اللي فاتت", "last_year"),
    ("السنه اللي فاتت", "last_year"), ("السنة الماضية", "last_year"), ("العام الماضي", "last_year"),
    ("العام اللي فات", "last_year"),
), key=lambda pair: -len(pair[0]))]


def _relative(which: str, today: date) -> Period:
    if which == "this_month":
        return month(today.year, today.month)
    if which == "last_month":
        return month(today.year - (today.month == 1), 12 if today.month == 1 else today.month - 1)
    return year(today.year if which == "this_year" else today.year - 1)


def read_period(text: str, today: date) -> tuple[str, Period | None]:
    """The subject words and the period of a typed question; no period when none is said or understood."""
    words = fold_search_text(text)
    padded = f" {words} "
    for phrase, which in _RELATIVE:
        if f" {phrase} " in padded:
            rest = padded.replace(f" {phrase} ", " ", 1)
            return " ".join(rest.split()), _relative(which, today)
    tokens = words.split()
    # 2026-10, 10/2026, 2026/10
    for i, token in enumerate(tokens):
        found = re.fullmatch(r"(20\d\d)[-/](\d{1,2})|(\d{1,2})[-/](20\d\d)", token)
        if found:
            y, m = (int(found.group(1)), int(found.group(2))) if found.group(1) else (int(found.group(4)), int(found.group(3)))
            if 1 <= m <= 12:
                return " ".join(tokens[:i] + tokens[i + 1:]), month(y, m)
    # October 2026, أكتوبر 2026, Oct, October (the latest October not after today)
    for i, token in enumerate(tokens):
        m = _MONTHS.get(token)
        if not m:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if re.fullmatch(r"20\d\d", nxt):
            return " ".join(tokens[:i] + tokens[i + 2:]), month(int(nxt), m)
        if token == "may" and i != len(tokens) - 1:
            continue
        y = today.year if m <= today.month else today.year - 1
        return " ".join(tokens[:i] + tokens[i + 1:]), month(y, m)
    # 2026
    for i, token in enumerate(tokens):
        if re.fullmatch(r"20\d\d", token):
            return " ".join(tokens[:i] + tokens[i + 1:]), year(int(token))
    return words, None
