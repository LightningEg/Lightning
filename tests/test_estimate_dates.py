"""An estimate date attributes only the eligible share; bank activity stays on its posting date."""
import pytest

from lightning.core.dates import parse_month
from lightning.core.errors import ValidationError
from tests.test_refund_links import _client


def test_purchase_refund_and_remainder_can_use_three_dates(c, setup):
    bank = setup[0]["cib"].id
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    purchase = c.transactions.record_outflow("2026-10-01", bank, 1000, food)
    refund = c.transactions.record_refund("2026-11-05", bank, 400, food)
    link = c.refunds.link(refund.id, purchase.id, 300)
    for month in ("09", "10", "11", "12"):
        c.transactions.record_outflow(f"2026-{month}-02", bank, 500, food)

    def basis():
        return [c.budgets.estimate_spending(*parse_month(f"2026-{m}"))[food] for m in ("09", "10", "11", "12")]

    c.budgets.set_estimate_date(purchase.id, "2026-09-30")
    assert basis() == [1200, 500, 400, 500]
    c.budgets.set_estimate_date(refund.id, "2026-12-01")
    assert basis() == [1200, 500, 500, 400]
    c.refunds.set_estimate_date(link["id"], "2026-10-01")
    assert basis() == [1500, 200, 500, 400]
    c.refunds.set_estimate_date(link["id"], None)
    assert basis() == [1200, 500, 500, 400]
    c.refunds.unlink(refund.id)
    assert basis() == [1500, 500, 500, 100]
    c.undo.replay()
    assert basis() == [1200, 500, 500, 400]
    assert c.budgets.owned_spending(*parse_month("2026-10"))[food] == 1500
    assert c.budgets.owned_spending(*parse_month("2026-11"))[food] == 100


@pytest.mark.parametrize("phone", [False, True])
def test_entry_date_and_recovery_date_through_forms(c, setup, phone):
    bank = setup[0]["cib"].id
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    client = _client(c, phone)
    entry = f"/accounts/{bank}/transaction/new"
    assert 'name="estimate_date"' in client.get(entry).text
    data = dict(kind="out", amount="1000", date="2026-10-01", category_id=str(food),
                estimate_date="2026-09-30", submission="a" * 32)
    count = c.db.scalar("SELECT count(*) FROM transactions")
    assert client.post(entry, data=data | {"estimate_date": "2026-02-30"}).status_code == 400
    assert c.db.scalar("SELECT count(*) FROM transactions") == count
    assert client.post(entry, data=data).status_code == 303
    assert client.post(entry, data=data).status_code == 303
    assert c.db.scalar("SELECT count(*) FROM transactions") == count + 1
    tid = c.db.scalar("SELECT transaction_id FROM budget_estimate_dates")
    assert c.budgets.estimate_date(tid) == "2026-09-30"
    assert 'datetime="2026-09-30"' in client.get(f"/transactions/{tid}").text
    claim = c.reimbursements.create_claim(tid, 500)
    receipt = c.transactions.record_inflow("2026-11-05", bank, 200, food)
    assert client.post(f"/reimbursements/{claim['id']}/receipts", data=dict(
        amount="200", receipt_id=receipt.id, estimate_date="2026-09-15")).status_code == 303
    assert c.budgets.estimate_attribution(receipt.id)[0]["effective_date"] == "2026-09-15"
    link = c.reimbursements.list_claims()[0]["receipts"][0]
    assert client.post(f"/reimbursements/receipts/{link['id']}/estimate-date",
                       data={"estimate_date": ""}).status_code == 303
    assert c.budgets.estimate_attribution(receipt.id)[0]["effective_date"] == "2026-09-30"
    assert c.reimbursements.list_claims()[0]["outstanding"] == 300


def test_reserve_funding_and_exclusions_are_applied_before_dates(c, setup):
    bank = setup[0]["cib"].id
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    expense = c.transactions.record_outflow("2026-12-03", bank, 500, food)
    reserve = c.reserves.create("Holiday", "300")
    c.reserves.allocate(reserve["id"], "300")
    c.reserves.set_expense_link(reserve["id"], expense.id, "300")
    c.budgets.set_estimate_date(expense.id, "2027-01-02")
    assert c.budgets.estimate_spending(*parse_month("2027-01"))[food] == 200
    c.budgets.set_left_out(expense.id, True)
    assert food not in c.budgets.estimate_spending(*parse_month("2027-01"))
    income = c.transactions.record_inflow("2026-12-03", bank, 500, c.categories.get_by_code("EXP.WORK.SALARY").id)
    with pytest.raises(ValidationError):
        c.budgets.set_estimate_date(income.id, "2027-01-02")


def test_old_profile_uses_automatic_dates_after_upgrade(tmp_path, monkeypatch):
    from shutil import copy2

    from lightning.bootstrap import build
    from lightning.database import migrator

    previous = tmp_path / "schema91"
    previous.mkdir()
    for file in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(file.name[:4]) <= 91:
            copy2(file, previous)
    profile = tmp_path / "family.db"
    with monkeypatch.context() as old:
        old.setattr(migrator, "MIGRATIONS_DIR", previous)
        c = build(profile)
        try:
            bank = c.account_flows.open_account("Cash", "CASH", "2026-09-01", "5000").id
            food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
            purchase = c.transactions.record_outflow("2026-09-02", bank, 500, food)
            c.refunds.record_refund(purchase.id, "2026-10-02", 100)
            before = [tuple(r) for r in c.db.all("SELECT * FROM ledger_entries ORDER BY id")]
        finally:
            c.db.close()
    c = build(profile)
    try:
        assert c.db.scalar("SELECT count(*) FROM budget_estimate_dates") == 0
        assert c.db.scalar("SELECT estimate_date_override FROM refund_links") is None
        assert c.budgets.estimate_spending(*parse_month("2026-09"))[food] == 400
        assert [tuple(r) for r in c.db.all("SELECT * FROM ledger_entries ORDER BY id")] == before
        assert migrator.migrate(c.db) == []
    finally:
        c.db.close()


def test_mixed_deposit_moves_only_the_spending_portion(c, setup):
    from decimal import Decimal

    from lightning.core.ledger import Effect, PostingLine
    from lightning.core.refs import DocType

    bank = setup[0]["cib"].id
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD").id
    salary = c.categories.get_by_code("EXP.WORK.SALARY").id
    cash = c.assets.cash_asset("EGP").id
    purchase = c.transactions.record_outflow("2026-09-02", bank, "1000", food)
    claim = c.reimbursements.create_claim(purchase.id, "300")
    receipt = c.transactions.post(DocType.IN, "2026-10-12", [
        PostingLine.cash(bank, cash, Decimal("2000"), Effect.INFLOW, salary),
        PostingLine.cash(bank, cash, Decimal("300"), Effect.OUTFLOW, food),
    ])
    c.reimbursements.link_dated_receipt(claim["id"], receipt.id, "300", "2026-09-10")
    assert c.budgets.estimate_spending(*parse_month("2026-09"))[food] == 700
    assert food not in c.budgets.estimate_spending(*parse_month("2026-10"))
    assert sum(g.value for g in c.reporting.money_in_by_category(*parse_month("2026-10"))) == 2000
    assert c.budgets.estimate_attribution(receipt.id) == [dict(transaction_id=receipt.id, category_id=food,
        linked=True, amount=-300, posting_date="2026-10-12", effective_date="2026-09-10")]
