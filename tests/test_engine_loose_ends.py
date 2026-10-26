"""Engine audit 2026-10-26: the shared writer checks master data (2I), instalment inputs fit the currency (2L),
and every financial edit form carries a revision (2M)."""
import re
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine
from lightning.core.refs import DocType
from lightning.planning.loan_actions import create_purchase, purchase_quote
from lightning.ui.web import create_app


def snapshot(c):
    return [tuple(row) for table in ('transactions', 'ledger_entries')
            for row in c.db.all(f'SELECT * FROM {table} ORDER BY id')]


@pytest.fixture
def usd(c):
    c.currencies.register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-09-01', '100')
    dollars = c.account_flows.open_account('Dollars', 'BANK', '2026-09-01', '0', currency='USD')
    return bank, dollars, c.categories.get_by_code('EXP.WORK.SALARY').id


# -- 2I: the shared posting boundary ------------------------------------------------------------

def test_post_refuses_cash_in_another_currencys_account(c, usd):
    bank, _, salary = usd
    line = PostingLine.cash(bank.id, c.assets.cash_asset('USD').id, D('10'), Effect.INFLOW, salary, fx_rate=D('50'))
    before = snapshot(c)
    with pytest.raises(ValidationError, match='holds EGP, not USD'):
        c.transactions.post(DocType.IN, '2026-09-02', [line])
    assert snapshot(c) == before
    assert c.reporting.account_balance(bank.id) == 100


@pytest.mark.parametrize('rate', ['0.5', '2'])
def test_post_refuses_profile_currency_cash_at_another_rate(c, usd, rate):
    bank, _, salary = usd
    line = PostingLine.cash(bank.id, c.assets.cash_asset('EGP').id, D('0.01'), Effect.INFLOW, salary, fx_rate=D(rate))
    with pytest.raises(ValidationError, match='rate of 1'):
        c.transactions.post(DocType.IN, '2026-09-02', [line])


def test_post_refuses_an_investment_posted_as_cash(c, usd):
    bank, _, salary = usd
    stock = c.assets.create_investment('Test company', 'STOCK', 'TEST')
    line = PostingLine.cash(bank.id, stock.id, D('10'), Effect.INFLOW, salary)
    with pytest.raises(ValidationError, match='is not cash'):
        c.transactions.post(DocType.IN, '2026-09-02', [line])


def test_repost_applies_the_same_check(c, usd):
    bank, _, salary = usd
    txn = c.transactions.record_inflow('2026-09-02', bank.id, '10', salary)
    line = PostingLine.cash(bank.id, c.assets.cash_asset('USD').id, D('10'), Effect.INFLOW, salary, fx_rate=D('50'))
    with pytest.raises(ValidationError, match='holds EGP, not USD'):
        c.transactions.repost(txn.id, txn.date, [line])
    assert c.transactions.get(txn.id).lines == txn.lines


def test_foreign_cash_keeps_its_conversion_rate(c, usd):
    _, dollars, salary = usd
    line = PostingLine.cash(dollars.id, c.assets.cash_asset('USD').id, D('10'), Effect.INFLOW, salary, fx_rate=D('50'))
    txn = c.transactions.post(DocType.IN, '2026-09-02', [line])
    assert txn.lines[0].amount_base == D('500.00')
    assert c.reporting.account_balance(dollars.id) == 10


# -- 2L: instalment inputs ----------------------------------------------------------------------

@pytest.mark.parametrize('price, fee', [('100.001', '0'), ('100', '0.005')])
def test_purchase_refuses_sub_cent_price_or_fee(c, price, fee):
    with pytest.raises(ValidationError, match='at most 2 decimal places'):
        purchase_quote(price, fee, 2, '2026-10-01')
    with pytest.raises(ValidationError):
        create_purchase(c.planning, name='Phone', price=price, fee=fee, months=2, first_date='2026-10-01')
    assert c.db.scalar('SELECT COUNT(*) FROM planned_items') == 0


def test_every_instalment_is_payable_and_sums_to_the_total(c):
    quote = purchase_quote('100.01', '0.02', 3, '2026-10-01')
    parts = [quote['monthly']] * 2 + [quote['final']]
    assert sum(parts) == quote['total'] == D('100.03')
    assert all(part == part.quantize(D('0.01')) and part > 0 for part in parts)


