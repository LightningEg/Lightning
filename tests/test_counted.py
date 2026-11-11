"""IV-3BC: counts read right ("1 day", not "1 days") in English and Arabic."""
import re

import pytest
from fastapi.testclient import TestClient

from lightning.ui.i18n import counted, translate
from lightning.ui.web import create_app


@pytest.mark.parametrize("n, text", [(0, "0 days"), (1, "1 day"), (2, "2 days"), (11, "11 days")])
def test_counted_english(n, text):
    assert counted(n, "day", "days") == text


def test_a_group_with_one_category_says_category(c):
    real = c.categories.table
    c.categories.table = lambda *a, **k: [(l1, rows[:1]) for l1, rows in real(*a, **k)]
    html = TestClient(create_app(c)).get("/categories").text
    sizes = re.findall(r"<small>(\d+ categor(?:y|ies))</small>", html)
    assert "1 category" in sizes and "1 categories" not in html


@pytest.mark.parametrize("n, ar", [(1, "فاضل يوم واحد"), (5, "فاضل 5 يوم")])
def test_days_left_in_arabic(n, ar):
    assert translate(counted(n, "day left", "days left"), "ar") == ar


_NOUNS = [  # (English key with {n}, singular, two, 3-10, 11+) for every counted noun the UI uses
    ("{n} accounts", "حساب واحد", "حسابين", "حسابات", "حساب"),
    ("{n} categories", "فئة واحدة", "فئتين", "فئات", "فئة"),
    ("{n} rows", "صف واحد", "صفين", "صفوف", "صف"),
    ("{n} bills", "فاتورة واحدة", "فاتورتين", "فواتير", "فاتورة"),
    ("{n} rules", "قاعدة واحدة", "قاعدتين", "قواعد", "قاعدة"),
    ("{n} items", "عنصر واحد", "عنصرين", "عناصر", "عنصر"),
    ("Every {n} years", "كل سنة واحدة", "كل سنتين", "كل {n} سنين", "كل {n} سنة"),
    ("{n} transactions", "معاملة واحدة", "معاملتين", "{n} معاملات", "{n} معاملة"),
]


@pytest.mark.parametrize("key, one, two, few, many", _NOUNS)
@pytest.mark.parametrize("n", [1, 2, 3, 11])
def test_arabic_agrees_for_every_counted_noun(key, one, two, few, many, n):
    out = translate(key, "ar", n=n)
    want = {1: one, 2: two, 3: few, 11: many}[n]
    if "{n}" not in want:
        want = want if n in (1, 2) else f"{n} {want}"
    assert out.replace("كل ", "").endswith(want.replace("كل ", "").replace("{n}", str(n)))
