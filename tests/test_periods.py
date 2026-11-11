"""NF-7AQ2: the period grammar alone, table by table (English and Egyptian Arabic, spelled several ways)."""
from __future__ import annotations

from datetime import date

import pytest

from lightning.core.periods import month, read_period, year

TODAY = date(2026, 11, 10)


@pytest.mark.parametrize("text,subject,period", [
    ("food last month", "food", month(2026, 10)),
    ("Food this month", "food", month(2026, 11)),
    ("rent this year", "rent", year(2026)),
    ("Carrefour last year", "carrefour", year(2025)),
    ("Carrefour 2026", "carrefour", year(2026)),
    ("food 2026-09", "food", month(2026, 9)),
    ("food 9/2026", "food", month(2026, 9)),
    ("eating out October", "eating out", month(2026, 10)),
    ("eating out Dec", "eating out", month(2025, 12)),     # the latest December not after today
    ("uber october 2025", "uber", month(2025, 10)),
    ("اكل الشهر اللي فات", "اكل", month(2026, 10)),
    ("أكل الشهر الماضي", "اكل", month(2026, 10)),
    ("ايجار السنة دي", "ايجار", year(2026)),
    ("ايجار السنه اللي فاتت", "ايجار", year(2025)),
    ("كارفور أكتوبر", "كارفور", month(2026, 10)),
    ("كارفور اكتوبر ٢٠٢٥", "كارفور", month(2025, 10)),
    ("مواصلات ٢٠٢٦", "مواصلات", year(2026)),
])
def test_a_period_is_read_and_its_words_leave_the_subject(text, subject, period):
    assert read_period(text, TODAY) == (subject, period)


@pytest.mark.parametrize("text", ["food", "how much on eating out", "may day", "13/2026 shop"])
def test_text_without_a_period_keeps_its_words(text):
    words, period = read_period(text, TODAY)
    assert period is None and words


def test_the_period_before_is_the_same_length():
    assert month(2026, 1).before() == month(2025, 12) and year(2026).before() == year(2025)