# -- 2M: the last three edit forms -------------------------------------------------------------

def token(page):
    match = re.search(r'name="revision" value="([a-f0-9]{64})"', page.text)
    assert page.status_code == 200 and match, page.text[:300]
    return match.group(1)


def conversion(c, usd):
    bank, dollars, _ = usd
    txn = c.transactions.record_conversion('2026-09-02', bank.id, dollars.id, '50', '1')
    return txn, f'/transactions/{txn.id}/convert/edit', dict(
        date='2026-09-02', from_account_id=str(bank.id), to_account_id=str(dollars.id),
        sent='50', received='1', fee='', notes='my unsaved note')


def ownership(c, usd):
    bank = usd[0]
    alice = c.counterparties.ensure_person('Alice')
    txn = c.transactions.change_cash_ownership('2026-09-02', bank.id, '40', None, alice)
    return txn, f'/transactions/{txn.id}/ownership/edit', dict(
        mode='assign', date='2026-09-02', amount='40', from_owner_id='', to_owner_id=str(alice),
        category_id='', notes='my unsaved note')


def investment(c, usd):
    broker = c.account_flows.open_account('THNDR', 'BROKERAGE', '2026-09-01', '5000')
    stock = c.assets.create_investment('Test company', 'STOCK', 'TEST')
    txn = c.investments.buy('2026-09-02', broker.id, stock.id, '10', '100')
    return txn, f'/investments/{txn.id}/edit', dict(
        date='2026-09-02', account_id=str(broker.id), asset_id=str(stock.id), quantity='10', price='100',
        fees='0', fees_included='1', cash_account_id=str(broker.id), notes='my unsaved note')


@pytest.mark.parametrize('build', [conversion, ownership, investment])
def test_stale_edit_form_is_refused_and_a_fresh_one_saves(c, usd, build):
    txn, path, values = build(c, usd)
    with TestClient(create_app(c)) as client:
        stale = token(client.get(path))
        # Another window saves first; any change to the header or lines makes the open form stale.
        c.db.execute("UPDATE transactions SET notes='newer note' WHERE id=?", (txn.id,))
        current = c.transactions.get(txn.id)
        response = client.post(path, data=values | dict(revision=stale), follow_redirects=False)
        assert response.status_code == 400 and 'changed since you opened' in response.text
        assert 'my unsaved note' in response.text
        assert c.transactions.get(txn.id) == current
        fresh = token(client.get(path))
        assert client.post(path, data=values | dict(revision=fresh), follow_redirects=False).status_code == 303
    assert c.transactions.get(txn.id).notes == 'my unsaved note'


# -- 2J: one save per submitted form -------------------------------------------------------------

def submission(page):
    match = re.search(r'name="submission" value="([a-f0-9]{32})"', page.text)
    assert page.status_code == 200 and match, page.text[:300]
    return match.group(1)


def entries(c, account_id):
    return c.db.scalar("SELECT COUNT(*) FROM transactions t JOIN ledger_entries e ON e.transaction_id=t.id "
                       "WHERE t.status!='VOID' AND e.account_id=? AND t.type='OUT'", (account_id,))


@pytest.mark.parametrize('screen', ['register', 'all accounts', 'popup'])
def test_a_resent_add_form_saves_once(c, setup, screen):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    get_path, post_path, values = {
        'register': (f'/accounts/{bank.id}', f'/accounts/{bank.id}/register',
                     dict(date='2026-09-02', amount='-10', category=food.name, notes='lunch')),
        'all accounts': ('/transactions', '/transactions/register',
                         dict(date='2026-09-02', amount='-10', category=food.name, notes='lunch', account_id=str(bank.id))),
        'popup': (f'/accounts/{bank.id}/transaction/new', f'/accounts/{bank.id}/transaction/new',
                  dict(kind='out', date='2026-09-02', amount='10', category_id=str(food.id), notes='lunch')),
    }[screen]
    with TestClient(create_app(c)) as client:
        values['submission'] = submission(client.get(get_path))
        first = client.post(post_path, data=values, follow_redirects=False)
        again = client.post(post_path, data=values, follow_redirects=False)
        assert first.status_code == again.status_code == 303, first.text[:300]
        assert entries(c, bank.id) == 1
        assert c.reporting.account_balance(bank.id) == D('49990')
        # The same token with different values is a new action on an old form: refused, nothing saved.
        changed = client.post(post_path, data=values | dict(amount='-20' if screen != 'popup' else '20'))
        assert changed.status_code == 400 and 'already saved' in changed.text
        assert entries(c, bank.id) == 1
        # A fresh form adds a legitimate identical expense.
        values['submission'] = submission(client.get(get_path))
        assert client.post(post_path, data=values, follow_redirects=False).status_code == 303
    assert entries(c, bank.id) == 2


