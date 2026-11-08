from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

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
        return {
            "2026-11": {1: Decimal("250.00")},
            "2026-12": {3: Decimal("125.00")},
        }[month]

    def budget_fill_schedule(self, month: str):
        return {2: {"due": f"{month}-10", "amount": Decimal("75.00")}}

    def income_a_month(self):
        return Decimal("4500.00")


@pytest.mark.parametrize(
    ("as_of", "expected_amount"),
    [(date(2026, 11, 1), Decimal("400.00")), (date(2026, 12, 1), Decimal("800.00"))],
)
def test_reserve_goal_needs_calculation_and_filtering(as_of, expected_amount):
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
        # Goals due before the requested month are excluded.
        {
            "id": "res-6",
            "name": "Past Goal",
            "kind": "GOAL",
            "due_date": "2026-10-31",
            "target": Decimal("1000.00"),
            "allocated": Decimal("0.00"),
        },
        {
            "id": "res-7",
            "name": "Overfunded Goal",
            "kind": "GOAL",
            "due_date": "2026-12-01",
            "target": Decimal("1000.00"),
            "allocated": Decimal("1100.00"),
        },
    ]

    reserves = FakeReserves(reserves_data)
    # The contribution uses the as-of date, independently of the requested month.
    needs = reserve_goal_needs(reserves, month="2026-11", as_of=as_of)

    assert len(needs) == 1
    goal = needs[0]
    assert goal["id"] == "res-5"
    assert goal["name"] == "Car Goal"
    assert goal["missing"] == Decimal("800.00")
    assert goal["amount"] == expected_amount
    assert goal["due_date"] == "2026-12-15"


def test_plan_schedule_delegation_to_sources(monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-11-01")
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
            },
            # Keep source order, even when the next goal has an earlier due date.
            {
                "id": "res-trip",
                "name": "Trip Reserve",
                "kind": "GOAL",
                "due_date": "2026-11-30",
                "target": Decimal("120.00"),
                "allocated": Decimal("30.00"),
            },
        ]
    )

    schedule = PlanSchedule(planning, reserves)

    assert schedule.loans("2026-11") == {1: Decimal("250.00")}
    assert schedule.loans("2026-12") == {3: Decimal("125.00")}
    assert schedule.bills("2026-11") == {
        2: {"due": "2026-11-10", "amount": Decimal("75.00")}
    }
    assert schedule.bills("2026-12") == {
        2: {"due": "2026-12-10", "amount": Decimal("75.00")}
    }
    assert schedule.income() == Decimal("4500.00")

    car = {
        "id": "res-car",
        "name": "Car Loan Reserve",
        "missing": Decimal("600.00"),
        "amount": Decimal("300.00"),
        "due_date": "2026-12-01",
    }
    trip = {
        "id": "res-trip",
        "name": "Trip Reserve",
        "missing": Decimal("90.00"),
        "amount": Decimal("90.00"),
        "due_date": "2026-11-30",
    }
    assert schedule.goal_needs("2026-11") == [car, trip]
    assert schedule.goal_needs("2026-12") == [car]
    assert schedule.goal_needs("2027-01") == []


def test_reserve_goal_needs_rounding_across_year_boundary():
    reserves = FakeReserves(
        [
            {
                "id": "res-new-year",
                "name": "New Year Goal",
                "kind": "GOAL",
                "due_date": "2027-01-15",
                "target": Decimal("1000.00"),
                "allocated": Decimal("0.00"),
            }
        ]
    )

    needs = reserve_goal_needs(reserves, "2026-11", as_of=date(2026, 11, 1))
    assert needs == [
        {
            "id": "res-new-year",
            "name": "New Year Goal",
            "missing": Decimal("1000.00"),
            "amount": Decimal("333.33"),
            "due_date": "2027-01-15",
        }
    ]


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
        assert view1.loans("2026-12") == {3: Decimal("125.00")}

        other_source = ScheduleSource(FakePlanning(), FakeReserves([]))
        other_view = other_source.view()
        assert other_view is not view1
        assert other_source.view() is other_view

    # A later request gets its own view, even with the same source and database.
    with request_cache(db):
        next_view = source.view()
        assert next_view is not view1
        assert source.view() is next_view

    # Outside the cache scope, memo decorator yields fresh instances
    view3 = source.view()
    view4 = source.view()
    assert isinstance(view3, PlanSchedule)
    assert isinstance(view4, PlanSchedule)
    assert view3 is not view4
