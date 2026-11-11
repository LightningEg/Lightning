"""NF-3AZ10: Needs you groups by job and consequence; the Overview, Needs you and the Weekly review lead to the same task
and show the same state, and reviewed or snoozed never silently means resolved."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox, by_consequence, consequence_of
from tests.screens import said

TODAY = date(2026, 12, 20)


def _world(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", TODAY.isoformat())
    accounts, cats = setup
    bill = c.planning.create(kind="BILL", name="Rent", amount="3000", frequency="ONCE", start_date="2026-12-18",
                             account_id=accounts["cib"].id, category_id=cats["EXP.PERSONAL.FOOD"].id)
    c.bank_imports.stage(accounts["cib"].id, "statement.csv", b"Date,Counterparty,Amount\n2026-12-19,Uber,-80\n")
    return bill


def test_every_item_has_one_consequence_and_sections_keep_their_order(c, setup, monkeypatch):
    _world(c, setup, monkeypatch)
    items = ReviewInbox(c).items(TODAY)
    assert items and all(item["consequence"] == consequence_of(item) for item in items)
    sections = by_consequence(items)
    assert [s["key"] for s in sections] == sorted((s["key"] for s in sections), key=["risk", "unreconciled", "cleanup"].index)
    rent = next(item for item in items if item["label"] == "Bill due: Rent")
    assert rent["consequence"] == "risk"
    waiting = next(item for item in items if "/accounts/" in item["href"] and "import" in item["href"])
    assert waiting["consequence"] == "unreconciled"


def test_the_three_pages_lead_to_the_same_task_and_snoozing_is_not_resolving(c, setup, monkeypatch):
    _world(c, setup, monkeypatch)
    client = TestClient(create_app(c))
    rent = next(i for i in ReviewInbox(c).items(TODAY) if i["label"] == "Bill due: Rent")
    href = rent["href"].replace("&", "&amp;")
    needs = client.get("/needs-you").text
    weekly = client.get("/review").text
    overview = client.get("/").text
    assert "Money at risk" in needs and "Money at risk" in weekly
    assert href in needs and href in weekly and "Bill due: Rent" in overview
    ReviewInbox(c).decide(rent["review_id"], "snoozed", TODAY, "2026-12-27")
    assert "Bill due: Rent" not in client.get("/needs-you").text
    assert "1 reviewed or snoozed items are still open, not resolved" in client.get("/review").text
    assert "1 reviewed or snoozed items are still open, not resolved" in client.get("/").text
    handled = client.get("/needs-you?tab=handled").text
    assert "Bill due: Rent" in handled and said("Snoozed until 2026-12-27, still open") in handled
    assert c.planning.what_you_owe(TODAY).bills_due_items                      # the bill itself is still owed
