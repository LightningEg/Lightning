"""BU-3 (tab-by-tab review §5): a first plan offers round limits; what the user types, and seeding, stay exact."""
from decimal import Decimal

import pytest

from lightning.budgeting.service import round_limit

D = Decimal


@pytest.mark.parametrize("amount, limit", [("68", "50"), ("671", "650"), ("1480", "1500"), ("4666", "4700"),
                                           ("15", "50"), ("25", "50"), ("975", "1000"), ("1049", "1000"),
                                           ("1050", "1100"), ("12000", "12000")])
def test_a_suggested_limit_is_the_nearest_50_under_1000_and_the_nearest_100_from_it(amount, limit):
    assert round_limit(D(amount)) == D(limit)


def test_the_first_plan_offers_round_limits_and_suggested_plan_stays_exact(c, setup):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    for day, amount in (("2026-07-10", "4600"), ("2026-08-10", "4700"), ("2026-09-10", "4698")):
        c.transactions.record_outflow(day, accounts["cib"].id, amount, food.id)
    assert c.budgets.suggested_plan("2026-10")[food.id] == D("4666")  # demo and sample seeding read this
    assert c.budgets.first_plan_suggestions("2026-10")[food.id] == D("4700")
