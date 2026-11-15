"""NF-12AL1 (#641, the #626 case): regular scheduled pay that falls from a date is offered to the plan from that
date, like a raise: plan on it from its month (a dated basis; earlier months keep the average) or keep the average.
A month with no scheduled pay is a gap, never a drop."""
from decimal import Decimal

from lightning.core.dates import today
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox
from tests.screens import _ScreenClient, visible_text
from tests.test_arabic_no_english import _client, _english

MONTH = "2026-12"  # conftest pins today to 2026-12-31


def _history(c, setup, plan: str = "8000"):
    """30,000 salary recorded in September, October and November (no schedule yet); Food planned from October."""
    accounts, cats = setup
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-25", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    c.budgets.set_budget(cats["EXP.PERSONAL.FOOD"].id, "2026-10", plan, schedule=c.schedules.view())
    c.reserves.set_emergency_fund("180000")
    return cats["EXP.WORK.SALARY"].id


def _basis(c, month):
    return c.budgets.income_average(month, schedule=c.schedules.view()).amount


def test_a_salary_that_falls_from_a_date_is_offered_from_that_date(c, setup):
    salary = _history(c, setup, plan="16000")
    assert c.health.income_change_offer(MONTH) is None
    c.planning.create(kind="INCOME", name="Reduced salary", amount="18000", frequency="MONTHLY",
                      start_date="2026-12-25", category_id=salary)
    assert _basis(c, MONTH) == Decimal("30000.00") and c.health.raise_offer(MONTH) is None
    offer = c.health.income_change_offer(MONTH)
    assert (offer["kind"], offer["from"], offer["from_month"], offer["recurring"], offer["average"], offer["drop"]) == (
        "drop", "2026-12-25", MONTH, Decimal("18000.00"), Decimal("30000.00"), Decimal("12000.00"))
    # Spending room on 18,000 keeps the 20% target: 14,400; the 16,000 plan is 1,600 over it.
    assert (offer["room"], offer["over"]) == (Decimal("14400.00"), Decimal("1600.00"))
    inbox = {item["label"]: item for item in ReviewInbox(c).items(today())}
    row = inbox["Your income falls to 18,000 from 25 Dec"]
    assert row["popup"] and row["href"] == f"/budget/raise?month={MONTH}" and "Plan on it from then" in row["detail"]
    browser = _ScreenClient(create_app(c), "http://testserver")
    popup = visible_text(browser.get(f"/budget/raise?month={MONTH}").text)
    assert "Your income falls to 18,000 from 25 Dec" in popup and "Plan on it from then" in popup
    assert "your plan is 1,600 over it" in popup and "Save the difference" not in popup
    assert "Income down 12,000" in visible_text(browser.get(f"/budget?month={MONTH}").text)


def test_the_drop_reads_in_arabic_on_the_pc_and_the_phone(c, setup):
    salary = _history(c, setup, plan="16000")
    c.planning.create(kind="INCOME", name="Reduced salary", amount="18000", frequency="MONTHLY",
                      start_date="2026-12-25", category_id=salary)
    names = {"Reduced salary", "CIB Current", "CIB", "Wallet"}
    for phone in (False, True):
        client = _client(c, phone)
        for path in (f"/budget/raise?month={MONTH}", f"/budget?month={MONTH}", "/settings?section=budget", "/", "/needs-you"):
            page = client.get(path)
            assert page.status_code == 200 and not _english(page.text, names), (phone, path, _english(page.text, names))
    c.health.take_raise("plan", MONTH)
    for phone in (False, True):
        page = _client(c, phone).get("/settings?section=budget")
        assert "18,000" in visible_text(page.text) or "١٨" in page.text
        assert not _english(page.text, names), (phone, _english(page.text, names))


def test_plan_on_it_changes_the_basis_from_its_month_only(c, setup):
    salary = _history(c, setup)
    c.planning.create(kind="INCOME", name="Reduced salary", amount="18000", frequency="MONTHLY",
                      start_date="2026-12-25", category_id=salary)
    browser = _ScreenClient(create_app(c), "http://testserver")
    page = visible_text(browser.post("/budget/raise", data={"month": MONTH, "choice": "plan"}).text)
    assert "The plan now counts 18,000 a month from December 2026" in page
    assert (_basis(c, "2026-11"), _basis(c, MONTH), _basis(c, "2027-01")) == (
        Decimal("30000.00"), Decimal("18000"), Decimal("18000"))
    assert c.health.income_change_offer(MONTH) is None and c.health.income_change_offer("2027-01") is None
    assert c.health.plan_check(MONTH).income == Decimal("18000")
    settings = visible_text(browser.get("/settings?section=budget").text)
    assert "Planning on 18,000 a month from December 2026" in settings
    assert c.health.take_raise("average") == "The plan counts your average income again."
    assert _basis(c, MONTH) == Decimal("30000.00")


def test_keep_stops_the_offer_at_that_amount(c, setup):
    salary = _history(c, setup)
    item = c.planning.create(kind="INCOME", name="Reduced salary", amount="18000", frequency="MONTHLY",
                             start_date="2026-12-25", category_id=salary)
    assert c.health.take_raise("keep", MONTH) == "The plan keeps counting your average income."
    assert c.health.income_change_offer(MONTH) is None and _basis(c, MONTH) == Decimal("30000.00")
    c.planning.set_amount(item, "15000")  # a different amount is new evidence: offered again
    assert c.health.income_change_offer(MONTH)["recurring"] == Decimal("15000.00")


def test_a_one_month_gap_offers_nothing(c, setup):
    """The salary is scheduled to the end of November and again from 1 February: January has no pay."""
    salary = _history(c, setup)
    c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY", start_date="2026-09-25",
                      end_date="2026-12-25", category_id=salary)
    c.planning.create(kind="INCOME", name="New job", amount="30000", frequency="MONTHLY", start_date="2027-02-01",
                      category_id=salary)
    assert c.health.income_change_offer(MONTH) is None
    assert c.health.income_change_offer("2027-01") is None


def test_a_small_change_or_a_lump_is_not_a_drop(c, setup):
    salary = _history(c, setup)
    c.planning.create(kind="INCOME", name="Salary", amount="28000", frequency="MONTHLY", start_date="2026-12-25",
                      category_id=salary)  # 7% below: not a drop
    assert c.health.income_change_offer(MONTH) is None
    c.planning.create(kind="INCOME", name="Bonus", amount="5000", frequency="YEARLY", start_date="2026-12-20")
    assert c.health.income_change_offer(MONTH) is None
