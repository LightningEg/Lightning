from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ConflictError, ValidationError
from lightning.ui.web import create_app


def _certificate(c, accounts, name="Monthly receipt certificate"):
    certificate, _ = c.deposits.purchase(
        accounts["cd"].id, name=name, start_date="2026-09-01",
        lockup_end_date="2026-09-01", maturity_date="2027-09-01", principal="5000", annual_rate="12.5",
        interest_method="SIMPLE", payout_frequency="MONTHLY", compounding_frequency="MONTHLY",
        destination_account_id=accounts["cib"].id, funding_account_id=accounts["cib"].id)
    return certificate


def _receipt(c, account_id, amount, day, category_id, name="Bank interest"):
    return c.transactions.record_inflow(day, account_id, amount, category_id, counterparty=name)


def test_certificate_receipts_allow_partial_multiple_confirmations_and_reduce_projection(c, setup):
    accounts, cats = setup
    certificate = _certificate(c, accounts)
    event_date = "2026-10-01"
    expected_event = next(e for e in c.deposits._certificate_events(
        certificate.terms, date(2026, 8, 31), date.fromisoformat(event_date))
                          if e.kind == "INTEREST")
    expected = expected_event.amount
    assert expected == Decimal("52.083333")  # 5,000 x 12.5% / 12, as the bank pays a month (IV-12J2)
    first = _receipt(c, accounts["cib"].id, "20", event_date, cats["EXP.INVEST.INTEREST"].id)
    second = _receipt(c, accounts["cib"].id, "15", event_date, cats["EXP.INVEST.INTEREST"].id)
    balance_before_confirmation = c.reporting.account_balance(accounts["cib"].id)
    result = c.deposit_receipts.confirm(certificate.terms.id, event_date, [first.id, second.id])
    assert result["received"] == Decimal("35")
    assert result["remaining"] == expected - Decimal("35")
    assert {item["transaction_id"] for item in result["receipts"]} == {first.id, second.id}

    projected = replace(expected_event, date=event_date)
    adjusted = c.deposit_receipts.adjust_events([projected], "2026-12-31")
    assert len(adjusted) == 1 and adjusted[0].amount == expected - Decimal("35")

    final = _receipt(c, accounts["cib"].id, "17.09", event_date,
                     cats["EXP.INVEST.INTEREST"].id)
    completed = c.deposit_receipts.confirm(certificate.terms.id, event_date, [final.id])
    assert completed["remaining"] == Decimal("0")
    assert c.deposit_receipts.adjust_events([projected], "2026-12-31") == []
    # Reconciliation creates no ledger entries and does not change actual certificate returns.
    assert c.reporting.account_balance(accounts["cib"].id) == balance_before_confirmation + Decimal("17.09")


def test_receipts_validate_one_use_and_exclude_reimbursement_receipts(c, setup):
    accounts, cats = setup
    certificate = _certificate(c, accounts)
    event_date = "2026-10-01"
    receipt = _receipt(c, accounts["cib"].id, "10", event_date, cats["EXP.INVEST.INTEREST"].id)
    # Any receipt already consumed by reimbursement reconciliation is unavailable to a certificate.
    expense = c.transactions.record_outflow("2026-10-01", accounts["cib"].id, "25",
                                            cats["EXP.PERSONAL.FOOD"].id)
    claim = c.reimbursements.create_claim(expense.id, "10")
    c.reimbursements.link_receipt(claim["id"], receipt.id, "10")
    with pytest.raises(ConflictError, match="reimbursement claim"):
        c.deposit_receipts.confirm(certificate.terms.id, event_date, [receipt.id])

    free = _receipt(c, accounts["cib"].id, "10", event_date, cats["EXP.INVEST.INTEREST"].id)
    c.deposit_receipts.confirm(certificate.terms.id, event_date, [free.id])
    with pytest.raises(ConflictError, match="already linked"):
        c.deposit_receipts.confirm(certificate.terms.id, event_date, [free.id])
    other_certificate = _certificate(c, accounts, "Second receipt certificate")
    with pytest.raises(ConflictError, match="only one certificate payout"):
        c.deposit_receipts.confirm(other_certificate.terms.id, event_date, [free.id])
    with pytest.raises(ValidationError, match="only once"):
        c.deposit_receipts.confirm(certificate.terms.id, event_date, [receipt.id, receipt.id])
    with pytest.raises(ValidationError):
        c.deposit_receipts.confirm(certificate.terms.id, "2026-10-02", [free.id])


def test_voided_or_edited_receipts_reopen_attention_and_future_projection(c, setup):
    accounts, cats = setup
    certificate = _certificate(c, accounts)
    event_date = "2026-10-01"
    receipt = _receipt(c, accounts["cib"].id, "10", event_date, cats["EXP.INVEST.INTEREST"].id)
    c.deposit_receipts.confirm(certificate.terms.id, event_date, [receipt.id])
    c.transactions.void(receipt.id, "duplicate")
    issues = c.deposit_receipts.attention("2026-12-31")
    issue = next(item for item in issues if item["event_date"] == event_date)
    assert issue["received"] == Decimal("0") and issue["remaining"] > 0 and issue["attention"]

    second = _receipt(c, accounts["cib"].id, "12", event_date, cats["EXP.INVEST.INTEREST"].id)
    c.deposit_receipts.remove(certificate.terms.id, event_date, receipt.id)
    c.deposit_receipts.confirm(certificate.terms.id, event_date, [second.id])
    c.transactions.update_money(second.id, event_date, accounts["cib"].id, "11",
                                cats["EXP.INVEST.INTEREST"].id, counterparty="Bank interest")
    refreshed = next(item for item in c.deposit_receipts.attention("2026-12-31")
                     if item["event_date"] == event_date)
    assert refreshed["attention"] and refreshed["received"] == Decimal("0")


def test_receipt_confirmation_page_shows_the_reconciled_occurrence(c, setup):
    accounts, cats = setup
    certificate = _certificate(c, accounts)
    event_date = "2026-10-01"
    receipt = _receipt(c, accounts["cib"].id, "10", event_date, cats["EXP.INVEST.INTEREST"].id)
    c.deposit_receipts.confirm(certificate.terms.id, event_date, [receipt.id])
    response = TestClient(create_app(c)).get(f"/deposits/{accounts['cd'].id}")
    assert response.status_code == 200 and "Expected interest receipts" in response.text
