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
