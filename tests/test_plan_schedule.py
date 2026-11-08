from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from lightning.core.memo import request_cache
from lightning.planning.schedule_view import (
    PlanSchedule,
    ScheduleSource,
    reserve_goal_needs,
)


class FakeDB:
    def __init__(self):
        self.closed = False
        self.conn = MagicMock()
        self.conn.in_transaction = False
        self.conn.total_changes = 0


class FakeReserves:
    def __init__(self, items):
        self._items = items

    def list_active(self):
        return self._items


class FakePlanning:
    def loan_payments_by_category(self, month: str):
        return {1: Decimal("250.00")}

    def budget_fill_schedule(self, month: str):
        return {2: {"due": f"{month}-10", "amount": Decimal("75.00")}}

    def income_a_month(self):
        return Decimal("4500.00")


def test_reserve_goal_needs_calculation_and_filtering():
    reserves_data = [
        # Emergency funds are excluded from goal needs
        {
            "id": "res-1",
            "name": "Emergency Fund",
            "kind": "EMERGENCY",
            "due_date": "2026-12-01",
            "target": Decimal("2000.00"),
            "allocated": Decimal("500.00"),
        },
        # Planned items linked are excluded
        {
            "id": "res-2",
            "name": "Planned Goal",
            "kind": "GOAL",
            "planned_item_id": "plan-1",
            "due_date": "2026-12-01",
            "target": Decimal("1000.00"),
            "allocated": Decimal("0.00"),
        },
        # Reserves with no due date are excluded
        {
            "id": "res-3",
            "name": "Undated Reserve",
            "kind": "GOAL",
            "due_date": None,
            "target": Decimal("1000.00"),
            "allocated": Decimal("0.00"),
        },
        # Target reached or exceeded needs nothing more
        {
            "id": "res-4",
            "name": "Completed Goal",
            "kind": "GOAL",
            "due_date": "2026-12-01",
            "target": Decimal("1000.00"),
            "allocated": Decimal("1000.00"),
        },
        # Active goal needing funding
        {
            "id": "res-5",
            "name": "Car Goal",
            "kind": "GOAL",
            "due_date": "2026-12-15",
            "target": Decimal("1200.00"),
            "allocated": Decimal("400.00"),
        },
    ]

    reserves = FakeReserves(reserves_data)
    # Test as of November 2026 (2 months left: Nov, Dec)
    needs = reserve_goal_needs(reserves, month="2026-11", as_of=date(2026, 11, 1))

    assert len(needs) == 1
    goal = needs[0]
    assert goal["id"] == "res-5"
    assert goal["name"] == "Car Goal"
    assert goal["missing"] == Decimal("800.00")
    # 800.00 / 2 months = 400.00
    assert goal["amount"] == Decimal("400.00")
    assert goal["due_date"] == "2026-12-15"


def test_plan_schedule_delegation_to_sources():
    planning = FakePlanning()
    reserves = FakeReserves(
        [
            {
                "id": "res-car",
                "name": "Car Loan Reserve",
                "kind": "GOAL",
                "due_date": "2026-12-01",
                "target": Decimal("600.00"),
                "allocated": Decimal("0.00"),
            }
        ]
    )

    schedule = PlanSchedule(planning, reserves)

    assert schedule.loans("2026-11") == {1: Decimal("250.00")}
    assert schedule.bills("2026-11") == {
        2: {"due": "2026-11-10", "amount": Decimal("75.00")}
    }
    assert schedule.income() == Decimal("4500.00")

    needs = schedule.goal_needs("2026-11")
    assert len(needs) == 1
    assert needs[0]["id"] == "res-car"
    assert needs[0]["name"] == "Car Loan Reserve"
    assert needs[0]["missing"] == Decimal("600.00")


def test_schedule_source_caching_per_request():
    db = FakeDB()
    planning = FakePlanning()
    reserves = FakeReserves([])
    source = ScheduleSource(planning, reserves)

    # Within an active request_cache scope, identical instance is returned
    with request_cache(db):
        view1 = source.view()
        view2 = source.view()
        assert isinstance(view1, PlanSchedule)
        assert view1 is view2

    # Outside the cache scope, memo decorator yields fresh instances
    view3 = source.view()
    view4 = source.view()
    assert isinstance(view3, PlanSchedule)
    assert isinstance(view4, PlanSchedule)
    assert view3 is not view4
