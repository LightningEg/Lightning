from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from lightning.core.errors import ValidationError
from lightning.database.currencies import CurrencyRegistry
from lightning.planning.domain import PaymentStatus


def _bill(c, account_id, category_id, *, name="Bill", amount="100", due="2026-10-05",
          window=7, tolerance=10):
    return c.planning.create(kind="BILL", name=name, amount=amount, frequency="MONTHLY", start_date=due,
                             account_id=account_id, category_id=category_id,
                             match_window_days=window, match_tolerance_pct=tolerance)


def _usd_account(c):
    CurrencyRegistry(c.db).register("USD")
    account = c.account_flows.open_account("Dollar bank", "BANK", "2026-09-01", "0", currency="USD")
    c.db.execute("INSERT INTO fx_rates(date,base,quote,rate_e6,source,created_at) VALUES(?,?,?,?,?,?)",
                 ("2026-09-01", "USD", "EGP", 50000000, "MANUAL", "2026-09-01T00:00:00Z"))
    c.transactions.record_inflow("2026-09-02", account.id, "1000", c.categories.get_by_code("EXP.WORK.SALARY").id)
    return account


def test_zero_match_window_and_tolerance_mean_exact(c, setup):
    accounts, cats = setup
    account_id, category_id = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    item_id = _bill(c, account_id, category_id, window=0, tolerance=0)
    item = c.planning.get(item_id)
    assert item.match_window_days == 0 and item.match_tolerance_pct == 0

    c.transactions.record_outflow("2026-10-04", account_id, "100", category_id)
    c.transactions.record_outflow("2026-10-05", account_id, "100.01", category_id)
    payment = c.planning.payments(item, "2026-10-05", date(2026, 10, 6))[0]
    assert c.planning.candidates(payment, date(2026, 10, 6)) == []
    exact = c.transactions.record_outflow("2026-10-05", account_id, "100", category_id)
    assert [row["id"] for row in c.planning.candidates(payment, date(2026, 10, 6))] == [exact.id]
    assert c.planning.match_payments(date(2026, 10, 6)) == 1
    assert c.planning.payments(item, "2026-10-05", date(2026, 10, 6))[0].status == PaymentStatus.PAID


def test_ambiguous_item_candidates_are_not_auto_linked(c, setup):
    accounts, cats = setup
    account_id, category_id = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    _bill(c, account_id, category_id, name="Electricity", window=2, tolerance=0)
    _bill(c, account_id, category_id, name="Water", window=2, tolerance=0)
    txn = c.transactions.record_outflow("2026-10-05", account_id, "100", category_id)

    assert c.planning.match_payments(date(2026, 10, 6)) == 0
    assert c.db.scalar("SELECT COUNT(*) FROM planned_payments WHERE transaction_id=?", (txn.id,)) == 0


def test_foreign_plan_matches_native_quantity_not_base_valuation(c, setup):
    _, cats = setup
    usd = _usd_account(c)
    category_id = cats["EXP.PERSONAL.FOOD"].id
    item_id = _bill(c, usd.id, category_id, amount="10", window=0, tolerance=0)
    txn = c.transactions.record_outflow("2026-10-05", usd.id, "10", category_id)
    item = c.planning.get(item_id)
    payment = c.planning.payments(item, "2026-10-05", date(2026, 10, 6))[0]

    candidates = c.planning.candidates(payment, date(2026, 10, 6))
    assert len(candidates) == 1 and candidates[0]["amount"] == Decimal("10")
    assert txn.lines[0].quantity == Decimal("-10")
    assert c.planning.match_payments(date(2026, 10, 6)) == 1


def test_manual_matching_rejects_amount_drift_over_saved_tolerance(c, setup):
    accounts, cats = setup
    account_id, category_id = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    item_id = _bill(c, account_id, category_id, amount="100", window=2, tolerance=5)
    txn = c.transactions.record_outflow("2026-10-05", account_id, "151", category_id)

    with pytest.raises(ValidationError, match="amount is too far"):
        c.planning.mark_paid(item_id, "2026-10-05", txn.id)
    assert c.db.scalar("SELECT COUNT(*) FROM planned_payments WHERE transaction_id=?", (txn.id,)) == 0


