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


def _lead(html: str) -> str:
    """The page's Lead (guideline 3.33, A07): the card that answers it, first on the page."""
    return _text(html.split('class="card lead-card lead-hero"', 1)[1].split('>', 1)[1].split('<div class="lead-side">', 1)[0])


def _cards(html: str) -> list[str]:
    row = html.split('class="kpi-row', 1)[1].split("</section>", 1)[0]
    return [_text(card) for card in re.split(r'<article class="kpi-card[^"]*">', row)[1:]]


def test_budgets_everyday_money_is_cash_plannings_budget_until_payday(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, _ = mohab
    day = date(2026, 10, 19)
    e = c.forecaster.everyday("2026-10", day)
    assert e.everyday_left == c.forecaster.forecast(day).months[0].budget_spending
    assert e.left == c.budgets.plan_summary("2026-10", schedule=c.schedules.view())["left"] and e.bills_to_pay == e.left - e.everyday_left
    assert e.days_left == 13 and e.per_day == (e.everyday_left / 13).quantize(D("0.01"))
    # September's rent was paid to the Landlord before the bill was scheduled: still a bill, not everyday spending.
    assert e.last_month_by_day[-1] < c.budgets.plan_summary("2026-09", schedule=c.schedules.view())["spent"] - D("12000")


def test_the_budget_opens_with_cards_that_compare(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, client = mohab
    html = client.get("/budget").text
    cards = _cards(html)
    assert 2 <= len(cards) <= 4
    e = c.forecaster.everyday("2026-10", date(2026, 10, 19))
    left, everyday = _lead(html), cards[0]
    assert html.index("lead-hero") < html.index('class="kpi-row')  # the answer first (A09)
    assert left.strip().startswith("Left in plan 13 days left") and f"{e.everyday_left:,.0f} for everyday, about {e.per_day:,.0f} a day" in left
    assert f"Spent {e.spent:,.0f} of {e.planned:,.0f} planned" in left
    assert "Everyday spending by day 19" in everyday and "the plan's pace" in everyday
    assert "Is everyday spending on pace?" in _text(html) and "Bills still to pay this month" in _text(html)
    assert 'class="waffle' not in html and 'class="key-notes' not in html   # the waffle and the strip left Budget


def test_cash_plannings_free_cash_compares_with_the_last_month_end(mohab, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, client = mohab
    html = client.get("/plan").text
    assert _lead(html).strip().startswith("Safe to spend")  # the page's Lead (guideline 3.33, A09)
    cards = [""] + _cards(html)
    assert [card.split(" ")[1] for card in cards[1:]] == ["Free", "Due", "Lowest"]
    then = c.position.at(date(2026, 9, 30)).free_cash
    now = c.forecaster.forecast(date(2026, 10, 19)).free_cash
    assert f"+{now - then:,.0f} since 2026-09-30" in cards[1]
    assert "Due before payday 4 late" in cards[2] and "already late" in cards[2]
    assert "below today" in cards[3] and "months of spending at its lowest" in cards[3]


def test_pace_follows_the_usual_month_not_a_straight_line(mohab, monkeypatch):
    """BV-12B: a person whose month starts heavy is not told they are over pace in a normal month."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    c, _ = mohab
    e = c.forecaster.everyday("2026-10", date(2026, 10, 6))
    assert len(e.usual_shape) == 31 and e.usual_shape[-1] == 1 and e.usual_shape[0] < e.usual_shape[-1]
    print("day6", e.everyday_spent, e.pace, e.usual_by_day[5], e.everyday_plan * 6 / 31)
    assert e.pace_gap <= e.everyday_spent - e.everyday_plan * 6 / 31


def test_a_month_heavier_than_usual_is_over_pace_and_a_usual_one_never_is():
    from dataclasses import replace
    from lightning.planning.domain import EverydayBudget
    shape = [min(D(1), D(i + 1) / 5) for i in range(10)]          # a front-loaded month: all spent by day 5
    usual = [min(D(1000), D(200 * (i + 1))) for i in range(10)]
    base = EverydayBudget("2026-10", D(2000), D(0), D(2000), D(0), D(2000), D(1000), D(0), 5, 10, True,
                          [], [], shape, usual)
    assert base.pace == D("1000.00")                                # the usual month has spent it all by day 5
    assert replace(base, everyday_spent=D(1200)).pace_gap == D(200)  # heavier than usual: over
    assert replace(base, everyday_spent=D(1000)).pace_gap == D(0)    # at the usual curve: not over
    assert replace(base, everyday_spent=D(700)).pace_gap < D(0)
    assert replace(base, usual_shape=[], usual_by_day=[]).pace == D("500.00")  # no history: the straight line
    # a usual month spends more than the plan allows: still never "over pace" while at or below it
    assert replace(base, everyday_plan=D(800), everyday_spent=D(1000)).pace_gap == D(0)


def _page(client, path):
    return _text(client.get(path).text)


def test_neighbouring_figures_no_longer_disagree_or_read_wrong(mohab, monkeypatch):
    """BV-12D (r26 F5): one rendered-text check per page."""
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-19")
    c, client = mohab
    scen = _page(client, "/plan/scenarios")                                    # (b) whole EGP and a note, (c) no "None None"
    assert "None None" not in scen and "No shortfall" in scen and "usual everyday spending" in scen
    assert not re.search(r"\d,\d{3}\.\d\d EGP", scen)
    health = _page(client, "/financial-health")                                # (d) only figures with a limit count
    judged = re.search(r"of the (\d+) figures you set a limit for", health)
    assert judged and int(judged.group(1)) <= len([i for i in c.health.overview(date(2026, 10, 19))["figures"] if i.limit is not None])
    plan = client.get("/plan").text                                            # (e) no "Bills due, loans apart 0"
    assert not re.search(r"Bills due, loans apart\s*</span>\s*<b>\s*0\s*<", plan)
    accounts = _page(client, "/accounts")                                      # (f) no plus on a debt
    assert not re.search(r"Gam.eya still to pay\s*\+", accounts)  # the sample has no circle owed; the plus is gone from the template
    spending = _page(client, "/birdview/expenses?period=month&month=2026-10")  # (i) the usual month is not a repeat
    assert spending.count("Against 2026-09") <= 1
