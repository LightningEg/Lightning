"""A settled salary offers a review, without assigning cash or recording a transaction."""
from datetime import date, timedelta

import pytest

from fastapi.testclient import TestClient

from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox


def _salary_item(c, on=date(2026, 12, 31)):
    return next((item for item in ReviewInbox(c).items(on) if item['label'] == 'Salary received'), None)


def test_salary_review_requires_a_real_settlement_and_renews_for_new_salary(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    accounts, cats = setup
    salary = cats['EXP.WORK.SALARY'].id
    item_id = c.planning.create(kind='INCOME', name='Salary', amount='2000', frequency='MONTHLY',
                                start_date='2026-11-30', month_day=30, account_id=accounts['cib'].id,
                                category_id=salary)
    assert _salary_item(c) is None
    txn = c.transactions.record_inflow('2026-11-30', accounts['cib'].id, '2000', salary, counterparty='Employer')
    assert _salary_item(c) is None
    c.planning.mark_paid(item_id, '2026-11-30', txn.id)
    reminder = _salary_item(c)
    c.planning.mark_paid(item_id, '2026-11-30', txn.id)
    assert _salary_item(c)['review_id'] == reminder['review_id']
    assert reminder and reminder['href'] == '/payday'
    count = c.db.scalar('SELECT count(*) FROM transactions')
    before_funding = c.db.scalar('SELECT count(*) FROM cash_funding')
    client = TestClient(create_app(c))
    page = client.get('/payday')
    assert page.status_code == 200 and 'Safe to spend' in page.text and 'Before your next payday' in page.text
    assert 'Your payday proposal' in page.text and 'after you confirm' in page.text
    c.settings.set('locale', 'ar')
    ar = client.get('/payday')
    assert 'قبل المرتب الجاي' in ar.text
    needs_ar = client.get('/needs-you')
    assert 'المرتب وصل' in needs_ar.text
    c.settings.set('locale', 'en')
    assert c.db.scalar('SELECT count(*) FROM transactions') == count
    assert c.db.scalar('SELECT count(*) FROM cash_funding') == before_funding
    ReviewInbox(c).decide(reminder['review_id'], 'snoozed', date(2026, 12, 31), '2027-01-02')
    c.budgets.set_budget(cats['EXP.PERSONAL.FOOD'].id, '2026-12', '500', schedule=c.schedules.view())
    assert _salary_item(c) is None
    assert _salary_item(c, date(2027, 1, 2))['review_id'] == reminder['review_id']
    ReviewInbox(c).decide(reminder['review_id'], 'reviewed', date(2026, 12, 31))
    assert _salary_item(c) is None
    next_txn = c.transactions.record_inflow('2026-12-30', accounts['cib'].id, '2000', salary, counterparty='Employer')
    c.planning.mark_paid(item_id, '2026-12-30', next_txn.id)
    assert _salary_item(c)['review_id'] != reminder['review_id']
    c.transactions.void(next_txn.id, 'Correction')
    assert _salary_item(c) is None


def test_confirming_payday_proposal_handles_salary_without_posting(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    accounts, cats = setup
    salary = cats['EXP.WORK.SALARY'].id
    item_id = c.planning.create(kind='INCOME', name='Salary', amount='2000', frequency='ONCE',
                                start_date='2026-12-31', account_id=accounts['cib'].id, category_id=salary)
    txn = c.transactions.record_inflow('2026-12-31', accounts['cib'].id, '2000', salary, counterparty='Employer')
    c.planning.mark_paid(item_id, '2026-12-31', txn.id)
    c.settings.set('cash_funding_enabled', '1')
    c.budgets.set_budget(cats['EXP.PERSONAL.FOOD'].id, '2026-12', '500', schedule=c.schedules.view())
    preview = c.funding.preview()
    count = c.db.scalar('SELECT count(*) FROM transactions')
    data = {'fingerprint': preview['token']}
    data.update({f"category_{row['id']}": str(row['suggested']) for row in preview['rows']})
    data.update({f"reserve_{row['id']}": str(row['suggested']) for row in preview['reserves']})
    client = TestClient(create_app(c))
    page = client.get('/payday')
    food_row = next(row for row in preview['rows'] if row['id'] == cats['EXP.PERSONAL.FOOD'].id)
    assert f'name="category_{food_row["id"]}" value="{food_row["suggested"]}"' in page.text
    response = client.post('/payday/apply', data=data, follow_redirects=False)
    assert response.status_code == 303
    assert _salary_item(c) is None
    assigned = c.db.scalar('SELECT count(*) FROM cash_funding')
    retry = client.post('/payday/apply', data=data, follow_redirects=False)
    assert retry.status_code in (303, 400)
    assert c.db.scalar('SELECT count(*) FROM cash_funding') == assigned
    assert c.db.scalar('SELECT count(*) FROM transactions') == count


def test_salary_setup_payment_records_once_and_surfaces_review(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    account = setup[0]['cib']
    item_id = c.salary_setup.set_up_salary(account.id, '2000', '31')
    assert _salary_item(c) is None
    before = c.db.scalar('SELECT count(*) FROM transactions')
    c.planning.record_payment(item_id, '2026-12-31', '2026-12-31', '2000', account.id)
    assert c.db.scalar('SELECT count(*) FROM transactions') == before + 1
    assert _salary_item(c)['href'] == '/payday'
    assert c.db.scalar('SELECT count(*) FROM cash_funding') == 0


def test_old_proposal_is_refused_if_a_different_salary_is_settled(c, setup, monkeypatch):
    from lightning.core.errors import ValidationError
    import pytest
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    account, salary = setup[0]['cib'].id, setup[1]['EXP.WORK.SALARY'].id
    first = c.planning.create(kind='INCOME', name='Salary', amount='2000', frequency='ONCE',
                              start_date='2026-12-30', account_id=account, category_id=salary)
    second = c.planning.create(kind='INCOME', name='Other salary', amount='1000', frequency='ONCE',
                               start_date='2026-12-31', account_id=account, category_id=salary)
    txn1 = c.transactions.record_inflow('2026-12-30', account, '2000', salary, counterparty='Employer')
    txn2 = c.transactions.record_inflow('2026-12-31', account, '1000', salary, counterparty='Employer')
    c.settings.set('cash_funding_enabled', '1')
    c.planning.mark_paid(first, '2026-12-30', txn1.id)
    old = c.funding.preview()
    c.planning.mark_paid(second, '2026-12-31', txn2.id)
    assert c.funding.preview()['cash'] == old['cash']
    with pytest.raises(ValidationError, match='changed'):
        c.funding.apply(old['token'], {}, {})
    assert _salary_item(c)['review_state'] == 'active'


def _missing_income(c, on):
    return [item for item in ReviewInbox(c).items(on) if item['label'].endswith(' has not arrived')]


def test_missing_salary_waits_two_days_and_recording_the_receipt_clears_it(c, setup, monkeypatch):
    due = date(2026, 12, 31)
    on = due + timedelta(days=2)
    monkeypatch.setenv('LIGHTNING_TODAY', on.isoformat())
    account, salary = setup[0]['cib'].id, setup[1]['EXP.WORK.SALARY'].id
    item_id = c.planning.create(kind='INCOME', name='Salary', amount='2000', frequency='ONCE',
                               start_date=due.isoformat(), account_id=account, category_id=salary)
    before = tuple(c.db.scalar(f'SELECT count(*) FROM {table}')
                   for table in ('transactions', 'planned_payments', 'cash_funding'))
    assert _missing_income(c, due) == []
    assert _missing_income(c, due + timedelta(days=1)) == []
    row, = _missing_income(c, on)
    assert row['label'] == 'Salary has not arrived'
    assert row['detail'] == 'Expected 2026-12-31 · 2,000.00 EGP. Record it when it arrives.'
    assert row['priority'] == 1 and row['popup'] and row['action'] == 'Record'
    assert row['late_days'] == 2
    client = TestClient(create_app(c))
    assert client.get(row['href']).status_code == 200
    assert tuple(c.db.scalar(f'SELECT count(*) FROM {table}')
                 for table in ('transactions', 'planned_payments', 'cash_funding')) == before
    response = client.post(f'/plan/items/{item_id}/pay', data={
        'due': due.isoformat(), 'outcome': 'record', 'date_paid': on.isoformat(),
        'amount': '2000', 'account_id': str(account), 'back': '/'}, follow_redirects=False)
    assert response.status_code == 303
    assert c.db.scalar('SELECT count(*) FROM transactions') == before[0] + 1
    assert _missing_income(c, on) == []


def test_missing_income_reminder_is_opt_in_stable_and_does_not_post_money(c, setup, monkeypatch):
    from lightning.workflows.reminders import ReminderService

    monkeypatch.setenv('LIGHTNING_TODAY', '2027-01-02')
    account, salary = setup[0]['cib'].id, setup[1]['EXP.WORK.SALARY'].id
    item_id = c.planning.create(kind='INCOME', name='Salary', amount='2000', frequency='ONCE',
                               start_date='2026-12-31', account_id=account, category_id=salary)
    service = ReminderService(c)
    before = c.db.scalar('SELECT count(*) FROM transactions')
    assert service.due() == []
    c.settings.set('reminders_enabled', '1')
    notices = [item for item in service.due() if item['label'] == 'Salary has not arrived']
    assert len(notices) == 1 and notices[0]['href'].startswith(f'/plan/items/{item_id}/pay?due=2026-12-31')
    assert notices == [item for item in service.due() if item['label'] == 'Salary has not arrived']
    assert c.db.scalar('SELECT count(*) FROM transactions') == before
    c.db.read_only = True
    try:
        assert service.due() == []
    finally:
        c.db.read_only = False
    c.planning.skip(item_id, '2026-12-31')
    assert _missing_income(c, date(2027, 1, 2)) == []
    assert not any(item['label'] == 'Salary has not arrived' for item in service.due())
    c.planning.reopen(item_id, '2026-12-31')
    assert len(_missing_income(c, date(2027, 1, 2))) == 1
    c.planning.remove(item_id)
    assert _missing_income(c, date(2027, 1, 2)) == []


@pytest.mark.parametrize('currency', ['EGP', 'USD'])
def test_missing_income_uses_its_account_currency_or_the_profile_default(c, currency, monkeypatch):
    from lightning.database.currencies import CurrencyRegistry

    monkeypatch.setenv('LIGHTNING_TODAY', '2027-01-02')
    account_id = None
    if currency == 'USD':
        CurrencyRegistry(c.db).register('USD')
        c.fx.save('USD', '2026-12-31', '50')
        account_id = c.account_flows.open_account('Dollars', 'BANK', '2026-12-31', '0', currency='USD').id
    c.planning.create(kind='INCOME', name='Income', amount='125.50', frequency='ONCE',
                      start_date='2026-12-31', account_id=account_id)
    row, = _missing_income(c, date(2027, 1, 2))
    assert row['detail'] == f'Expected 2026-12-31 · 125.50 {currency}. Record it when it arrives.'


@pytest.mark.parametrize('phone', [False, True])
def test_missing_income_row_and_notification_are_translated_on_both_surfaces(c, setup, monkeypatch, phone):
    monkeypatch.setenv('LIGHTNING_TODAY', '2027-01-02')
    monkeypatch.setenv('LIGHTNING_REMINDER_SCHEDULE', str(c.data_dir / 'test-reminder-schedule.json'))
    account, salary = setup[0]['cib'].id, setup[1]['EXP.WORK.SALARY'].id
    c.planning.create(kind='INCOME', name='المرتب', amount='2000', frequency='ONCE',
                      start_date='2026-12-31', account_id=account, category_id=salary)
    c.settings.set('reminders_enabled', '1')
    app = create_app(c)
    if phone:
        inner = app

        async def phone_app(scope, receive, send):
            if scope['type'] == 'http':
                scope.setdefault('state', {})['phone'] = True
            await inner(scope, receive, send)
        app = phone_app
    client = TestClient(app)
    en = client.get('/needs-you/payments')
    assert en.status_code == 200 and 'المرتب has not arrived' in en.text
    c.settings.set('locale', 'ar')
    ar = client.get('/needs-you/payments')
    assert ar.status_code == 200 and 'المرتب لسه ما وصلش' in ar.text
    assert 'سجّله لما يوصل.' in ar.text and 'has not arrived' not in ar.text
    notice, = [item for item in client.get('/reminders/due.json').json()['items']
               if item['label'] == 'المرتب لسه ما وصلش']
    assert 'سجّله لما يوصل.' in notice['detail'] and 'Expected' not in notice['detail']
