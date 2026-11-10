"""Two statements back one explicit conversion with exact native legs, never an inferred rate."""
from decimal import Decimal as D
import pytest
from fastapi.testclient import TestClient
from lightning.core.errors import ConflictError
from lightning.database.currencies import CurrencyRegistry
from lightning.ui.web import create_app


def accounts(c):
    CurrencyRegistry(c.db).register('USD')
    c.fx.save('USD', '2026-09-01', '50')
    return (c.account_flows.open_account('Pounds', 'BANK', '2026-09-01', '10000'),
            c.account_flows.open_account('Dollars', 'BANK', '2026-09-01', '0', currency='USD'))


def stage(c, account, day, amount, party):
    batch, _ = c.bank_imports.stage(account.id, f'{party}.csv', f'Date,Amount,Counterparty\n{day},{amount},{party}\n'.encode())
    return batch, c.bank_imports.preview(batch)[1][0]


def test_pair_with_fee_and_settlement_delay_posts_conversion_once_then_links(c):
    a, b = accounts(c)
    batch, row = stage(c, a, '2026-09-02', '-5010', 'Dollars')
    decision = {'match': 'new', 'transfer_account_id': str(b.id), 'conversion_amount': '100', 'fee': '10'}
    result = c.bank_imports.confirm(batch, {row['_import_row_id']: decision})
    assert not result['errors'] and result['posted'] == 1
    txn_id = c.db.scalar('SELECT transaction_id FROM bank_import_rows WHERE id=?', (row['_import_row_id'],))
    assert c.transactions.get(txn_id).type == 'CNV'
    assert c.reporting.account_balance(a.id) == 4990 and c.reporting.account_balance(b.id) == 100
    other_batch, other = stage(c, b, '2026-09-03', '100', 'Pounds')
    candidate, = other['_link_candidates']
    assert candidate['id'] == txn_id and 'USD' in candidate['conversion'] and 'EGP' in candidate['conversion']
    before = c.db.scalar('SELECT COUNT(*) FROM transactions')
    result = c.bank_imports.confirm(other_batch, {other['_import_row_id']: {'match': f'link:{txn_id}'}})
    assert result['linked'] == 1 and not result['errors']
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == before
    with pytest.raises(ConflictError):
        c.bank_imports.confirm(other_batch, {other['_import_row_id']: {'match': f'link:{txn_id}'}})
    assert c.reporting.account_balance(a.id) == 4990 and c.reporting.account_balance(b.id) == 100


def test_no_implicit_rate_and_exact_native_amount_required(c):
    a, b = accounts(c)
    batch, row = stage(c, a, '2026-09-02', '-5000', 'Dollars')
    rid = row['_import_row_id']
    for value in ('', '0', '-100', 'bad'):
        result = c.bank_imports.confirm(batch, {rid: {'match':'new', 'conversion_amount':value}})
        assert rid in result['errors']
        assert c.reporting.account_balance(a.id) == 10000 and c.reporting.account_balance(b.id) == 0
    assert not c.bank_imports.confirm(batch, {rid:{'match':'new', 'conversion_amount':'99'}})['errors']
    _, wrong = stage(c, b, '2026-09-03', '100', 'Pounds')
    assert not wrong['_link_candidates']


def test_incoming_statement_can_be_first_and_voided_conversion_cannot_link(c):
    a, b = accounts(c)
    batch, row = stage(c, b, '2026-09-02', '100', 'Pounds')
    assert not c.bank_imports.confirm(batch, {row['_import_row_id']:{'match':'new', 'conversion_amount':'5000'}})['errors']
    txn_id = c.db.scalar('SELECT transaction_id FROM bank_import_rows WHERE id=?', (row['_import_row_id'],))
    c.transactions.void(txn_id)
    _, other = stage(c, a, '2026-09-02', '-5000', 'Dollars')
    assert not other['_link_candidates']


@pytest.mark.parametrize('phone', [False, True])
def test_review_shows_currency_amount_field_and_retains_value_on_refusal(c, phone):
    a, b = accounts(c)
    batch, row = stage(c, a, '2026-09-02', '-5000', 'Dollars')
    app = create_app(c)
    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    with TestClient(app) as client:
        page = client.get(f'/accounts/{a.id}/import/{batch}?rows=all')
        assert page.status_code == 200 and f'name="conversion_amount_{row["_import_row_id"]}"' in page.text
        assert 'Other account amount' in page.text


def test_an_explicit_counterparty_with_an_account_name_is_an_expense_not_a_transfer(c):
    a=c.account_flows.open_account('Bank','BANK','2026-09-01','1000')
    wallet=c.account_flows.open_account('Wallet','CASH','2026-09-01','0')
    party=c.counterparties.create('Wallet')
    food=c.categories.get_by_code('EXP.PERSONAL.FOOD')
    batch,row=stage(c,a,'2026-09-02','-10','Wallet')
    rid=row['_import_row_id']
    assert row['_identity_ambiguous'] and not row['_ready']
    refused=c.bank_imports.confirm(batch,{rid:{'match':'new','category_id':food.id}})
    assert rid in refused['errors'] and c.reporting.account_balance(a.id)==1000
    result=c.bank_imports.confirm(batch,{rid:{'match':'new','category_id':food.id,'counterparty_choice':f'existing:{party}'}})
    assert not result['errors']
    txn=c.transactions.get(c.db.scalar('SELECT transaction_id FROM bank_import_rows WHERE id=?',(rid,)))
    assert txn.type=='OUT' and c.reporting.account_balance(a.id)==990 and c.reporting.account_balance(wallet.id)==0


def test_legacy_duplicate_account_names_are_resolved_by_the_explicit_id(c):
    a,b=accounts(c)
    other=c.account_flows.open_account('Other dollars','BANK','2026-09-01','0')
    # Older/imported profiles may contain names current account forms refuse.
    c.db.execute('UPDATE accounts SET name=? WHERE id=?',('Dollars',other.id))
    batch,row=stage(c,a,'2026-09-02','-5000','Dollars')
    assert row['_identity_ambiguous'] and not row['_ready']
    result=c.bank_imports.confirm(batch,{row['_import_row_id']:{'match':'new','transfer_account_id':str(b.id),'conversion_amount':'100'}})
    assert not result['errors'] and c.reporting.account_balance(b.id)==100
