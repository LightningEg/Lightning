"""2Y: converted monetary values must fit SQLite before integer binding."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.core.money import from_e6, to_e6
from lightning.ui.web import create_app


@pytest.mark.parametrize('scaled', [-(2**63), 2**63-1, 0])
def test_storage_limits_roundtrip_exactly(scaled):
    assert to_e6(from_e6(scaled))==scaled


@pytest.mark.parametrize('value', ['9223372036854.775808','-9223372036854.775809','1e100','NaN','Infinity'])
def test_out_of_range_values_raise_a_financial_validation_error(value):
    with pytest.raises(ValidationError):
        to_e6(Decimal(value))


def foreign(c):
    c.currencies.register('USD')
    c.fx.save('USD','2026-09-01','50')
    account=c.account_flows.open_account('USD','BANK','2026-09-01','0',currency='USD')
    return account,c.categories.get_by_code('EXP.WORK.SALARY').id


def test_large_foreign_income_rolls_back_its_header_and_counterparty(c):
    account,salary=foreign(c)
    before=c.db.scalar('SELECT COUNT(*) FROM transactions')
    with pytest.raises(ValidationError,match='too large'):
        c.transactions.record_inflow('2026-09-02',account.id,'999999999999.99',salary,counterparty='Must roll back')
    assert c.db.scalar('SELECT COUNT(*) FROM transactions')==before
    assert c.db.scalar("SELECT COUNT(*) FROM counterparties WHERE name='Must roll back'")==0
    assert c.reporting.account_balance(account.id)==0


def test_register_renders_an_error_instead_of_http_500(c):
    account,salary=foreign(c)
    response=TestClient(create_app(c)).post(f'/accounts/{account.id}/register',data={
        'date':'2026-09-02','amount':'999999999999.99','category_choice':salary},follow_redirects=False)
    assert response.status_code==400
    assert 'too large' in response.text
    assert c.reporting.account_balance(account.id)==0


def test_overflow_on_edit_preserves_original_posting(c):
    account,salary=foreign(c)
    txn=c.transactions.record_inflow('2026-09-02',account.id,'10',salary)
    before=c.transactions.get(txn.id)
    with pytest.raises(ValidationError,match='too large'):
        c.transactions.update_money(txn.id,'2026-09-02',account.id,'999999999999.99',salary)
    assert c.transactions.get(txn.id)==before
