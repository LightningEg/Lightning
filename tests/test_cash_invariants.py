"""2G/2H: every ledger transition validates the accounts and owners it removes and adds."""
from decimal import Decimal as D

import pytest

from lightning.core.errors import ValidationError
from lightning.transactions.domain import TxnSource
from lightning.undo import user_action


@pytest.fixture
def ledger(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-09-01', '100')
    other = c.account_flows.open_account('Other bank', 'BANK', '2026-09-01', '0')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    salary = c.categories.get_by_code('EXP.WORK.SALARY').id
    return bank, other, food, salary


def snapshot(c):
    return [tuple(row) for table in ('transactions', 'ledger_entries', 'audit_log')
            for row in c.db.all(f'SELECT * FROM {table} ORDER BY id')]


@pytest.mark.parametrize('operation', ['void', 'delete_many', 'update_money', 'set_transaction_owner'])
def test_cannot_remove_cash_that_funds_later_spending(c, ledger, operation):
    bank, other, food, salary = ledger
    income = c.transactions.record_inflow('2026-09-02', bank.id, '100', salary)
    c.transactions.record_outflow('2026-09-03', bank.id, '150', food)
    owner = c.counterparties.ensure_person('Alice')
    before = snapshot(c)
    with pytest.raises(ValidationError):
        if operation == 'update_money':
            c.transactions.update_money(income.id, income.date, other.id, '100', salary)
        elif operation == 'set_transaction_owner':
            c.transactions.set_transaction_owner(income.id, owner)
        elif operation == 'delete_many':
            c.transactions.delete_many([income.id])
        else:
            c.transactions.void(income.id)
    assert snapshot(c) == before
    assert c.reporting.account_balance(bank.id) == 50


def test_restore_expense_must_fit_cash_still_available(c, ledger):
    bank, _, food, _ = ledger
    expense = c.transactions.record_outflow('2026-09-02', bank.id, '80', food)
    c.transactions.void(expense.id)
    c.transactions.record_outflow('2026-09-03', bank.id, '70', food)
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.transactions.restore(expense.id)
    assert snapshot(c) == before and c.reporting.account_balance(bank.id) == 30


@pytest.mark.parametrize('value', ['0', '10'])
def test_opening_edit_cannot_remove_funding(c, ledger, value):
    bank, _, food, _ = ledger
    c.transactions.record_outflow('2026-09-02', bank.id, '80', food)
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.account_flows.update_account(bank.id, bank.name, 'BANK', bank.opening_date, value)
    assert snapshot(c) == before and c.reporting.account_balance(bank.id) == 20


@pytest.mark.parametrize('kind', ['BANK', 'BROKERAGE'])
def test_conversion_cannot_create_unfunded_cash(c, ledger, kind):
    source = c.account_flows.open_account('Empty source', kind, '2026-09-01', '0')
    c.currencies.register('USD')
    target = c.account_flows.open_account('USD bank', 'BANK', '2026-09-01', '0', currency='USD')
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.transactions.record_conversion('2026-09-02', source.id, target.id, '500', '10')
    assert snapshot(c) == before
    assert c.db.scalar("SELECT COUNT(*) FROM fx_rates WHERE source='TRADE'") == 0


def test_restoring_buy_cannot_borrow_brokerage_cash(c, ledger):
    broker = c.account_flows.open_account('Broker', 'BROKERAGE', '2026-09-01', '100')
    asset = c.assets.create_investment('Stock', 'STOCK', 'CASHGUARD')
    buy = c.investments.buy('2026-09-02', broker.id, asset.id, '1', '80')
    c.transactions.void(buy.id)
    c.investments.buy('2026-09-03', broker.id, asset.id, '1', '70')
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.transactions.restore(buy.id)
    assert snapshot(c) == before and c.investments.holding(broker.id, asset.id) == 1


@pytest.mark.parametrize('operation', ['edit', 'void', 'delete'])
def test_old_owners_holdings_are_checked_even_when_pooled_units_stay_positive(c, ledger, operation):
    _, _, _, salary = ledger
    broker = c.account_flows.open_account('Broker', 'BROKERAGE', '2026-09-01', '200')
    owner = c.counterparties.ensure_person('Alice')
    c.transactions.record_inflow('2026-09-01', broker.id, '200', salary, owner_id=owner)
    asset = c.assets.create_investment('Stock', 'STOCK', 'OWNERGUARD')
    buy = c.investments.buy('2026-09-02', broker.id, asset.id, '1', '50', owner_id=owner)
    c.investments.buy('2026-09-02', broker.id, asset.id, '1', '50')
    c.investments.sell('2026-09-03', broker.id, asset.id, '1', '50', owner_id=owner)
    before = snapshot(c)
    with pytest.raises(ValidationError):
        if operation == 'edit':
            c.investments.update(buy.id, account_id=broker.id, asset_id=asset.id,
                                 quantity='1', price='50', owner_id=None)
        elif operation == 'void':
            c.transactions.void(buy.id)
        else:
            c.transactions.delete_many([buy.id])
    assert snapshot(c) == before
    assert c.investments.holding_for_owner(broker.id, asset.id, '2026-09-04', owner) == 0


def test_owner_change_also_checks_the_old_date_when_moved_later(c, ledger):
    bank, _, food, _ = ledger
    alice = c.counterparties.ensure_person('Alice')
    bob = c.counterparties.ensure_person('Bob')
    txn = c.transactions.change_cash_ownership('2026-09-02', bank.id, '100', None, alice)
    c.transactions.record_outflow('2026-09-03', bank.id, '90', food, owner_id=alice)
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.transactions.change_cash_ownership('2026-09-10', bank.id, '100', None, bob, txn_id=txn.id)
    assert snapshot(c) == before


def test_bulk_delete_checks_the_final_batch_not_each_intermediate_step(c, ledger):
    bank, _, food, salary = ledger
    income = c.transactions.record_inflow('2026-09-02', bank.id, '100', salary)
    expense = c.transactions.record_outflow('2026-09-03', bank.id, '150', food)
    assert c.transactions.delete_many([income.id, expense.id]) == 2
    assert c.reporting.account_balance(bank.id) == 100


def test_imported_deficit_allows_metadata_and_repair_but_no_worse_day(c, ledger):
    bank, _, food, salary = ledger
    txn = c.transactions.record_outflow('2026-09-02', bank.id, '150', food, source=TxnSource.IMPORT)
    c.transactions.update_money(txn.id, txn.date, bank.id, '150', food, notes='statement history')
    with pytest.raises(ValidationError):
        c.transactions.update_money(txn.id, txn.date, bank.id, '160', food)
    c.transactions.record_inflow('2026-09-04', bank.id, '100', salary)
    c.transactions.record_outflow('2026-09-05', bank.id, '100', food, source=TxnSource.IMPORT)
    # The existing minimum stays -50, but -10 on Sep 4 would still be a new deficit.
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.transactions.record_outflow('2026-09-04', bank.id, '60', food)
    assert snapshot(c) == before
    c.transactions.record_inflow('2026-09-03', bank.id, '50', salary)
    assert c.reporting.account_balance(bank.id) == 0


@pytest.mark.parametrize('redo', [False, True])
def test_history_cannot_remove_funding_or_restore_unaffordable_spending(c, ledger, redo):
    bank, _, food, salary = ledger
    if redo:
        with user_action('Expense'):
            c.transactions.record_outflow('2026-09-02', bank.id, '80', food)
        c.undo.replay()
        c.transactions.record_outflow('2026-09-03', bank.id, '70', food)
    else:
        with user_action('Income'):
            c.transactions.record_inflow('2026-09-02', bank.id, '100', salary)
        c.transactions.record_outflow('2026-09-03', bank.id, '150', food)
    before = snapshot(c)
    with pytest.raises(ValidationError):
        c.undo.replay(redo=redo)
    assert snapshot(c) == before


def test_history_can_reverse_metadata_over_an_imported_deficit(c, ledger):
    bank, _, food, _ = ledger
    txn = c.transactions.record_outflow('2026-09-02', bank.id, '150', food, source=TxnSource.IMPORT)
    with user_action('Correct note'):
        c.transactions.update_money(txn.id, txn.date, bank.id, '150', food, notes='correct note')
    c.undo.replay()
    assert c.transactions.get(txn.id).notes == ''
    assert c.reporting.account_balance(bank.id) == -50
