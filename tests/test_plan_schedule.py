"""IT-1T: PlanSchedule and ScheduleSource, and the month split of reserve_goal_needs, tested directly.

PlanSchedule and ScheduleSource are thin: one forwards to Planning and the reserves, the other builds the
view once per request. The month split in reserve_goal_needs is the logic worth pinning."""
from datetime import date
from decimal import Decimal

from lightning.core.memo import request_cache
from lightning.planning.schedule_view import PlanSchedule, ScheduleSource, reserve_goal_needs

D = Decimal


class Planning:
    def loan_payments_by_category(self, month):
        return {1: D("500")}

    def budget_fill_schedule(self, month):
        return {2: {"amount": D("300")}}

    def income_a_month(self):
        return D("20000")


class Reserves:
    def __init__(self, rows):
        self.rows = rows

    def list_active(self):
        return self.rows


def goal(id, name, target, allocated, due, **extra):
    return {"id": id, "name": name, "kind": "GOAL", "target": D(target), "allocated": D(allocated),
            "due_date": due, **extra}


def test_goal_needs_split_what_is_missing_over_the_months_left():
    reserves = Reserves([
        goal(1, "Car", "12000", "0", "2027-01-15"),          # Dec to Jan inclusive from Nov: 3 months -> 4,000
        goal(2, "Trip", "1000", "400", "2026-11-30"),         # this month: 600 in one go
        goal(3, "Done", "1000", "1000", "2027-06-01"),        # fully funded: nothing more
        goal(4, "Past", "1000", "0", "2026-09-01"),           # due before the month: skipped
        goal(5, "Undated", "1000", "0", None),                # no date: not a monthly need
        goal(6, "Planned", "1000", "0", "2027-03-01", planned_item_id=9),  # already a plan item
        goal(7, "Fund", "1000", "0", "2027-03-01", kind="EMERGENCY"),      # the emergency fund has its own top-up
    ])
    needs = reserve_goal_needs(reserves, "2026-11", date(2026, 11, 10))
    assert [(row["id"], row["amount"]) for row in needs] == [(1, D("4000.00")), (2, D("600.00"))]
    assert needs[0]["missing"] == D("12000") and needs[0]["due_date"] == "2027-01-15"


def test_plan_schedule_forwards_each_question_to_its_owner():
    schedule = PlanSchedule(Planning(), Reserves([goal(2, "Trip", "1000", "400", "2099-01-01")]))
    assert schedule.loans("2026-11") == {1: D("500")}
    assert schedule.bills("2026-11") == {2: {"amount": D("300")}}
    assert schedule.income() == D("20000")
    assert [row["id"] for row in schedule.goal_needs("2026-11")] == [2]


def test_one_view_per_request_and_a_fresh_one_outside_it(c):
    source = ScheduleSource(c.planning, c.reserves)
    with request_cache(c.db):
        assert source.view() is source.view()
    assert source.view() is not source.view()
