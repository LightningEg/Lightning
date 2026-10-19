"""End-to-end checks for virtual cash allocation and activity annotations."""
from decimal import Decimal

import pytest

from lightning.core.errors import ConflictError, ValidationError
from lightning.ui.web import create_app
from lightning.workflows.activity import ActivityReview


def _cash(c, amount="5000"):
    account = c.account_flows.open_account("Everyday", "BANK", "2026-09-01", amount)
    return account


def _expense(c, account, amount="1000", category=None, day="2026-12-31"):
    category = category or c.categories.get_by_code("EXP.PERSONAL.FOOD")
    return c.transactions.record_outflow(day, account.id, amount, category.id)


def _ledger_state(c, account, day="2026-12-31"):
    balance = c.reporting.account_balance(account.id, day)
    count = c.db.scalar("SELECT COUNT(*) FROM ledger_entries")
    return balance, count


def test_partial_reserve_link_is_an_annotation_and_keeps_reserve_open(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    expense = _expense(c, account, "600", food)
    reserve = c.reserves.create("Groceries", "1000", category_id=food.id)
    c.reserves.allocate(reserve["id"], "1000")
    before = _ledger_state(c, account)

    c.reserves.set_expense_link(reserve["id"], expense.id, "250")

    updated = c.reserves.get(reserve["id"])
    assert updated["status"] == "ACTIVE"
    assert updated["allocated"] == Decimal("1000")
    assert updated["spent"] == Decimal("250")
    assert updated["effective_allocated"] == Decimal("750")
    assert _ledger_state(c, account) == before

    with pytest.raises(ValidationError):
        c.reserves.set_expense_link(10**30, expense.id, "1")


def test_reimbursement_partial_receipt_is_unique_and_dynamic_after_edits(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    expense = _expense(c, account, "1000", food, "2026-10-01")
    claim = c.reimbursements.create_claim(expense.id, "1000")
    receipt = c.transactions.record_inflow("2026-10-02", account.id, "600",
                                           c.categories.get_by_code("EXP.WORK.SALARY").id)
    ledger_before = _ledger_state(c, account, "2026-10-02")

    c.reimbursements.link_receipt(claim["id"], receipt.id, "600")
    row = c.reimbursements.list_claims()[0]
    assert row["received"] == Decimal("600")
    assert row["outstanding"] == Decimal("400")
    assert receipt.id not in {r["transaction_id"] for r in c.reimbursements.available_receipts()}
    with pytest.raises((ConflictError, ValidationError)):
        c.reimbursements.link_receipt(claim["id"], receipt.id, "1")
    assert _ledger_state(c, account, "2026-10-02") == ledger_before

    c.transactions.update_money(expense.id, "2026-10-01", account.id, "500", food.id)
    row = c.reimbursements.list_claims()[0]
    assert row["outstanding"] == Decimal("0")
    assert row["issues"]
    c.transactions.void(receipt.id, "duplicate")
    row = c.reimbursements.list_claims()[0]
    assert row["received"] == Decimal("0")
    assert any("no longer a posted" in issue for issue in row["issues"])


def test_reimbursement_rechecks_changed_expense_before_adding_a_receipt(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    expense = _expense(c, account, "1000", food, "2026-10-01")
    claim = c.reimbursements.create_claim(expense.id, "1000")
    receipt = c.transactions.record_inflow("2026-10-02", account.id, "500",
                                           c.categories.get_by_code("EXP.WORK.SALARY").id)
    c.transactions.update_money(expense.id, "2026-10-01", account.id, "400", food.id)
    with pytest.raises(ValidationError, match="current outstanding"):
        c.reimbursements.link_receipt(claim["id"], receipt.id, "500")
    summary = c.reimbursements.list_claims()[0]
    assert summary["received"] == Decimal("0")
    assert summary["issues"]
    assert receipt.id in {r["transaction_id"] for r in c.reimbursements.available_receipts()}


def test_reimbursement_rejects_claim_over_owned_expense_and_cross_claim_receipt(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    first = _expense(c, account, "500", food, "2026-10-01")
    second = _expense(c, account, "500", food, "2026-10-02")
    with pytest.raises(ValidationError):
        c.reimbursements.create_claim(first.id, "501")
    claim_a = c.reimbursements.create_claim(first.id, "500")
    claim_b = c.reimbursements.create_claim(second.id, "500")
    receipt = c.transactions.record_refund("2026-10-03", account.id, "500", food.id)
    c.reimbursements.link_receipt(claim_a["id"], receipt.id, "200")
    with pytest.raises((ConflictError, ValidationError)):
        c.reimbursements.link_receipt(claim_b["id"], receipt.id, "100")
    by_id = {row["id"]: row for row in c.reimbursements.list_claims()}
    assert by_id[claim_b["id"]]["received"] == Decimal("0")


def test_funding_uses_owned_cash_not_expected_income_and_apply_undo(c):
    account = _cash(c, "2000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    salary = c.categories.get_by_code("EXP.WORK.SALARY")
    c.budgets.set_budget(food.id, "2026-12", "1000")
    c.planning.create(kind="INCOME", name="Expected salary", amount="50000", frequency="ONCE",
                     start_date="2026-12-31", account_id=account.id, category_id=salary.id)
    c.settings.set("cash_funding_enabled", "1")
    preview = c.funding.preview()
    assert preview["cash"] == Decimal("2000")
    row = next(line for line in preview["rows"] if line["id"] == food.id)
    assert row["suggested"] <= Decimal("2000")

    ledger_before = c.db.scalar("SELECT COUNT(*) FROM ledger_entries")
    c.funding.apply(preview["token"], {str(food.id): "600"}, {})
    actual = c.db.scalar("SELECT amount_e6 FROM cash_funding WHERE month='2026-12' AND category_id=?", (food.id,))
    assert actual == 600_000_000
    assert c.db.scalar("SELECT COUNT(*) FROM ledger_entries") == ledger_before
    undo = c.undo.available()["undo"]
    assert undo and undo["label"] == "Fund the payday plan"
    c.undo.replay(expected_id=undo["id"])
    assert c.db.scalar("SELECT COUNT(*) FROM cash_funding WHERE month='2026-12' AND category_id=?", (food.id,)) == 0


def test_funding_rejects_overassignment_and_stale_preview(c):
    account = _cash(c, "1000")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    c.budgets.set_budget(food.id, "2026-12", "2000")
    c.settings.set("cash_funding_enabled", "1")
    preview = c.funding.preview()
    with pytest.raises(ValidationError):
        c.funding.apply(preview["token"], {str(food.id): "2000"}, {})

    fresh = c.funding.preview()
    _expense(c, account, "100", food)
    with pytest.raises(ValidationError, match="changed"):
        c.funding.apply(fresh["token"], {}, {})


def test_activity_combined_category_bill_and_partial_reserve_is_atomic_and_undoable(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    expense = _expense(c, account, "600", food)
    item_id = c.planning.create(kind="BILL", name="Transit pass", amount="600", frequency="ONCE",
                                start_date="2026-12-31", account_id=account.id,
                                category_id=transport.id)
    # This rule matches the account before and after the combined category change.
    # A category-restricted rule now requires that category to match as well.
    reserve = c.reserves.create("Transit", "1000", account_id=account.id)
    c.reserves.allocate(reserve["id"], "1000")
    review = ActivityReview(c)
    initial = review.summary(expense.id)
    payment = next(row for row in initial["planned_choices"] if row["item_id"] == item_id)
    assert any(row["id"] == reserve["id"] for row in initial["reserve_choices"])
    before = _ledger_state(c, account)

    review.apply(expense.id, initial["fingerprint"], category_id=transport.id,
                 payment=f"{item_id}|{payment['due_date']}", reserve_id=reserve["id"],
                 reserve_amount="250")
    assert c.transactions.get(expense.id).lines[0].category_id == transport.id
    assert c.db.scalar("SELECT transaction_id FROM planned_payments WHERE planned_item_id=?", (item_id,)) == expense.id
    assert c.reserves.links_for_transaction(expense.id)[0]["amount"] == Decimal("250")
    assert _ledger_state(c, account) == before

    undo = c.undo.available()["undo"]
    assert undo and undo["label"] == "Review activity"
    c.undo.replay(expected_id=undo["id"])
    assert c.transactions.get(expense.id).lines[0].category_id == food.id
    assert c.db.scalar("SELECT transaction_id FROM planned_payments WHERE planned_item_id=?", (item_id,)) is None
    assert c.reserves.links_for_transaction(expense.id) == []
    assert _ledger_state(c, account) == before


def test_activity_combined_failure_rolls_back_earlier_category_change(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    expense = _expense(c, account, "600", food)
    item_id = c.planning.create(kind="BILL", name="Different bill", amount="600", frequency="ONCE",
                                start_date="2026-12-31", account_id=account.id,
                                category_id=food.id)
    review = ActivityReview(c)
    initial = review.summary(expense.id)
    before = _ledger_state(c, account)
    # A current loose candidate is shown before recategorizing, but becomes an
    # invalid strict match after the chosen category changes.
    payment = next(row for row in initial["planned_choices"] if row["item_id"] == item_id)
    with pytest.raises(ValidationError):
        review.apply(expense.id, initial["fingerprint"], category_id=transport.id,
                     payment=f"{item_id}|{payment['due_date']}")
    assert c.transactions.get(expense.id).lines[0].category_id == food.id
    assert c.db.scalar("SELECT transaction_id FROM planned_payments WHERE planned_item_id=?", (item_id,)) is None
    assert _ledger_state(c, account) == before


def test_activity_rejects_stale_transaction_fingerprint(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    transport = c.categories.get_by_code("EXP.PERSONAL.TRANSPORT")
    expense = _expense(c, account, "600", food)
    review = ActivityReview(c)
    stale = review.summary(expense.id)["fingerprint"]
    c.transactions.update_money(expense.id, "2026-12-30", account.id, "500", food.id)
    with pytest.raises(ValidationError, match="changed"):
        review.apply(expense.id, stale, category_id=transport.id)
    assert c.transactions.get(expense.id).lines[0].category_id == food.id


def test_activity_http_apply_uses_current_fingerprint_and_existing_annotation(c):
    account = _cash(c)
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    expense = _expense(c, account, "600", food)
    reserve = c.reserves.create("Groceries", "1000", category_id=food.id)
    c.reserves.allocate(reserve["id"], "1000")
    from fastapi.testclient import TestClient
    client = TestClient(create_app(c))
    page = client.get(f"/activity/{expense.id}")
    assert page.status_code == 200
    fingerprint = ActivityReview(c).summary(expense.id)["fingerprint"]
    response = client.post(f"/activity/{expense.id}/apply", data={
        "fingerprint": fingerprint, "reserve_id": str(reserve["id"]), "reserve_amount": "250"})
    assert response.status_code in (200, 303)
    assert c.reserves.links_for_transaction(expense.id)[0]["amount"] == Decimal("250")