def test_manual_suggestions_can_review_a_salary_eight_days_before_due(c, setup):
    accounts, cats = setup
    account_id = accounts["cib"].id
    salary = cats["EXP.WORK.SALARY"]
    txn = c.transactions.record_inflow("2026-12-24", account_id, "30000", salary.id,
                                        counterparty="Employer")
    employer = c.counterparties.resolve("Employer")
    item_id = c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY",
                                start_date="2027-01-01", account_id=account_id, category_id=salary.id,
                                counterparty_id=employer["id"], match_window_days=7, match_tolerance_pct=10)
    item = c.planning.get(item_id)
    payment = c.planning.payments(item, "2027-01-01", date(2027, 1, 1))[0]

    assert c.planning.candidates(payment, date(2027, 1, 1)) == []
    assert [row["id"] for row in c.planning.plausible_candidates(payment, date(2027, 1, 1))] == [txn.id]
    assert c.planning.match_payments(date(2027, 1, 1)) == 0
    c.planning.mark_paid(item_id, "2027-01-01", txn.id)
    assert c.planning.payments(item, "2027-01-01", date(2027, 1, 1))[0].status == PaymentStatus.PAID


def test_manual_suggestions_can_review_changed_amount_but_auto_matching_cannot(c, setup):
    accounts, cats = setup
    account_id = accounts["cib"].id
    salary = cats["EXP.WORK.SALARY"]
    txn = c.transactions.record_inflow("2026-12-31", account_id, "42000", salary.id,
                                        counterparty="Employer")
    employer = c.counterparties.resolve("Employer")
    item_id = c.planning.create(kind="INCOME", name="Salary", amount="30000", frequency="MONTHLY",
                                start_date="2026-12-31", account_id=account_id, category_id=salary.id,
                                counterparty_id=employer["id"], match_window_days=7, match_tolerance_pct=10)
    item = c.planning.get(item_id)
    payment = c.planning.payments(item, "2026-12-31", date(2026, 12, 31))[0]

    assert c.planning.candidates(payment, date(2026, 12, 31)) == []
    assert [row["id"] for row in c.planning.plausible_candidates(payment, date(2026, 12, 31))] == [txn.id]
    assert c.planning.match_payments(date(2026, 12, 31)) == 0
    c.planning.mark_paid(item_id, "2026-12-31", txn.id)
    assert c.planning.payments(item, "2026-12-31", date(2026, 12, 31))[0].status == PaymentStatus.PAID


def test_refund_does_not_match_an_outgoing_bill(c, setup):
    accounts, cats = setup
    account_id, category_id = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    item_id = _bill(c, account_id, category_id, amount="30", window=0, tolerance=0)
    refund = c.transactions.record_refund("2026-10-05", account_id, "30", category_id)
    item = c.planning.get(item_id)
    payment = c.planning.payments(item, "2026-10-05", date(2026, 10, 6))[0]

    assert c.planning.candidates(payment, date(2026, 10, 6)) == []
    with pytest.raises(ValidationError, match="posted, owned transaction"):
        c.planning.mark_paid(item_id, "2026-10-05", refund.id)


def test_income_matching_requires_a_positive_cash_inflow(c, setup):
    accounts, cats = setup
    account_id = accounts["cib"].id
    expense = cats["EXP.PERSONAL.FOOD"]
    income = cats["EXP.WORK.SALARY"]
    outflow = c.transactions.record_outflow("2026-10-05", account_id, "200", expense.id,
                                            counterparty="Employer")
    inflow = c.transactions.record_inflow("2026-10-05", account_id, "200", income.id,
                                          counterparty="Employer")
    party = c.counterparties.resolve("Employer")
    item_id = c.planning.create(kind="INCOME", name="Salary", amount="200", frequency="MONTHLY",
                                start_date="2026-10-05", account_id=account_id,
                                counterparty_id=party["id"], match_window_days=0, match_tolerance_pct=0)
    item = c.planning.get(item_id)
    payment = c.planning.payments(item, "2026-10-05", date(2026, 10, 6))[0]

    assert [row["id"] for row in c.planning.candidates(payment, date(2026, 10, 6))] == [inflow.id]
    assert outflow.id not in {row["id"] for row in c.planning.candidates(payment, date(2026, 10, 6))}


