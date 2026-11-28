"""r41 phase 1 (payday opens the month): the day after the salary, To do leads with "Salary arrived · Plan" (guideline
C13), and the payday step's Bills protected are the bills due before the next payday, the same total Safe to spend
takes off, so the step and Home tell one story (r37 W8, r40 F13)."""
from __future__ import annotations

from datetime import date

import pytest

from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.planning.bill_state import BillRow, BillState, CatchUp
from lightning.workflows.todo import todo_rows

DAY = date(2026, 10, 2)   # October's salary arrived on the 1st


@pytest.fixture
def mohab(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", DAY.isoformat())
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    c = build(tmp_path / "t.db")
    load_mohab_2026(c)
    yield c
    c.db.close()


def test_bills_protected_are_the_bills_before_the_next_payday(mohab):
    forecast = mohab.forecaster.forecast(DAY)
    proposal = mohab.funding.preview(DAY)["proposal"]
    assert forecast.payments_before_income, "the sample has bills before November's salary"
    assert proposal["bills"] == forecast.payments_before_income_total
    # The four parts still add up to Cash available to assign (BT-12AD).
    assert (proposal["bills"] + proposal["to_plan"] + proposal["reserves"] + proposal["unassigned"]
            == proposal["available_before"])


def test_the_payday_row_leads_to_do_on_payday_and_bills_follow(mohab):
    bill = BillRow(payment=mohab.forecaster.forecast(DAY).payments_before_income[0], state=BillState.DUE_SOON,
                   late_days=0, days_until=1)
    payday_item = {"label": "Salary arrived", "href": "/payday", "action": "Plan"}
    away = CatchUp(days_since_entry=0, stale_bills=0, away=False)
    on_payday = todo_rows(mohab, DAY, [bill], [payday_item], away, paid_today=True)
    assert [r.kind for r in on_payday] == ["payday", "bill"]
    later = todo_rows(mohab, DAY, [bill], [payday_item], away, paid_today=False)
    assert [r.kind for r in later] == ["bill"], "the payday row shows only the day the salary lands and the next"


def test_home_on_payday_shows_the_payday_row_first(mohab):
    from lightning.ui.phone.screens.home import build as home
    screen = home(mohab, DAY)
    assert screen.state == "payday"
    kinds = [r.kind for r in screen.todo]
    assert kinds[0] == "payday", kinds
