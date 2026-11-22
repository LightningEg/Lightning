"""An employer advance changes personal costs while the bank still shows each cash movement."""
from decimal import Decimal

from fastapi.testclient import TestClient

from lightning.core.dates import parse_month
from lightning.ui.web import create_app


def test_full_advance_partial_repayment_and_writeoff(c, setup):
    account = setup[0]["cib"]
    work = c.categories.get_by_code("EXP.WORK.TRANSPORT").id
    client = TestClient(create_app(c))
    form = {"kind": "out", "amount": "10000", "date": "2026-09-15", "category_id": work,
            "paid_for_work": "1", "submission": "work-trip-10000", "return_to": "/budget"}
    saved = client.post(f"/accounts/{account.id}/transaction/new", data=form, follow_redirects=False)
    assert saved.status_code == 303
    claim, = c.reimbursements.list_claims()
    assert claim["paid_for_work"] and claim["expected"] == 10000
    sep, oct_ = parse_month("2026-09"), parse_month("2026-10")
    assert c.budgets.owned_spending(*sep).get(work, 0) == 0
    assert sum(r["value"] for r in c.reporting.spending_lines(*sep)) == 0
    assert c.reporting.cash_flow(*sep).outflows == 10000
    receipt = c.transactions.record_inflow("2026-10-08", account.id, "8000", work)
    c.reimbursements.link_receipt(claim["id"], receipt.id, "8000")
    assert c.budgets.owned_spending(*oct_).get(work, 0) == 0
    assert c.budgets.estimate_spending(*oct_).get(work, 0) == 0
    assert c.reimbursements.work_period(*sep)[0]["owed"] == 10000
    assert c.reimbursements.work_period(*oct_)[0]["owed"] == 2000
    assert c.reporting.cash_flow(*oct_).outflows == -8000
    assert "Owed at period end" in client.get("/budget?month=2026-09").text
    c.reimbursements.close_work_claim(claim["id"], "2026-11-01")
    assert c.budgets.owned_spending(*sep)[work] == 2000
    assert c.reimbursements.work_period(*oct_)[0]["owed"] == 2000
    assert c.reimbursements.list_claims()[0]["outstanding"] == 0


def test_salary_includes_only_personal_share_and_sms_can_link_the_receipt(c, setup):
    account = setup[0]["cib"]
    work = c.categories.get_by_code("EXP.WORK.TRANSPORT").id
    salary = c.categories.get_by_code("EXP.WORK.SALARY").id
    employer = c.counterparties.create("Employer")
    expense = c.transactions.record_outflow("2026-09-15", account.id, "12000", work)
    claim = c.reimbursements.create_claim(expense.id, "10000", employer)
    c.reimbursements.mark_paid_for_work(claim["id"])
    receipt = c.transactions.record_inflow("2026-10-08", account.id, "35000", salary, counterparty="Employer")
    batch, _ = c.bank_imports.stage(account.id, "SMS 2026-10-08", b"Date,Amount,Counterparty\n2026-10-08,35000,Employer\n")
    row, = c.bank_imports.preview(batch)[1]
    assert not c.bank_imports.confirm(batch, {row["_import_row_id"]: {"match": f"link:{receipt.id}"}})["errors"]
    client = TestClient(create_app(c))
    assert "Apply to work claim" in client.get("/sms").text
    client.post(f"/reimbursements/{claim['id']}/receipts", data={"receipt_id": receipt.id, "amount": "10000"})
    assert c.budgets.owned_spending(*parse_month("2026-09"))[work] == 2000
    assert sum(g.value for g in c.reporting.money_in_by_category(*parse_month("2026-10"))) == Decimal("25000")
    assert c.reporting.cash_flow(*parse_month("2026-10")).inflows == 35000
    assert c.reimbursements.list_claims()[0]["outstanding"] == 0
    assert "Apply to work claim" not in client.get("/sms").text


