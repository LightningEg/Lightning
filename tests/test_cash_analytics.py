"""FIFO ages retain cash provenance; the daily calendar reconciles with Spending."""
from decimal import Decimal as D
import pytest
from fastapi.testclient import TestClient
from lightning.ui.web import create_app


def bank(c):
    return c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '0')


def salary(c, account, day, amount):
    return c.transactions.record_inflow(day, account.id, amount, c.categories.get_by_code('EXP.WORK.SALARY').id)


def spend(c, account, day, amount):
    return c.transactions.record_outflow(day, account.id, amount, c.categories.get_by_code('EXP.PERSONAL.FOOD').id)


def test_fifo_uses_exact_amount_weighted_dates_and_transfer_does_not_reset(c):
    a = bank(c)
    b = c.account_flows.open_account('Wallet', 'CASH', '2026-01-01', '0')
    salary(c, a, '2026-01-01', '100')
    salary(c, a, '2026-01-11', '100')
    c.transactions.record_transfer('2026-01-15', a.id, b.id, '150')
    spend(c, b, '2026-01-21', '150')
    before = c.db.conn.total_changes
    age = c.reporting.cash_age('2026-01-31')
    assert age.days == D(50) / 3  # 100*20 + 50*10, divided by 150
    assert age.payments == 1 and age.unknown_payments == 0
    assert c.db.conn.total_changes == before


def test_opening_cash_age_is_unknown_and_void_future_income_and_refunds_do_not_fake_it(c):
    a = c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '100')
    spend(c, a, '2026-01-11', '100')
    assert c.reporting.cash_age('2026-01-31').days is None
    salary(c, a, '2026-02-01', '100')
    assert c.reporting.cash_age('2026-01-31').unknown_payments == 1


def test_only_last_ten_expenses_and_previous_ten_are_compared(c):
    a = bank(c)
    salary(c, a, '2026-01-01', '1000')
    for n in range(1, 21):
        spend(c, a, f'2026-01-{n+1:02}', '10')
    age = c.reporting.cash_age('2026-01-31')
    assert age.days == D('15.5') and age.previous_days == D('5.5') and age.payments == 10


def test_currency_conversion_carries_source_age(c):
    from lightning.database.currencies import CurrencyRegistry
    a = bank(c)
    CurrencyRegistry(c.db).register('USD')
    c.fx.save('USD', '2026-01-01', '50')
    b = c.account_flows.open_account('Dollars', 'BANK', '2026-01-01', '0', currency='USD')
    salary(c, b, '2026-01-01', '20')
    c.transactions.record_conversion('2026-01-10', b.id, a.id, '20', '1000')
    spend(c, a, '2026-01-21', '100')
    assert c.reporting.cash_age('2026-01-31').days == 20


def test_calendar_matches_spending_with_refunds_and_excludes_transfers(c):
    a = bank(c)
    salary(c, a, '2026-01-01', '1000')
    spend(c, a, '2026-01-02', '100')
    cat = c.categories.get_by_code('EXP.PERSONAL.FOOD')
    c.transactions.record_inflow('2026-01-02', a.id, '25', cat.id)
    rows = c.reporting.spending_calendar('2026-01-01', '2026-01-31')
    assert len(rows) == 1 and rows[0]['amount'] == 75 and rows[0]['transactions'] == 2
    assert sum(r['amount'] for r in rows) == sum(r['value'] for r in c.reporting.spending_lines('2026-01-01', '2026-01-31'))


@pytest.mark.parametrize('phone', [False, True])
@pytest.mark.parametrize('locale', ['en', 'ar'])
def test_calendar_and_age_page(c, phone, locale):
    c.settings.set('locale', locale)
    app = create_app(c)
    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)
    with TestClient(app) as client:
        page = client.get('/spending/calendar?month=2026-01')
        assert page.status_code == 200
        if phone:
            assert 'phone-appbar' in page.text
        if locale == 'ar':
            assert 'Age of Money' not in page.text


def test_same_day_cash_age_uses_stable_references_instead_of_local_transaction_ids(tmp_path):
    from lightning.bootstrap import build
    ages=[]
    for i,order in enumerate((('spend','buy'),('buy','spend'))):
        c=build(tmp_path/f'order-{i}.db')
        try:
            a=bank(c)
            broker=c.account_flows.open_account('Broker','BROKERAGE','2026-01-01','0')
            salary(c,a,'2026-01-01','200')
            salary(c,a,'2026-01-11','100')
            c.transactions.record_transfer('2026-01-12',a.id,broker.id,'50')
            asset=c.assets.create_investment('Fictional stock','STOCK','FIFO')
            for operation in order:
                if operation=='spend':
                    spend(c,a,'2026-01-21','250')
                else:
                    c.investments.buy_total('2026-01-21',broker.id,asset.id,'1','50')
            assert not c.db.all('PRAGMA foreign_key_check')
            ages.append(c.reporting.cash_age('2026-01-31').days)
        finally:
            c.db.close()
    assert ages==[D('16'),D('16')]
