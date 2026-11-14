"""BT-7AZ (r37 W6, owner 2026-11-14): payday is the salary only. Other income before it is money in inside
Safe to spend's window; it never moves the window's end."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from lightning.core.figures import label
from lightning.planning.bill_state import next_income_date
from lightning.planning.calendar import month_calendar
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app


def test_a_side_income_before_the_salary_adds_to_safe_to_spend_and_keeps_payday(c, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    day = date(2026, 10, 2)
    before = c.forecaster.forecast(day)
    assert before.next_income_date and before.next_income_date > "2026-10-25"
    bonus = str(c.categories.get_by_code("EXP.WORK.BUSINESS").id)
    side = c.planning.create(kind="INCOME", name="Side project", amount="8,000", frequency="ONCE",
                             start_date="2026-10-25", category_id=bonus)

    after = c.forecaster.forecast(day)
    assert after.next_income_date == before.next_income_date
    assert after.safe_to_spend == before.safe_to_spend + 8000
    assert dict(after.safe_to_spend_parts)[label("income_before_payday")] == 8000
    assert next_income_date(c.planning, day) == before.next_income_date
    assert side not in c.planning.payday_item_ids()

    cal = month_calendar(c.planning, c.gameya, "2026-10", day)
    assert "2026-10-25" not in cal.paydays
    assert cal.next_payday == before.next_income_date
    with TestClient(create_app(c)) as browser:
        assert browser.get("/plan/upcoming").status_code == 200


def test_with_no_salary_the_largest_regular_income_is_payday(c):
    work = str(c.categories.get_by_code("EXP.WORK.BUSINESS").id)
    small = c.planning.create(kind="INCOME", name="Tutoring", amount="3,000", frequency="MONTHLY",
                              interval_count="1", start_date="2026-10-10", category_id=work)
    large = c.planning.create(kind="INCOME", name="Contract", amount="20,000", frequency="MONTHLY",
                              interval_count="1", start_date="2026-10-28", category_id=work)
    c.planning.create(kind="INCOME", name="One-off", amount="90,000", frequency="ONCE", start_date="2026-10-05",
                      category_id=work)
    assert c.planning.payday_item_ids() == {large}
    assert small not in c.planning.payday_item_ids()
