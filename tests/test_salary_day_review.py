"""A settled salary offers a review, without assigning cash or recording a transaction."""
from datetime import date

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
