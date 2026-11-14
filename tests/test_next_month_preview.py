"""NF-12AL4 (#645, owner rule 4 of 2026-11-13): Budget opens next month as it will start, read only. The limits that
carry forward (a this-month-only amount does not), the bills and loan payments scheduled in it and the income the plan
will count, a dated basis from an income drop included; no Save, no Fill, and a line saying when it can be changed.
The current month is unchanged."""
import re
from decimal import Decimal

from lightning.ui.web import create_app
from tests.screens import _ScreenClient, visible_text
from tests.test_arabic_no_english import _client, _english

THIS, NEXT, LATER = "2026-12", "2027-01", "2027-02"  # conftest pins today to 2026-12-31


def _plan(c, setup):
    accounts, cats = setup
    for month in ("09", "10", "11"):
        c.transactions.record_inflow(f"2026-{month}-25", accounts["cib"].id, "30000", cats["EXP.WORK.SALARY"].id)
    schedule = c.schedules.view()
    c.budgets.set_budget(cats["EXP.PERSONAL.FOOD"].id, "2026-10", "8000", schedule=schedule)
    c.budgets.set_budget(cats["EXP.PERSONAL.FOOD"].id, THIS, "9500", only_this_month=True, schedule=schedule)
    c.planning.create(kind="BILL", name="Landlord", amount="12000", frequency="MONTHLY", start_date="2026-10-05",
                      category_id=cats["EXP.WORK.SOFTWARE"].id)
    return cats


def test_the_preview_carries_the_plan_bills_and_income_forward(c, setup):
    cats = _plan(c, setup)
    p = c.budgets.preview(NEXT, schedule=c.schedules.view())
    lines = {line["name"]: line["planned"] for group in p["groups"] for line in group["lines"]}
    assert lines["Food & groceries"] == Decimal("8000")  # December's this-month-only 9,500 does not carry
    assert [(row["name"], row["amount"], row["items"]) for row in p["bills"]] == [
        (cats["EXP.WORK.SOFTWARE"].name, Decimal("12000.00"), ["Landlord"])]
    assert p["income"] == Decimal("30000.00") and p["left"] == p["income"] - p["planned"]
    assert p["planned"] == sum((group["planned"] for group in p["groups"]), Decimal(0))


def test_a_planned_income_drop_is_the_income_next_month_counts(c, setup):
    cats = _plan(c, setup)
    c.planning.create(kind="INCOME", name="Reduced salary", amount="18000", frequency="MONTHLY",
                      start_date="2027-01-25", category_id=cats["EXP.WORK.SALARY"].id)
    c.health.take_raise("plan", THIS)
    p = c.budgets.preview(NEXT, schedule=c.schedules.view())
    assert (p["income"], p["income_since"]) == (Decimal("18000.00"), NEXT)
    assert c.budgets.income_average(THIS, schedule=c.schedules.view()).amount == Decimal("30000.00")


def test_next_month_opens_read_only_on_the_pc(c, setup):
    _plan(c, setup)
    browser = _ScreenClient(create_app(c), "http://testserver")
    page = browser.get(f"/budget?month={NEXT}")
    assert page.status_code == 200
    main = page.text.split('<main', 1)[1]
    assert not re.search(r'<form[^>]*method="post"', main) and "/budget/fill" not in main
    text = visible_text(page.text)
    assert "This is how January 2027 starts. You can change it from 1 Jan 2027." in text
    assert "Landlord" in text and "8,000" in text and "Left after limits" in text
    later = browser.get(f"/budget?month={LATER}", follow_redirects=False)
    assert later.status_code in (302, 303) and later.headers["location"].startswith(f"/budget?month={NEXT}")
    current = browser.get(f"/budget?month={THIS}").text
    assert f'href="/budget?month={NEXT}"' in current and "/budget/fill?month=" + THIS in current
    assert "Next month" in visible_text(current)


def test_next_month_opens_read_only_on_the_phone(c, setup):
    _plan(c, setup)
    phone = _client(c, True)
    page = phone.get(f"/budget?month={NEXT}")
    assert page.status_code == 200
    main = page.text.split('<main', 1)[1]
    assert not re.search(r'<form[^>]*method="post"', main)
    assert "Landlord" in visible_text(page.text)
    assert f'href="/budget?month={NEXT}' in phone.get("/budget").text  # this month's stepper leads to next month


def test_next_month_reads_in_arabic(c, setup):
    _plan(c, setup)
    names = {"Landlord", "CIB Current", "CIB", "Wallet", "Food & groceries", "Software", "Personal", "Work"}
    for phone in (False, True):
        page = _client(c, phone).get(f"/budget?month={NEXT}")
        assert page.status_code == 200 and not _english(page.text, names), (phone, _english(page.text, names))
