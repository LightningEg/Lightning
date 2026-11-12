"""IT-12AE4 (phone, kpis, keynotes, status): the figures these screens used to work out now live beside their inputs."""
from decimal import Decimal as D

from lightning.budgeting.domain import (left_in_plan, left_per_day, over_plan_by, over_plan_total, share_of_plan,
                                        spent_outside, used_of_plan)
from lightning.planning.domain import CashForecast, EverydayBudget, ForecastMonth, a_month, a_year, plan_parts
from lightning.planning.service import PlanningService
from lightning.reporting.fx_positions import FxPositions
from lightning.reporting.service import CashFlow, ReportingService
from lightning.reporting.spending import average, change, change_percent, rest_of, share_of, usual_for


def _everyday(**kw) -> EverydayBudget:
    base = dict(month="2026-03", planned=D(1000), spent=D(400), left=D(600), bills_to_pay=D(100), everyday_left=D(500),
                everyday_plan=D(800), everyday_spent=D(300), day=10, days_in_month=31, current=True,
                by_day=[], last_month_by_day=[D(50)] * 9 + [D(250)] + [D(700)] * 21)
    base.update(kw)
    return EverydayBudget(**base)


def test_everyday_budget_owns_its_shares_and_comparisons():
    e = _everyday()
    assert e.spent_percent == D(40)
    assert e.everyday_used_percent == D("37.5")
    assert e.spent_less_pace == e.everyday_spent - e.pace
    assert e.against_last_month_same_day == D(50)
    assert e.against_last_month == D(-400)
    assert e.everyday_parts == (D(300), D(500), D(0))
    empty = _everyday(planned=D(0), everyday_plan=D(0), last_month_by_day=[])
    assert empty.spent_percent is None and empty.everyday_used_percent is None
    assert empty.against_last_month is None and empty.against_last_month_same_day is None


def test_plan_parts_and_plan_figures():
    assert plan_parts(D(100), D(130)) == (D(100), D(0), D(30))
    assert left_in_plan(D(100), D(30)) == D(70) and used_of_plan(D(100), D(70)) == D(30)
    assert over_plan_by(D(130), D(100)) == D(30) and share_of_plan(D(25), D(100)) == D(25)
    assert left_per_day(D(90), 3) == D(30)
    assert over_plan_total([D(5), D(7)]) == D(12)
    assert spent_outside(D(100), [D(40), D(-5), D(30)]) == D(30)
    assert a_year(D(10)) == D(120) and a_month(D(120)) == D(10)


def test_cash_forecast_owns_what_the_cash_plan_cards_compare():
    months = [ForecastMonth.__new__(ForecastMonth) for _ in range(2)]
    for m, closing in zip(months, (D(400), D(250))):
        object.__setattr__(m, "closing", closing)
    f = CashForecast("2026-03-10", D(1000), None, 0, None, False, D(600),
                     [("Saving for goals", D(-100)), ("Due before payday", D(-300))], months, [])
    assert f.safe_percent_of_free_cash == D(60)
    assert f.promised == D(400)
    assert f.taken_off("Saving for goals", "Due before payday", "missing") == D(400)
    assert f.free_cash_change(D(700)) == D(300)
    assert f.free_cash_after(D(300)) == D(700) and f.free_cash_short_of(D(1200)) == D(200)
    assert f.drop_to_lowest == D(750)
    assert f.lowest_in_months(D(125)) == D(2) and f.lowest_in_months(D(0)) is None


def test_reporting_and_planning_owners():
    assert change(D(120), D(100)) == D(20) and change_percent(D(80), D(100)) == D(20)
    assert share_of(D(25), D(200)) == D("12.5") and usual_for(D(100), 3) == D(300)
    assert rest_of([{"value": D(5), "share": D(1)}, {"value": D(7), "share": D(2)}]) == (D(12), D(3))
    assert average([D(2), D(4)]) == D(3) and average([]) is None
    assert CashFlow.rate_gap(D(30), D("12.5")) == D("17.5")
    assert ReportingService.balances_total([D(10), D(-3)]) == D(7)
    assert FxPositions.held({"value": D(10), "investments": D(5)}) == D(15)
    assert PlanningService.still_to_pay_across([{"still_to_pay": D(10)}, {"still_to_pay": D(15)}]) == D(25)
