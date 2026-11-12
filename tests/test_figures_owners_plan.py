"""IT-12AE4 (plan area): the Budget, Plan, Reserves, Overview and analysis figures are worked out by their owners."""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

from lightning.budgeting.period import (category_pace, month_factor, over_matters, plan_used, spent_percent)
from lightning.planning.domain import PlanKind
from lightning.planning.totals import (LoanTotals, RecurringEntry, RecurringTotals, a_month, bills_by_category,
                                       budget_effect, reserve_effect, share_of_free_cash, total)
from lightning.reporting.period_compare import (CompareTotals, average, change, compare_rows, item_trend, ratio,
                                                share, usual_over)
from lightning.reserves import EmergencyRefill, effective_after, would_exceed_cash


def test_budget_period_helpers():
    assert month_factor("month", "2026-02", date(2026, 2, 10), date(2026, 2, 20)) == 1
    assert month_factor("custom", "2026-02", date(2026, 2, 1), date(2026, 2, 14)) == D(14) / D(28)
    assert month_factor("custom", "2026-03", date(2026, 2, 1), date(2026, 2, 14)) == 0
    assert over_matters(D(100), D(2000)) and not over_matters(D(99), D(100)) and not over_matters(D(100), D(2001))
    assert plan_used(D(1000), D(250)) == (D(750), D(75))
    assert plan_used(D(0), D(0))[1] is None
    assert spent_percent(D("1005"), D(2000)) == 50 and spent_percent(D(-5), D(100)) == 0
    pace = category_pace(D("1000.4"), D("600.6"), date(2026, 4, 1), date(2026, 4, 30), date(2026, 4, 15))
    assert pace["left"] == D(399) and pace["pace"] == D(50) and pace["risk"]
    assert category_pace(D(100), D(10), date(2026, 4, 1), date(2026, 4, 30), date(2026, 5, 2))["pace"] is None


def test_plan_totals():
    bill = SimpleNamespace(kind=PlanKind.BILL, is_income=False)
    sub = SimpleNamespace(kind=PlanKind.SUBSCRIPTION, is_income=False)
    pay = SimpleNamespace(kind=PlanKind.BILL, is_income=True)  # income: only is_income counts
    due = SimpleNamespace(amount=D(50))
    totals = RecurringTotals([RecurringEntry(bill, D(1200), [due, due]), RecurringEntry(sub, D(120)),
                              RecurringEntry(pay, D(24000), [due])])
    planning = SimpleNamespace(amount_in_base=lambda item, amount, day: amount * 2)
    assert totals.subscriptions_per_year == D(120) and totals.income_a_month == D(2000)
    assert totals.due_count == 2 and totals.due_total(planning, date(2026, 1, 1)) == D(200)
    assert a_month(D(1200)) == D(100)
    loans = LoanTotals.of([{"paid_amount": D(30), "total_amount": D(100)}, {"paid_amount": D(5), "total_amount": D(10)}])
    assert (loans.paid, loans.borrowed, loans.left) == (D(35), D(110), D(75))
    assert total([D(1), D(2)]) == D(3)
    assert reserve_effect({"name": "Rent", "effective_allocated": D(300)}, D(500))["after"] == 0
    effect = budget_effect(SimpleNamespace(name="Food", remaining=D(100)), "2026-01", D(150))
    assert effect["left_after"] == D(-50) and effect["over"]
    assert share_of_free_cash(D(250), D(1000)) == D(25)
    item = SimpleNamespace(category_id=7)
    payments = [SimpleNamespace(due_date="2026-01-05", item=item, amount=D(100), still_owed=D(40)),
                SimpleNamespace(due_date="2026-02-05", item=item, amount=D(100), still_owed=D(0))]
    assert bills_by_category(planning, payments, "2026-01", date(2026, 1, 9)) == {7: (D(200), D(120))}


def test_reserves_owner():
    assert would_exceed_cash(D(500), D(100), D(700), D(1000)) is True
    assert would_exceed_cash(D(500), D(100), D(600), D(1000)) is False
    assert effective_after(D(100), D(150)) == 0
    refill = EmergencyRefill(D(400), D(1000))
    assert refill.gap == D(600) and refill.room(D(250)) == D(250) and refill.to(D(600)) == D(1000)
    assert refill.fills(D(600)) and not refill.fills(D(599))


def test_period_compare_owner():
    rows = compare_rows([("a", "F", "Food", 1, D(300)), ("b", "F", "Food", 1, D(200)), ("b", "R", "Rent", 2, D(50)),
                         ("a", "Z", "Zero", 3, D(0))])
    assert [(r["key"], r["diff"], r["pct"]) for r in rows] == [("F", D(100), D(50)), ("R", D(-50), D(-100))]
    totals = CompareTotals.of(rows)
    assert (totals.total_a, totals.total_b, totals.diff) == (D(300), D(250), D(50))
    lines = [{"date": "2026-01-03", "value": D(10), "transaction_id": 1, "ref": "a"},
             {"date": "2026-02-03", "value": D(30), "transaction_id": 2, "ref": "b"}]
    data = item_trend(["2026-01", "2026-02"], lines, lambda r: "Shop", "2026-02", "2026-01", 10)
    assert data["total"] == D(40) and data["average"] == D("20.00") and data["trend"][0]["pct"] == 33
    assert data["count"] == 2 and data["top"][0]["value"] == D(30)
    assert change(D(150), D(100)) == (D(50), D(50)) and change(D(1), D(0))[1] is None
    assert average([D(10), D(20)], 2) == D(15) and average([], 0) is None
    assert usual_over(D(100), 3) == D(300) and usual_over(None, 3) is None
    assert ratio(D(30), D(10)) == D(3) and share(D(1), D(4)) == D(25)