def test_invalid_work_amount_rolls_back_expense(c, setup):
    account = setup[0]["cib"]
    count = c.db.scalar("SELECT COUNT(*) FROM transactions")
    response = TestClient(create_app(c)).post(f"/accounts/{account.id}/transaction/new", data={
        "kind": "out", "date": "2026-09-15", "amount": "100", "category_id": c.categories.get_by_code("EXP.WORK.TRANSPORT").id,
        "paid_for_work": "1", "work_expected": "110"})
    assert response.status_code == 400
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == count


def test_merchant_refund_reduces_work_owed_and_keeps_personal_spending_zero(c, setup):
    account = setup[0]["cib"]
    work = c.categories.get_by_code("EXP.WORK.TRANSPORT").id
    client = TestClient(create_app(c), follow_redirects=False)
    response = client.post(f"/accounts/{account.id}/transaction/new", data={
        "kind": "out", "date": "2026-09-15", "amount": "1000", "category_id": work, "paid_for_work": "1"})
    assert response.status_code == 303
    claim, = c.reimbursements.list_claims()
    response = client.post(f"/transactions/{claim['expense_id']}/refund",
                           data={"date": "2026-10-08", "amount": "400"})
    assert response.status_code == 303
    refund, = c.refunds.refunds_of(claim["expense_id"])
    sep, oct_ = parse_month("2026-09"), parse_month("2026-10")

    updated, = c.reimbursements.list_claims()
    assert updated["outstanding"] == 600
    assert updated["received"] == 0
    assert c.reimbursements.work_period(*sep)[0]["owed"] == 1000
    october, = c.reimbursements.work_period(*oct_)
    assert (october["owed"], october["repaid"], october["refunded"]) == (600, 0, 400)
    assert "Merchant refund 400" in client.get("/budget?month=2026-10").text
    assert "Merchant refund 400" in client.get("/reimbursements").text
    assert c.budgets.owned_spending(*oct_).get(work, 0) == 0
    assert sum(row["value"] for row in c.reporting.spending_lines(*oct_)) == 0
    assert c.reporting.cash_flow(*oct_).outflows == -400
    assert c.reporting.account_balance(account.id, oct_[1]) == 49400
    assert all(r["transaction_id"] != refund["refund_id"] for r in c.reimbursements.available_receipts())

    c.refunds.unlink(refund["refund_id"])
    assert c.reimbursements.list_claims()[0]["outstanding"] == 1000
    assert c.budgets.owned_spending(*oct_)[work] == -400


def test_partial_work_claim_preserves_personal_refund_and_counts_refund_before_writeoff(c, setup):
    account = setup[0]["cib"]
    work = c.categories.get_by_code("EXP.WORK.TRANSPORT").id
    expense = c.transactions.record_outflow("2026-09-15", account.id, "1000", work)
    claim = c.reimbursements.create_work_claim(expense.id, "600")
    refund = c.refunds.record_refund(expense.id, "2026-10-08", "700")
    receipt = c.transactions.record_inflow("2026-10-09", account.id, "200", work)
    c.reimbursements.link_receipt(claim["id"], receipt.id, "200")
    sep, oct_ = parse_month("2026-09"), parse_month("2026-10")
    assert c.reimbursements.list_claims()[0]["outstanding"] == 100
    assert c.budgets.owned_spending(*sep)[work] == 400
    assert c.budgets.owned_spending(*oct_)[work] == -400
    assert c.budgets.estimate_spending(*sep).get(work, 0) == 0
    assert c.budgets.estimate_spending(*oct_).get(work, 0) == 0

    c.reimbursements.close_work_claim(claim["id"], "2026-11-01")
    assert c.budgets.owned_spending(*sep)[work] == 500
    assert c.budgets.estimate_spending(*sep)[work] == 100
    assert c.reimbursements.work_period(*oct_)[0]["owed"] == 100
    assert c.reimbursements.list_claims()[0]["outstanding"] == 0
    c.budgets.set_left_out(expense.id, True)
    assert c.budgets.estimate_spending(*sep).get(work, 0) == 0
    assert c.budgets.estimate_spending(*oct_).get(work, 0) == 0

    c.transactions.void(refund["refund_id"])
    assert c.budgets.owned_spending(*sep)[work] == 800