def test_a_form_without_a_token_keeps_the_old_contract(c, setup):
    bank, food = setup[0]['cib'], setup[1]['EXP.PERSONAL.FOOD']
    values = dict(date='2026-09-02', amount='-10', category=food.name)
    with TestClient(create_app(c)) as client:
        for _ in range(2):
            assert client.post(f'/accounts/{bank.id}/register', data=values, follow_redirects=False).status_code == 303
    assert entries(c, bank.id) == 2


# -- write paths around the ledger (audit 2026-10-26, B1-B6) --------------------------------------------------

from lightning.core.errors import ConflictError  # noqa: E402


@pytest.fixture
def cd(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '100000', institution='CIB')
    payout = c.account_flows.open_account('Payout', 'BANK', '2026-01-01', '0', institution='CIB')
    portfolio = c.account_flows.open_account('CIB CDs', 'DEPOSIT', '2026-01-01', '0', institution='CIB')
    cert, _ = c.deposits.purchase(portfolio.id, 'CD1', '2026-02-01', '2026-03-01', '2027-02-01', '50000', '20',
                                  'SIMPLE', 'MONTHLY', 'MONTHLY', payout.id, bank.id)
    return bank, payout, cert.terms.id


def test_a_voided_redemption_lets_the_certificate_be_redeemed_again(c, cd):
    bank, _, cid = cd
    first = c.deposits.redeem(cid, '2026-04-01', '51000', bank.id)
    c.transactions.void(first.id)
    c.deposits.redeem(cid, '2026-05-01', '52000', bank.id)
    assert c.deposits.certificate(cid).redeemed
    with pytest.raises(ValidationError, match='less than zero'):
        c.transactions.restore(first.id)
    assert c.reporting.account_balance(bank.id) == D('102000')


def test_an_account_a_live_certificate_pays_into_stays_active(c, cd):
    _, payout, cid = cd
    with pytest.raises(ConflictError, match='the certificate CD1'):
        c.account_flows.deactivate(payout.id)
    assert c.accounts.get(payout.id).active