def test_record_payment_rejects_different_funding_currency(c, setup):
    accounts, cats = setup
    usd = _usd_account(c)
    category_id = cats["EXP.PERSONAL.FOOD"].id
    item_id = _bill(c, accounts["cib"].id, category_id, amount="10")
    unassigned_id = _bill(c, None, category_id, name="Unassigned bill", amount="10")
    before = c.db.scalar("SELECT COUNT(*) FROM transactions")

    for planned_id in (item_id, unassigned_id):
        with pytest.raises(ValidationError, match="account in EGP"):
            c.planning.record_payment(planned_id, "2026-10-05", "2026-10-05", "10", usd.id)
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before
    assert c.db.scalar("SELECT COUNT(*) FROM planned_payments WHERE planned_item_id IN (?,?)",
                       (item_id, unassigned_id)) == 0


@pytest.mark.parametrize(("due_date", "message"), [
    ("not-a-date", "scheduled payment date"),
    ("2026-10-06", "not on this payment schedule"),
])
def test_record_payment_rejects_invalid_or_off_schedule_due_date(c, setup, due_date, message):
    accounts, cats = setup
    account_id, category_id = accounts["cib"].id, cats["EXP.PERSONAL.FOOD"].id
    item_id = _bill(c, account_id, category_id, due="2026-10-05", window=0, tolerance=0)
    before_balance = c.reporting.account_balance(account_id)
    before_transactions = c.db.scalar("SELECT COUNT(*) FROM transactions")

    with pytest.raises(ValidationError, match=message):
        c.planning.record_payment(item_id, due_date, "2026-10-05", "100", account_id)
    assert c.reporting.account_balance(account_id) == before_balance
    assert c.db.scalar("SELECT COUNT(*) FROM transactions") == before_transactions
    assert c.db.scalar("SELECT COUNT(*) FROM planned_payments WHERE planned_item_id=?", (item_id,)) == 0


def test_loans_keep_profile_currency_account_restriction(c, setup):
    accounts, cats = setup
    usd = _usd_account(c)
    values = {"kind": "LOAN", "name": "Car loan", "amount": "100", "frequency": "MONTHLY",
              "start_date": "2026-10-05", "payment_count": "12", "category_id": cats["EXP.PERSONAL.FOOD"].id}
    with pytest.raises(ValidationError, match="profile currency"):
        c.planning.create(**(values | {"account_id": usd.id}))
    item_id = c.planning.create(**(values | {"account_id": accounts["cib"].id}))
    with pytest.raises(ValidationError, match="profile currency"):
        c.planning.update(item_id, **(values | {"account_id": usd.id}))


@pytest.mark.parametrize(("field", "value", "message"), [
    ("interval_count", "many", "Repeat every 1 to 52 periods"),
    ("interval_count", "0", "Repeat every 1 to 52 periods"),
    ("payment_count", "many", "Enter 1 to 600 payments"),
    ("account_id", "not-an-id", "valid option"),
    ("account_id", "0", "valid option"),
    ("account_id", "999999", "valid funding account"),
    ("account_id", "999999999999999999999999999999", "valid option"),
])
def test_invalid_numeric_counts_and_accounts_raise_validation_errors(c, setup, field, value, message):
    accounts, cats = setup
    values = {"kind": "BILL", "name": "Bill", "amount": "100", "frequency": "MONTHLY",
              "start_date": "2026-10-05", "account_id": str(accounts["cib"].id),
              "category_id": str(cats["EXP.PERSONAL.FOOD"].id)}
    with pytest.raises(ValidationError, match=message):
        c.planning.create(**(values | {field: value}))
