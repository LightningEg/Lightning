"""Owner, 2026-11-18: Safe to spend today is Expected by payday less Income before payday. Expected by payday is the old
Safe to spend, unchanged, and says its payday date, how payday was chosen and each income it counts. Can I afford this?
checks the new headline. Dummy data only."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.core.figures import FIGURES, RETIRED_NAMES, label
from lightning.planning.afford import can_afford
from lightning.planning.domain import ExpectedIncome
from lightning.samples import load_mohab_2026
from lightning.ui.expected import expected_by_payday
from lightning.ui.web import create_app

D = Decimal
DAY = date(2026, 10, 2)


def _with_side_income(c, monkeypatch, amount="8,000", when="2026-10-25"):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    before = c.forecaster.forecast(DAY)
    work = str(c.categories.get_by_code("EXP.WORK.BUSINESS").id)
    c.planning.create(kind="INCOME", name="Side project", amount=amount, frequency="ONCE", start_date=when,
                      category_id=work)
    return before, c.forecaster.forecast(DAY)


def test_the_names_and_the_retired_one():
    assert label("safe_to_spend") == "Safe to spend today"
    assert label("expected_by_payday") == "Expected by payday"
    assert RETIRED_NAMES["Safe to spend"] == "expected_by_payday"
    assert FIGURES["safe_to_spend"].formula == "Expected by payday − Income before payday"


def test_safe_today_is_expected_less_income_and_expected_keeps_the_old_formula(c, monkeypatch):
    before, after = _with_side_income(c, monkeypatch)
    assert after.income_before_payday == D(8000) == after.income_before_payday - before.income_before_payday + before.income_before_payday
    assert after.safe_to_spend == after.expected_by_payday - after.income_before_payday
    # Expected by payday is the old figure: it moved by the income, exactly as Safe to spend used to.
    assert after.expected_by_payday == before.expected_by_payday + 8000
    # Safe to spend today did not move: the income has not arrived.
    assert after.safe_to_spend == before.safe_to_spend
    # The old formula's steps are all still there, the income step among them.
    parts = dict(after.expected_by_payday_parts)
    assert parts[label("income_before_payday")] == 8000
    assert sum(parts.values()) == after.expected_by_payday
    today_parts = dict(after.safe_to_spend_parts)
    assert label("income_before_payday") not in today_parts
    assert sum(today_parts.values()) == after.safe_to_spend
    assert after.safe_to_spend_working.adds_up and after.expected_by_payday_working.adds_up


def test_expected_says_its_payday_how_it_was_chosen_and_each_income(c, monkeypatch):
    _, after = _with_side_income(c, monkeypatch)
    assert after.payday_source == "salary"
    assert after.income_before_payday_items == (ExpectedIncome("Side project", "2026-10-25", D(8000)),)
    e = expected_by_payday(after)
    assert e["date"] == after.next_income_date and e["source"] == "your salary" and e["value"] == after.expected_by_payday
    assert e["incomes"] == [{"name": "Side project", "date": "2026-10-25", "amount": D(8000)}]


def test_without_a_salary_the_highest_recurring_income_is_payday(c):
    work = str(c.categories.get_by_code("EXP.WORK.BUSINESS").id)
    c.planning.create(kind="INCOME", name="Tutoring", amount="3,000", frequency="MONTHLY", interval_count="1",
                      start_date="2026-10-10", category_id=work)
    c.planning.create(kind="INCOME", name="Contract", amount="20,000", frequency="MONTHLY", interval_count="1",
                      start_date="2026-10-28", category_id=work)
    f = c.forecaster.forecast(date(2026, 10, 2))
    assert f.payday_source == "highest recurring income" and f.next_income_date == "2026-10-28"
    assert [(i.name, i.date) for i in f.income_before_payday_items] == [("Tutoring", "2026-10-10")]


def test_with_no_dated_income_payday_is_an_estimate(c):
    f = c.forecaster.forecast(date(2026, 10, 2))
    assert f.payday_source == "estimated" and f.income_before_payday_items == ()
    assert f.safe_to_spend == f.expected_by_payday


def test_a_purchase_that_fits_only_after_income_says_when():
    income = [ExpectedIncome("Side project", "2026-10-25", D(8000)), ExpectedIncome("Bonus", "2026-10-28", D(5000))]
    safe, expected = D(10000), D(23000)
    assert can_afford(D(9000), safe, D(30000), "2026-11-01", expected, income).verdict == "yes"
    one = can_afford(D(15000), safe, D(30000), "2026-11-01", expected, income)
    assert one.verdict == "after_income" and one.headline == "Fits only after EGP 8,000 arrives on 2026-10-25."
    two = can_afford(D(20000), safe, D(30000), "2026-11-01", expected, income, "USD")
    assert two.headline == "Fits only after USD 13,000 arrives on 2026-10-28."
    # past Expected by payday it is the old answer: the plan, or free cash
    assert can_afford(D(25000), safe, D(30000), "2026-11-01", expected, income).verdict == "plan"
    assert can_afford(D(40000), safe, D(30000), "2026-11-01", expected, income).verdict == "no"
    # an old-style call (no incomes) still reads Safe to spend today only
    assert can_afford(D(3000), D(5000), D(9000), None).headline == "Yes. You keep 2,000 safe to spend today."


def test_the_screens_lead_with_safe_today_and_show_expected_with_its_working(c, monkeypatch):
    _, f = _with_side_income(c, monkeypatch)
    with TestClient(create_app(c)) as browser:
        page = browser.get(f"/plan?afford={int(f.safe_to_spend) + 1000}").text
        assert "Safe to spend today" in page and "Expected by payday" in page
        assert "Side project" in page and "25 Oct" in page and "1 Nov" in page  # amounts, dates in the app's own style
        assert "Payday chosen from your salary" in page and "8,000" in page
        assert "Fits only after EGP 8,000 arrives on 25 Oct." in page
