"""NF-12AL3 (#646) and NF-12AK5's review row (#648), owner 2026-11-13: one card of what changed leads Budget. An
unchanged month says "Your plan continues"; each change appears once with its evidence and stays dismissed until the
evidence changes; Needs you shows only the count; a purchase over half its category's window is offered to leave out."""
from datetime import date

import pytest

from lightning.undo import user_action
from lightning.workflows.review import ReviewInbox
from tests.test_budget_exclusions_ui import client_for

TODAY = date(2026, 12, 31)  # tests/conftest.py pins LIGHTNING_TODAY


def _food(c):
    return c.categories.get_by_code("EXP.PERSONAL.FOOD").id


def _planned(c, accounts, amount="3000"):
    food = _food(c)
    for day in ("2026-09-04", "2026-10-04", "2026-11-04"):
        c.transactions.record_outflow(day, accounts["cib"].id, "1000", food)
    c.budgets.set_budget(food, "2026-12", amount, schedule=c.schedules.view())
    return food


def _laptop(c, accounts, food):
    return c.transactions.record_outflow("2026-11-03", accounts["cib"].id, "9000", food, counterparty="Laptop shop")


def _unusual(c):
    return [item for item in ReviewInbox(c).changes(TODAY) if item.get("post")]


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("locale", ["en", "ar"])
def test_an_unchanged_month_says_the_plan_continues(c, setup, phone, locale):
    accounts, _ = setup
    _planned(c, accounts, "1000")
    page = client_for(c, phone, locale).get("/budget?month=2026-12").text
    assert 'id="changes"' in page
    assert ("Your plan continues" in page) == (locale == "en")
    assert "budget-change\"" not in page


def test_a_large_purchase_is_offered_once_and_its_choice_is_undoable(c, setup):
    accounts, _ = setup
    food = _planned(c, accounts)
    laptop = _laptop(c, accounts, food)
    rows = _unusual(c)
    assert len(rows) == 1 and "9,000 purchase" in rows[0]["label"]
    assert rows[0]["post"]["fields"]["transaction_id"] == laptop.id

    client = client_for(c, False, "en")
    page = client.get("/budget?month=2026-12").text
    assert page.count("9,000 purchase") == 1
    client.post("/budget/leave-out", data={"transaction_id": laptop.id, "month": "2026-12"})
    assert c.budgets.is_left_out(laptop.id) and _unusual(c) == []
    c.budgets.set_left_out(laptop.id, False)  # counted again: the offer comes back
    assert len(_unusual(c)) == 1
    with user_action("Leave out"):
        c.budgets.set_left_out(laptop.id, True)
    c.undo.replay()  # the choice is undoable
    assert not c.budgets.is_left_out(laptop.id) and len(_unusual(c)) == 1


def test_keep_holds_until_the_evidence_changes(c, setup):
    accounts, _ = setup
    food = _planned(c, accounts)
    _laptop(c, accounts, food)
    row = _unusual(c)[0]
    client = client_for(c, False, "en")
    answer = client.post("/needs-you/state", data={"identity": row["review_id"], "action": "reviewed",
                                                   "back": "/budget?month=2026-12#changes"}, follow_redirects=False)
    assert answer.headers["location"].startswith("/budget?month=2026-12")
    assert _unusual(c) == []
    c.transactions.record_outflow("2026-11-20", accounts["cib"].id, "500", food)  # the window total changes
    assert len(_unusual(c)) == 1


def test_needs_you_shows_one_row_with_the_count(c, setup):
    accounts, _ = setup
    food = _planned(c, accounts)
    _laptop(c, accounts, food)
    inbox = ReviewInbox(c)
    changes = inbox.changes(TODAY)
    items = inbox.items(TODAY)
    summary = [item for item in items if item["href"].endswith("#changes")]
    assert len(summary) == 1 and summary[0]["label"].startswith(f"{len(changes)} change")
    assert not any(item.get("change") for item in items)  # the rows themselves live on Budget only
