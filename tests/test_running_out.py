"""NF-12S: a flexible category whose pace passes its limit before the month ends is one row in Needs you, with Move
room and Raise; it is gone when back on pace or snoozed, and bill-only categories are never paced."""
from datetime import date
from decimal import Decimal

from lightning.workflows.review import ReviewInbox

MONTH = "2026-12"
DAY = date(2026, 12, 10)  # ten days gone of 31


def _ids(c):
    return (c.categories.get_by_code("EXP.PERSONAL.FOOD").id, c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id)


def _plan(c, setup, food_spent="1500"):
    accounts, _ = setup
    food, transport = _ids(c)
    s = c.schedules.view()
    c.budgets.set_budget(food, MONTH, "3000", schedule=s)
    c.budgets.set_budget(transport, MONTH, "2000", schedule=s)
    c.transactions.record_outflow("2026-12-04", accounts["cib"].id, food_spent, food)
    c.transactions.record_outflow("2026-12-04", accounts["cib"].id, "100", transport)
    return food, transport


def test_ahead_of_pace_names_the_day_and_a_category_to_move_from(c, setup):
    food, transport = _plan(c, setup)
    [row] = c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view())
    assert (row["category_id"], row["day"], row["limit"]) == (food, 20, Decimal("3000"))
    assert row["amount"] == Decimal("1650") and row["can_move"] and row["from_id"] == transport
    item = {i["label"]: i for i in ReviewInbox(c).items(DAY)}["Food & groceries will run out around the 20th"]
    assert item["action"] == "Move room" and item["href"].startswith(f"/budget/move?month={MONTH}&to={food}&from={transport}")
    assert item["alt"]["label"] == "Raise"


def test_on_pace_early_in_the_month_and_over_already_say_nothing(c, setup):
    _plan(c, setup, food_spent="900")  # 900 / 10 x 31 = 2,790, inside 3,000
    assert c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view()) == []
    _plan(c, setup, food_spent="1500")
    assert c.budgets.running_out(MONTH, date(2026, 12, 5), schedule=c.schedules.view()) == []  # after day 5 only
    assert c.budgets.running_out(MONTH, date(2027, 1, 10), schedule=c.schedules.view()) == []  # not this month


def test_a_category_with_bills_is_not_paced(c, setup):
    food, _ = _plan(c, setup)
    c.planning.create(kind="BILL", name="Groceries club", amount="200", frequency="MONTHLY",
                      start_date="2026-12-20", category_id=food)
    assert c.budgets.running_out(MONTH, DAY, schedule=c.schedules.view()) == []


def test_snoozed_row_leaves_needs_you_and_without_a_donor_it_offers_only_raise(c, setup):
    food, transport = _plan(c, setup)
    c.budgets.set_budget(transport, MONTH, "1000", schedule=c.schedules.view())
    inbox = ReviewInbox(c)
    [item] = [i for i in inbox.items(DAY) if "will run out" in i["label"]]
    assert item["action"] == "Raise" and "alt" not in item and f"limit-{food}" in item["href"]
    inbox.decide(item["review_id"], "snoozed", DAY, "2026-12-20")
    assert not [i for i in inbox.items(DAY) if "will run out" in i["label"]]
