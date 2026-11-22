"""NF-12AK4 (#647, owner 2026-11-13): a refund that names a reserve-funded purchase goes back to the reserve first.
#626's case: 1,000 paid from a reserve, 200 refunded next month. The reserve has used 800 and keeps 200; the refund's
month shows 0 plan spending, not -200; Cash and the account balance are unchanged."""
from decimal import Decimal

from lightning.core.dates import parse_month

D = Decimal


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id


def _plan(c, month, cid):
    return c.budgets.plan_funded_spending(*parse_month(month)).get(cid, D(0))


def _reserve_case(c, accounts, refund="200"):
    food = _food(c)
    reserve = c.reserves.create("New fridge", "1000")
    c.reserves.allocate(reserve["id"], "1000")
    purchase = c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "1000", food)
    c.reserves.set_expense_link(reserve["id"], purchase.id, "1000")
    money_back = c.transactions.record_refund("2026-10-05", accounts["cib"].id, refund, food)
    return food, reserve, purchase, money_back


def test_a_refund_of_a_reserve_funded_purchase_goes_back_to_the_reserve(c, setup):
    accounts, _ = setup
    food, reserve, purchase, money_back = _reserve_case(c, accounts)
    cash_before = c.reporting.cash_flow(*parse_month("2026-10"))
    balance_before = c.reporting.account_balance(accounts["cib"].id, "2026-10-31")
    assert c.reserves.get(reserve["id"])["spent"] == D("1000")  # before the link, the refund is ordinary money back
    assert _plan(c, "2026-10", food) == D("-200")

    c.refunds.link(money_back.id, purchase.id)
    after = c.reserves.get(reserve["id"])
    assert (after["spent"], after["effective_allocated"]) == (D("800"), D("200"))
    assert _plan(c, "2026-09", food) == D("0") and _plan(c, "2026-10", food) == D("0")
    assert c.budgets.estimate_spending(*parse_month("2026-10")).get(food, D(0)) == D("0")
    assert c.budgets.estimate_spending(*parse_month("2026-09")).get(food, D(0)) == D("0")
    assert [r["name"] for r in c.reserves.refunds_back(money_back.id)] == ["New fridge"]
    assert [row["amount_e6"] for row in c.reserves.links_for_reserve(reserve["id"])] == [-200_000_000, 1_000_000_000]
    # Cash and balances never move for a link.
    assert c.reporting.cash_flow(*parse_month("2026-10")) == cash_before
    assert c.reporting.account_balance(accounts["cib"].id, "2026-10-31") == balance_before

    c.refunds.unlink(money_back.id)
    assert c.reserves.get(reserve["id"])["spent"] == D("1000")
    assert _plan(c, "2026-10", food) == D("-200")


def test_only_the_reserve_funded_part_returns_to_the_reserve(c, setup):
    accounts, _ = setup
    food = _food(c)
    reserve = c.reserves.create("Holiday", "600")
    c.reserves.allocate(reserve["id"], "600")
    purchase = c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "1000", food)
    c.reserves.set_expense_link(reserve["id"], purchase.id, "600")  # 400 came from the monthly plan
    first = c.transactions.record_refund("2026-10-05", accounts["cib"].id, "500", food)
    second = c.transactions.record_refund("2026-10-20", accounts["cib"].id, "300", food)
    c.refunds.link(first.id, purchase.id)
    c.refunds.link(second.id, purchase.id)
    assert c.reserves.get(reserve["id"])["spent"] == D("0")  # 500 + 100 of the second refill the 600
    assert _plan(c, "2026-10", food) == D("-200")  # the rest lowers plan spending as before
    assert sum(r["amount"] for r in c.reserves.refunds_back(second.id)) == D("100")


def test_reserve_balances_without_refund_links_are_unchanged(c, setup):
    accounts, _ = setup
    food = _food(c)
    reserve = c.reserves.create("Car", "900")
    c.reserves.allocate(reserve["id"], "900")
    purchase = c.transactions.record_outflow("2026-09-10", accounts["cib"].id, "300", food)
    c.reserves.set_expense_link(reserve["id"], purchase.id, "300")
    c.transactions.record_refund("2026-10-05", accounts["cib"].id, "100", food)  # not linked: an ordinary refund
    row = c.reserves.get(reserve["id"])
    assert (row["spent"], row["effective_allocated"]) == (D("300"), D("600"))