def test_restoring_an_expense_cannot_overspend_its_reserve(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-09-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    reserve = c.reserves.create('Trip', '500', due_date='2026-12-30')
    c.reserves.allocate(reserve['id'], '300')
    first = c.transactions.record_outflow('2026-09-02', bank.id, '200', food)
    c.reserves.set_expense_link(reserve['id'], first.id, '200')
    c.transactions.void(first.id)
    second = c.transactions.record_outflow('2026-09-03', bank.id, '300', food)
    c.reserves.set_expense_link(reserve['id'], second.id, '300')
    with pytest.raises(ValidationError, match='more from the reserve Trip'):
        c.transactions.restore(first.id)
    assert c.reserves.get(reserve['id'])['spent'] == 300


@pytest.mark.parametrize('user', ['plan', 'reserve'])
def test_a_category_a_plan_or_reserve_uses_is_archived_not_a_crash(c, user):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    created = c.categories.create(food.id, 'Gym')
    category = getattr(created, 'id', created)
    if user == 'plan':
        c.planning.create(kind='BILL', name='Gym fee', amount='300', frequency='MONTHLY', start_date='2027-01-05',
                          category_id=category, account_id=bank.id)
    else:
        c.reserves.create('Gym fund', '100', category_id=category)
    assert c.categories.delete_or_archive(category) is True
    assert not c.categories.get(category).active


def test_a_claim_payer_is_archived_not_silently_removed(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    boss = c.counterparties.create('Boss')
    claim = c.reimbursements.create_claim(c.transactions.record_outflow('2026-09-02', bank.id, '200', food).id,
                                          '200', payer_id=boss)
    assert c.counterparties.delete_or_archive(boss) is True
    assert c.db.scalar('SELECT payer_id FROM reimbursement_claims WHERE id=?', (claim['id'],)) == boss


def test_a_circle_pays_out_once_and_takes_one_instalment_per_member(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '100000')
    circle = c.account_flows.open_account('Circle', 'GAMEYA', '2026-01-01', '0')
    c.gameya.save_terms(circle.id, organiser='Aunt', members=3, installment='1000', first_date='2026-02-01',
                        my_turn=1, funding_account_id=bank.id, payout_account_id=bank.id)
    first = c.gameya.record_payout(circle.id, '2026-02-01')
    c.transactions.void(first.id)
    c.gameya.record_payout(circle.id, '2026-02-02')
    with pytest.raises(ValidationError, match='already paid you its pot'):
        c.transactions.restore(first.id)
    for month in range(3):
        c.gameya.record_instalment(circle.id, f'2026-0{2 + month}-01')
    with pytest.raises(ValidationError, match='all its instalments are recorded'):
        c.transactions.record_transfer('2026-06-01', bank.id, circle.id, '1000')
    progress = c.gameya.progress(circle.id)
    assert (progress.paid, progress.payouts) == (3, 1)


@pytest.mark.parametrize('field', ['expected', 'receipt'])
def test_reimbursement_amounts_use_whole_cents(c, field):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '1000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    expense = c.transactions.record_outflow('2026-09-02', bank.id, '200', food)
    with pytest.raises(ValidationError, match='decimal places'):
        if field == 'expected':
            c.reimbursements.create_claim(expense.id, '10.0001')
        else:
            claim = c.reimbursements.create_claim(expense.id, '200')
            receipt = c.transactions.record_inflow('2026-09-05', bank.id, '200',
                                                   c.categories.get_by_code('EXP.WORK.SALARY').id)
            c.reimbursements.link_receipt(claim['id'], receipt.id, '200.005')


# -- loans, schedules, investment edits and onboarding (audit 2026-10-26, C1-C5) ------------------------------

from datetime import date  # noqa: E402

from lightning.planning.loan_actions import preview_early_payment, record_early_payment  # noqa: E402
from lightning.planning.schedule import payment_dates  # noqa: E402


@pytest.fixture
def loan(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '50000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    item = c.planning.create(kind='LOAN', name='Car', amount='100', payment_count='3', principal='300',
                             start_date='2026-09-02', account_id=bank.id, category_id=food.id)
    return bank, item


def test_a_backdated_early_payment_cannot_pay_a_settled_loan_twice(c, loan):
    bank, item = loan
    preview = preview_early_payment(c.planning, item, '300', '0', '2026-08-20')
    record_early_payment(c.planning, item, '300', '0', '2026-08-20', bank.id, preview['remaining_before'])
    with pytest.raises(ValidationError, match='no more than the remaining loan'):
        preview_early_payment(c.planning, item, '300', '0', '2026-08-10')
    assert c.reporting.account_balance(bank.id) == D('49700')


def test_an_instalment_cannot_take_more_than_it_owes(c, loan):
    bank, item = loan
    with pytest.raises(ValidationError, match="remaining amount"):
        c.planning.record_payment(item, '2026-09-02', '2026-09-02', '250', bank.id)
    assert c.reporting.account_balance(bank.id) == D('50000')
    c.planning.record_payment(item, '2026-09-02', '2026-09-02', '100', bank.id)
    assert c.planning.loan_progress(c.planning.get(item))['still_to_pay'] == D('200')


@pytest.mark.parametrize('start, weekend, as_of, expected', [
    ('2026-07-31', 'none', date(2026, 8, 15), ['2026-08-31', '2026-09-30', '2026-10-31', '2026-11-30', '2026-12-31']),
    ('2026-06-04', 'after', date(2026, 6, 20), ['2026-07-05', '2026-08-04', '2026-09-06', '2026-10-04', '2026-11-04']),
])
def test_already_paid_keeps_the_bills_day(c, start, weekend, as_of, expected):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '50000')
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    item = c.planning.create(kind='BILL', name='Rent', amount='100', frequency='MONTHLY', weekend_move=weekend,
                             start_date=start, account_id=bank.id, category_id=food.id)
    assert c.planning.start_after_paid(item, as_of) == expected[0]
    assert [due for _, due in payment_dates(c.planning.get(item), '2026-11-30')] == [
        due for due in expected if due <= '2026-11-30']


def test_editing_a_brokerage_buy_cannot_pay_from_another_account(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '50000')
    broker = c.account_flows.open_account('THNDR', 'BROKERAGE', '2026-01-01', '0')
    stock = c.assets.create_investment('Commercial International Bank', 'STOCK', 'COMI')
    c.transactions.record_transfer('2026-02-01', bank.id, broker.id, '10000')
    buy = c.investments.buy('2026-02-02', broker.id, stock.id, '10', '100')
    values = c.investments.values_of(buy.id)
    values.pop('kind')
    with pytest.raises(ValidationError, match='cash already in that brokerage'):
        c.investments.update(buy.id, **(values | dict(cash_account_id=bank.id)))
    assert c.reporting.account_balance(broker.id) == D('9000')


def test_workbook_onboarding_refuses_a_future_transaction(c, tmp_path):
    from lightning.reporting.xlsx import tabular_workbook_bytes
    from lightning.workflows.data_export import _raw_tables
    from lightning.workflows.workbook_import import confirm_import
    from lightning.bootstrap import build

    bank = c.account_flows.open_account('Example bank', 'BANK', '2026-01-01', '1000')
    txn = c.transactions.record_outflow('2026-02-01', bank.id, '12.34', c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    sheets = []
    for name, headers, rows, widths in _raw_tables(c):
        key = 'id' if name == 'transactions' else 'transaction_id' if name == 'ledger_entries' else None
        if key:
            rows = [tuple('2099-01-01' if column == 'date' and row[headers.index(key)] == txn.id else value
                          for column, value in zip(headers, row)) for row in rows]
        sheets.append((name[:31], headers, rows, widths))
    target = build(tmp_path / 'new.db')
    with pytest.raises(ValueError, match='dated in the future'):
        confirm_import(target, tabular_workbook_bytes(sheets))
    assert target.db.scalar('SELECT count(*) FROM transactions') == 0


# -- integrity checks and valuation (audit 2026-10-26, A1-A3) -------------------------------------------------

def checks_by_name(c, day):
    return {check.name: check for check in c.integrity.checks(day)}


def test_investment_fees_do_not_raise_a_budget_issue(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-09-01', '1000')
    c.transactions.record_outflow('2026-09-02', bank.id, '100', c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    c.transactions.record_outflow('2026-09-03', bank.id, '40', c.categories.get_by_code('EXP.INVEST.FEES').id)
    assert checks_by_name(c, '2026-09-30')['Budget actual equals categorized spending'].status == 'PASS'


def test_profile_currency_cash_off_its_face_value_is_an_issue(c):
    bank = c.account_flows.open_account('Bank', 'BANK', '2026-09-01', '1000')
    expense = c.transactions.record_outflow('2026-09-02', bank.id, '100',
                                            c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    assert checks_by_name(c, '2026-09-30')['Profile-currency cash moves at face value'].status == 'PASS'
    c.db.execute('UPDATE ledger_entries SET amount_base_e6=amount_base_e6*10 WHERE transaction_id=?', (expense.id,))
    check = checks_by_name(c, '2026-09-30')['Profile-currency cash moves at face value']
    assert check.status == 'ISSUE' and check.actual == D('900')


def test_an_estimate_keeps_counting_money_moved_after_it(c):
    c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '500000')
    flat = c.account_flows.open_account('Flat', 'OTHER_ASSET', '2026-01-01', '1000000')
    c.reporting.other_asset_values.save(c.accounts.get(flat.id), '2026-02-01', '1200000')
    assert c.reporting.net_worth('2026-02-28').total == D('1700000')
    c.transactions.record_outflow('2026-03-05', flat.id, '100000', c.categories.get_by_code('EXP.PERSONAL.FOOD').id)
    assert c.reporting.net_worth('2026-03-31').total == D('1600000')
