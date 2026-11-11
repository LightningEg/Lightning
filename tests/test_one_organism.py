"""IV-3G: one category sheet for every tab (3G6), "since your last visit" on the Overview (3G5) and Ctrl-K entries (3G7)."""
from fastapi.testclient import TestClient

from lightning.core.dates import fmt_date, month_of, today
from lightning.ui.routes.search import entry, matches
from lightning.ui.web import create_app


def test_one_category_sheet_opens_from_budget_spending_and_transactions(c, setup):
    accounts, cats = setup
    food = cats["EXP.PERSONAL.FOOD"]
    month = month_of(today())
    c.transactions.record_outflow(fmt_date(today()), accounts["cib"].id, "250", food.id, counterparty="Carrefour")
    client = TestClient(create_app(c))
    sheet = client.get(f"/budget/category/{food.id}/sheet?month={month}")
    assert sheet.status_code == 200
    assert "category-sheet" in sheet.text and "Carrefour" in sheet.text and "See transactions" in sheet.text
    assert "250" in sheet.text
    spending = client.get(f"/birdview/expenses?period=month&month={month}").text
    assert f"/budget/category/{food.id}/sheet?month={month}" in spending  # Spending's tiles open the same sheet
    register = client.get(f"/transactions?category_id={food.id}&month={month}").text
    assert f"/budget/category/{food.id}/sheet?month={month}" in register  # and so does a category's register


def test_since_last_visit_counts_what_was_recorded_after_it(c, setup):
    accounts, cats = setup
    client = TestClient(create_app(c))
    first = client.get("/")
    assert "since your last visit" not in first.text and "lightning_overview_seen" in first.headers.get("set-cookie", "")
    client.cookies.clear()
    client.cookies.set("lightning_overview_seen", "2000-01-01T00:00:00+00:00")
    c.transactions.record_outflow(fmt_date(today()), accounts["cib"].id, "40", cats["EXP.PERSONAL.FOOD"].id)
    again = client.get("/").text
    assert "since your last visit on 1 Jan 2000" in again
    client.cookies.clear()
    client.cookies.set("lightning_overview_seen", "not a time")
    assert "since your last visit" not in client.get("/").text  # a cookie that is not a time is ignored


def test_ctrl_k_turns_a_typed_entry_into_a_filled_in_transaction(c, setup):
    _, cats = setup
    found = entry(c, "120 uber")
    assert found["label"] == "Add 120 out · uber" and found["popup"]
    assert "amount=120" in found["href"] and "kind=out" in found["href"] and "counterparty=uber" in found["href"]
    food = cats["EXP.PERSONAL.FOOD"]
    by_category = entry(c, f"{food.name} 45.50")
    assert f"category_id={food.id}" in by_category["href"] and "amount=45.50" in by_category["href"]
    assert "kind=in" in entry(c, "+5,000 bonus")["href"]
    for plain in ("120", "uber", "2026-10-02", "10 20 uber"):
        assert entry(c, plain) is None
    assert matches(c, "uber 120")[0]["label"].startswith("Add 120 out")
