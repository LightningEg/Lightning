"""Dates as people say them on screens (guideline A06.1, IV-3BK2): each output in English and Arabic, year
boundaries, and today taken from LIGHTNING_TODAY."""
from datetime import date

from lightning.ui.date_text import day_text, month_text, range_text
from lightning.ui.web import templates

NOW = date(2026, 11, 8)


def test_a_day_is_today_yesterday_or_its_date():
    assert [day_text(d, "en", NOW) for d in ("2026-11-08", "2026-11-07", "2026-11-05", "2025-11-08")] == [
        "Today", "Yesterday", "5 Nov", "8 Nov 2025"]
    assert [day_text(d, "ar", NOW) for d in ("2026-11-08", "2026-11-07", "2026-11-05", "2025-11-08")] == [
        "النهارده", "امبارح", "٥ نوفمبر", "٨ نوفمبر ٢٠٢٥"]
    assert day_text(date(2026, 12, 1), "en", NOW) == "1 Dec"
    assert day_text("not a date", "en", NOW) == "not a date" and day_text(None) == ""


def test_yesterday_crosses_a_year():
    new_year = date(2027, 1, 1)
    assert day_text("2026-12-31", "en", new_year) == "Yesterday"
    assert day_text("2026-12-30", "en", new_year) == "30 Dec 2026"
    assert day_text("2027-01-01", "ar", new_year) == "النهارده"


def test_a_month_is_named_in_full():
    assert month_text("2026-11", "en") == "November 2026" and month_text(date(2026, 1, 9), "en") == "January 2026"
    assert month_text("2026-11", "ar") == "نوفمبر ٢٠٢٦"
    assert month_text("2026-13", "en") == "2026-13"


def test_a_range_says_each_part_once():
    assert range_text("2026-11-01", "2026-11-08", "en", NOW) == "1–8 Nov"
    assert range_text("2026-10-28", "2026-11-08", "en", NOW) == "28 Oct – 8 Nov"
    assert range_text("2025-12-28", "2026-01-03", "en", NOW) == "28 Dec 2025 – 3 Jan 2026"
    assert range_text("2025-11-01", "2025-11-08", "en", NOW) == "1–8 Nov 2025"
    assert range_text("2025-12-01", "2026-01-31", "en", NOW) == "Dec 2025 – Jan 2026"
    assert range_text("2026-09", "2026-11", "en", NOW) == "Sep – Nov 2026"
    assert range_text("2026-11-01", "2026-11-30", "en", NOW) == "November 2026"
    assert range_text("2026-11-08", "2026-11-08", "en", NOW) == "Today"
    assert range_text("2026-11-01", "2026-11-08", "ar", NOW) == "١–٨ نوفمبر"
    assert range_text("2026-10-28", "2026-11-08", "ar", NOW) == "٢٨ أكتوبر – ٨ نوفمبر"
    assert range_text("2025-12-01", "2026-01-31", "ar", NOW) == "ديسمبر ٢٠٢٥ – يناير ٢٠٢٦"


def test_today_comes_from_lightning_today_and_the_filters_are_registered(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-08")
    assert day_text("2026-11-07") == "Yesterday" and range_text("2026-11-01", "2026-11-08") == "1–8 Nov"
    render = templates.env.from_string("{{ d|day('en') }} · {{ m|month('ar') }} · {{ a|day_range(b, 'en') }}").render
    assert render(d="2026-11-08", m="2026-11", a="2026-11-01", b="2026-11-08") == "Today · نوفمبر ٢٠٢٦ · 1–8 Nov"
