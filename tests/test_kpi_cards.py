"""KPI cards (guideline 3.32, A08): every card compares its figure with something, two to four fill a row, and
Budget and Cash planning read the same everyday money (owner 2026-10-19: Budget's day rate counts everyday money only)."""
from __future__ import annotations

import re
from datetime import date
from html import unescape
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.samples import load_mohab_2026
from lightning.ui import charts, kpis
from lightning.ui.web import create_app


def test_a_card_without_a_comparison_is_refused():
    with pytest.raises(ValueError, match="no comparison"):
        kpis.card("Free cash", D("100"), {"figure": "", "text": "", "tone": "plain"}, tone="hold")
    with pytest.raises(ValueError, match="tone"):
        kpis.card("Free cash", D("100"), kpis.compare("since 2026-09-30", "+5"), tone="green")


def test_a_lone_card_is_not_a_row():
    one = kpis.card("Free cash", D("100"), kpis.compare("since 2026-09-30", "+5"), tone="hold")
    assert kpis.row([one, None]) == []
    assert len(kpis.row([one] * 5)) == 4


def test_the_sparkline_dot_sits_on_the_point_the_label_names():
    low = charts.sparkline([D(5), D(1), D(9)], "low")
    last = charts.sparkline([D(5), D(1), D(9)])
    assert low["dot"][1] == 90.0 and last["dot"] == last["last"]   # the lowest is drawn at the bottom


def test_pace_marks_today_against_the_plans_straight_line():
    p = charts.pace([D(0), D(300), D(300)], D(3000), 30, [D(100)] * 30)
    assert p["today"]["day"] == 3 and p["today"]["pace"] == D(300)
    assert p["today"]["before"] == D(100) and p["plan"]["value"] == D(3000)


@pytest.fixture(scope="module")
def mohab(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-19")
        from lightning.bootstrap import build
        c = build(tmp_path_factory.mktemp("kpi") / "t.db")
        load_mohab_2026(c)
        yield c, TestClient(create_app(c))
        c.db.close()


def _text(html: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


def _cards(html: str) -> list[str]:
    row = html.split('class="kpi-row', 1)[1].split("</section>", 1)[0]
    return [_text(card) for card in re.split(r'<article class="kpi-card[^"]*">', row)[1:]]


def test_budgets_everyday_money_is_cash_plannings_budget_until_payday(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, _ = mohab
    day = date(2026, 10, 19)
    e = c.forecaster.everyday("2026-10", day)
    assert e.everyday_left == c.forecaster.forecast(day).months[0].budget_spending
    assert e.left == c.budgets.plan_summary("2026-10")["left"] and e.bills_to_pay == e.left - e.everyday_left
    assert e.days_left == 13 and e.per_day == (e.everyday_left / 13).quantize(D("0.01"))
    # September's rent was paid to the Landlord before the bill was scheduled: still a bill, not everyday spending.
    assert e.last_month_by_day[-1] < c.budgets.plan_summary("2026-09")["spent"] - D("12000")


def test_the_budget_opens_with_cards_that_compare(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, client = mohab
    html = client.get("/budget").text
    cards = _cards(html)
    assert 2 <= len(cards) <= 4
    e = c.forecaster.everyday("2026-10", date(2026, 10, 19))
    left, everyday = cards[0], cards[1]
    assert left.startswith(" Left in plan 13 days left") and f"{e.everyday_left:,.0f} for everyday, about {e.per_day:,.0f} a day" in left
    assert f"Spent {e.spent:,.0f} of {e.planned:,.0f} planned" in left
    assert "Everyday spending by day 19" in everyday and "the plan's pace" in everyday
    assert "Is everyday spending on pace?" in _text(html) and "Bills in this month's plan" in _text(html)
    assert 'class="waffle' not in html and 'class="key-notes' not in html   # the waffle and the strip left Budget


def test_cash_plannings_free_cash_compares_with_the_last_month_end(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, client = mohab
    cards = _cards(client.get("/plan").text)
    assert [card.split(" ")[1] for card in cards] == ["Safe", "Free", "Due", "Lowest"]
    then = c.position.at(date(2026, 9, 30)).free_cash
    now = c.forecaster.forecast(date(2026, 10, 19)).free_cash
    assert f"+{now - then:,.0f} since 2026-09-30" in cards[1]
    assert "Due before payday 4 late" in cards[2] and "already late" in cards[2]
    assert "below today" in cards[3] and "months of spending at its lowest" in cards[3]
