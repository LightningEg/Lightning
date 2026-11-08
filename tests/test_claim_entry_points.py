"""NF-3AZ5: a reimbursable expense offers Create claim and an unmatched receipt offers Match reimbursement; both reach the
same claim, claim outstanding and cash received stay separate, and a partial match reduces the claim once."""
from __future__ import annotations

from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _world(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-06")
    account = setup[0]["cib"]
    category = c.categories.get_by_code("EXP.WORK.TRANSPORT")
    c.db.execute("UPDATE categories SET default_reimbursable=1 WHERE id=?", (category.id,))
    expense = c.transactions.record_outflow("2026-09-08", account.id, "1200", category.id, counterparty="Uber")
    return account, category, expense


def test_a_reimbursable_expense_offers_create_claim_and_both_doors_reach_one_claim(c, setup, monkeypatch):
    account, category, expense = _world(c, setup, monkeypatch)
    client = TestClient(create_app(c))
    page = client.get(f"/transactions/{expense.id}")
    assert "Create claim" in page.text and f"/reimbursements?expense_id={expense.id}&amp;expected=1200" in page.text
    claim_page = client.get(f"/reimbursements?expense_id={expense.id}&expected=1200")
    assert 'value="1200"' in claim_page.text
    made = client.post("/reimbursements", data={"transaction_id": str(expense.id), "expected": "1200"}, follow_redirects=False)
    assert made.status_code == 303 and len(c.reimbursements.list_claims()) == 1
    again = client.get(f"/transactions/{expense.id}")
    assert "Create claim" not in again.text                                  # one claim per expense
    # The receipt is a different door to the same claim.
    receipt = c.transactions.record_inflow("2026-09-21", account.id, "500", category.id, counterparty="ACME")
    rpage = client.get(f"/transactions/{receipt.id}")
    assert "Match reimbursement" in rpage.text and f"/reimbursements?receipt_id={receipt.id}" in rpage.text
    claim = c.reimbursements.list_claims()[0]
    cash = c.reporting.account_balance(account.id, "2026-10-06")
    picker = client.get(f"/reimbursements?receipt_id={receipt.id}")
    assert f'value="{receipt.id}" selected' in picker.text and 'value="500.00"' in picker.text   # a partial match is prefilled
    client.post(f"/reimbursements/{claim['id']}/receipts", data={"receipt_id": str(receipt.id), "amount": "500"})
    after = c.reimbursements.list_claims()[0]
    assert after["received"] == D("500") and after["outstanding"] == D("700")    # reduced once
    assert c.reporting.account_balance(account.id, "2026-10-06") == cash         # linking moves no money
    assert "Match reimbursement" not in client.get(f"/transactions/{receipt.id}").text
