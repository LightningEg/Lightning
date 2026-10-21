"""One review inbox: every decision Lightning waits on, listed once in Needs you."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lightning.core.dates import today
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox


def _labels(items):
    return [item["label"] for item in items]


def test_each_statement_left_in_review_is_listed_with_its_waiting_rows(c, setup):
    accounts, _ = setup
    cib, wallet = accounts["cib"].id, accounts["wallet"].id
    first, _ = c.bank_imports.stage(cib, "cib-oct.csv",
                                    b"Date,Counterparty,Amount\n2026-10-03,Shop,-5\n2026-10-04,Cafe,-7\n")
    second, _ = c.bank_imports.stage(wallet, "wallet.csv", b"Date,Counterparty,Amount\n2026-10-06,Kiosk,-2\n")

    statements = [item for item in ReviewInbox(c).items(today())
                  if item["label"] == "Imported activity needs a decision"]
    assert len(statements) == 2  # not only the first waiting row of the first statement
    cib_item, wallet_item = statements
    assert cib_item["detail"] == "cib-oct.csv · 2 rows wait · from row 2 · 2026-10-03."
    assert cib_item["href"].startswith(f"/accounts/{cib}/import/{first}#import-row-")
    assert wallet_item["detail"] == "wallet.csv · 1 row waits · from row 2 · 2026-10-06."
    assert wallet_item["href"].startswith(f"/accounts/{wallet}/import/{second}#import-row-")
    assert cib_item["action"] == "Finish the import"


def test_activity_without_a_category_is_counted_and_linked(c, setup):
    accounts, _ = setup
    cib = accounts["cib"].id
    spent = c.categories.get_by_code("EXP.UNACCOUNTED")
    found = c.categories.get_by_code("INC.UNACCOUNTED")
    for amount in ("40", "60"):
        c.transactions.record_outflow("2026-10-02", cib, amount, spent.id, allow_system_category=True)
    c.transactions.record_inflow("2026-10-03", cib, "25", found.id, allow_system_category=True)

    items = {item["label"]: item for item in ReviewInbox(c).items(today())}
    assert items["2 payments have no category"]["href"] == f"/transactions?category_id={spent.id}"
    assert items["1 incoming amount has no category"]["href"] == f"/transactions?category_id={found.id}"
    assert items["2 payments have no category"]["action"] == "Sort them out"


def test_a_voided_uncategorized_payment_needs_nothing(c, setup):
    accounts, _ = setup
    spent = c.categories.get_by_code("EXP.UNACCOUNTED")
    txn = c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "40", spent.id, allow_system_category=True)
    c.transactions.void(txn.id, "duplicate")
    assert not any("no category" in label for label in _labels(ReviewInbox(c).items(today())))


def test_the_overview_lists_the_whole_inbox_in_needs_you(c, setup):
    accounts, _ = setup
    client = TestClient(create_app(c))
    assert '<section class="needs"' not in client.get("/").text  # nothing to show: no row at all (A09)

    spent = c.categories.get_by_code("EXP.UNACCOUNTED")
    c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "40", spent.id, allow_system_category=True)
    c.bank_imports.stage(accounts["cib"].id, "cib-oct.csv", b"Date,Counterparty,Amount\n2026-10-03,Shop,-5\n")
    page = client.get("/").text
    assert "Needs you" in page
    # Feedback ticket 84: one row per kind of decision; this kind has two, so it opens its own page.
    assert "Activity to sort out · 2" in page and 'href="/needs-you/activity"' in page
    assert "Imported activity needs a decision, 1 payment has no category" in page
    group = client.get("/needs-you/activity").text
    assert "Imported activity needs a decision" in group and "cib-oct.csv · 1 row waits" in group
    assert "1 payment has no category" in group and "Sort them out" in group


def test_a_kind_of_decision_with_one_item_leads_straight_to_it(c, setup):
    accounts, _ = setup
    c.bank_imports.stage(accounts["cib"].id, "cib-oct.csv", b"Date,Counterparty,Amount\n2026-10-03,Shop,-5\n")
    page = TestClient(create_app(c)).get("/").text
    assert "Imported activity needs a decision</b>" in page and "Finish the import" in page
    assert "/needs-you/activity" not in page and "Activity to sort out" not in page


def test_inbox_groups_follow_the_link_of_each_item():
    from lightning.workflows.review import group_of
    assert group_of({"href": "/plan/items/3/pay?due=2026-10-01"}) == "payments"
    assert group_of({"href": "/gameya/2#record-instalment"}) == "payments"
    assert group_of({"href": "/plan/reserves"}) == "cash"
    assert group_of({"href": "/budget/move?month=2026-10"}) == "budget"
    assert group_of({"href": "/settings?section=currencies&tab=rates"}) == "prices"
    assert group_of({"href": "/sms"}) == "activity"


def test_the_sort_them_out_link_says_the_register_is_filtered(c, setup):
    accounts, _ = setup
    spent = c.categories.get_by_code("EXP.UNACCOUNTED")
    c.transactions.record_outflow("2026-10-02", accounts["cib"].id, "40", spent.id, allow_system_category=True)
    page = TestClient(create_app(c)).get(f"/transactions?category_id={spent.id}").text
    assert f"Only {c.categories.display_name(spent.id)} · 1 transaction" in page
    assert '<a class="btn small" href="/transactions">Clear</a>' in page
