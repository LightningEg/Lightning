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
