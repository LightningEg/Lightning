"""Milestone 1 uses the existing screens and keeps plans separate from cash."""
from datetime import date
from decimal import Decimal as D
from io import BytesIO, StringIO
from zipfile import ZipFile
import csv
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.planning.domain import PlanKind
from lightning.planning.loan_actions import create_purchase, preview_early_payment, record_early_payment
from lightning.ui.web import create_app
from lightning.workflows.salary_setup import set_up_salary
from lightning.workflows.data_export import export_all


def test_salary_setup_is_a_plan_preserves_payday_and_does_not_post_cash(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-02-14')
    accounts, _ = setup
    before = c.reporting.account_balance(accounts['cib'].id, '2026-02-14')
    client = TestClient(create_app(c))
    page = client.post('/setup/salary', data={'account_id': accounts['cib'].id, 'amount': '30000', 'payday': '31'})
    assert page.status_code == 200 and 'Salary' in page.text
    item = c.planning.items((PlanKind.INCOME,))[0]
    dates = [p.due_date for p in c.planning.payments(item, '2026-03-31') if p.outstanding]
    assert dates == ['2026-02-28', '2026-03-31']
    assert c.budgets.income_average('2026-02', schedule=c.schedules.view()).amount == D('30000')
    assert c.forecaster.forecast(date(2026, 2, 14)).next_income_date == '2026-02-28'
    assert c.reporting.account_balance(accounts['cib'].id, '2026-02-14') == before
    assert client.post('/setup/salary', data={'account_id': accounts['cib'].id, 'amount': '30000', 'payday': '31'}).status_code == 400
    assert len(c.planning.items((PlanKind.INCOME,))) == 1


def test_bank_presets_reuse_only_exact_headers_and_consistent_confirmed_bank_choices(c, setup):
    accounts, _ = setup
    source = accounts['cib']
    second = c.account_flows.open_account('CIB savings', 'BANK', '2026-01-01', '0', institution='cib')
    other = c.account_flows.open_account('NBE', 'BANK', '2026-01-01', '0', institution='NBE')
    headers = ['When', 'Paid', 'Name']
    mapping = {'amount_model': 'SINGLE', 'Date': 'When', 'Amount': 'Paid', 'Counterparty': 'Name'}
    c.bank_imports.stage(source.id, 'first.csv', b'When,Paid,Name\n2026-10-01,15,Cafe\n', mapping, invert_amount=True)
    reused = c.bank_imports.saved_mapping(second.id, headers)
    assert reused['Amount'] == 'Paid' and reused['amount_sign'] == 'invert'
    assert c.bank_imports.saved_mapping(other.id, headers) is None
    assert c.bank_imports.saved_mapping(second.id, ['When', 'Money', 'Name']) is None
    conflicting = c.account_flows.open_account('CIB another', 'BANK', '2026-01-01', '0', institution='CIB')
    c.bank_imports.stage(conflicting.id, 'different.csv', b'When,Paid,Name\n2026-10-02,15,Cafe\n', mapping, invert_amount=False)
    assert c.bank_imports.saved_mapping(second.id, headers) is None


def test_export_all_has_plans_transactions_archived_records_and_no_formula_cells(c, setup):
    accounts, cats = setup
    c.transactions.record_outflow('2026-10-01', accounts['cib'].id, '123.45', cats['EXP.PERSONAL.FOOD'].id, notes='=1+1')
    c.planning.create(kind='BILL', name='Internet', amount='100', frequency='MONTHLY', start_date='2026-10-01')
    c.settings.set('device_password', 'dummy-secret-not-for-export')
    data, _, _ = export_all(c, 'csv')
    with ZipFile(BytesIO(data)) as z:
        rows = list(csv.DictReader(StringIO(z.read('ledger_entries.csv').decode('utf-8-sig'))))
        assert any(D(row['amount']) == D('123.45') or D(row['amount']) == D('-123.45') for row in rows)
        assert 'Internet' in z.read('planned_items.csv').decode('utf-8-sig')
        assert "'=1+1" in z.read('transactions.csv').decode('utf-8-sig')
        assert 'dummy-secret-not-for-export' not in z.read('settings.csv').decode('utf-8-sig')
        assert 'loan_extra_payments.csv' in z.namelist()
    workbook, _, _ = export_all(c, 'xlsx')
    with ZipFile(BytesIO(workbook)) as z:
        for name in z.namelist():
            if name.startswith('xl/worksheets/'):
                root = ET.fromstring(z.read(name))
                assert root.findall('.//{*}f') == []
        assert b'transactions' in z.read('xl/workbook.xml')
    client = TestClient(create_app(c))
    assert client.get('/exports/all').status_code == 200
    assert client.get('/exports/all?format=csv').headers['content-type'] == 'application/zip'


def _loan(c, accounts):
    return c.planning.create(kind='LOAN', name='Car loan', amount='1000', frequency='MONTHLY',
                             start_date='2026-10-20', payment_count='4', account_id=accounts['cib'].id)


def test_early_payment_shortens_term_fee_is_cash_only_and_void_restores_the_schedule(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-14')
    accounts, _ = setup
    loan = _loan(c, accounts)
    before = c.position.at('2026-10-14')
    quote = preview_early_payment(c.planning, loan, '1500', '50')
    assert (quote['remaining_after'], quote['last_date']) == (D('2500'), '2026-12-20')
    assert c.planning.loan_progress(c.planning.get(loan))['still_to_pay'] == D('4000')  # preview writes nothing
    txn = record_early_payment(c.planning, loan, '1500', '50', '2026-10-14', accounts['cib'].id, '4000')
    payments = c.planning.payments(c.planning.get(loan), '2027-12-31')
    assert [p.amount for p in payments] == [D('1000'), D('1000'), D('500')]
    after = c.position.at('2026-10-14')
    assert after.loans_still_to_pay == D('2500')
    assert before.cash_you_own - after.cash_you_own == D('1550')
    assert before.net_worth - after.net_worth == D('50')
    assert c.planning.loan_progress(c.planning.get(loan))['paid_amount'] == D('1500')
    assert c.position.at('2026-10-13').loans_still_to_pay == D('4000')
    with pytest.raises(ValidationError, match='changed'):
        record_early_payment(c.planning, loan, '1500', '50', '2026-10-14', accounts['cib'].id, '4000')
    c.transactions.void(txn)
    assert c.position.at('2026-10-14').loans_still_to_pay == D('4000')
    assert c.position.at('2026-10-14').cash_you_own == before.cash_you_own


def test_purchase_rounding_skip_and_partial_payment_keep_exact_debt(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-14')
    accounts, _ = setup
    balance = c.reporting.account_balance(accounts['cib'].id, '2026-10-14')
    loan = create_purchase(c.planning, name='Phone', price='1000', fee='0', months='3', first_date='2026-10-20', account_id=accounts['cib'].id)
    item = c.planning.get(loan)
    assert [p.amount for p in c.planning.payments(item, '2027-01-31')] == [D('333.34'), D('333.34'), D('333.32')]
    assert c.reporting.account_balance(accounts['cib'].id, '2026-10-14') == balance
    c.planning.skip(loan, '2026-10-20')
    assert sum((p.still_owed for p in c.planning.payments(item, '2027-01-31')), D(0)) == D('1000')
    # Two actual payments against one instalment retain both receipts and settle exactly its amount.
    c.planning.record_payment(loan, '2026-11-20', '2026-10-14', '100', accounts['cib'].id)
    assert c.planning.loan_progress(item)['still_to_pay'] == D('900')
    c.planning.record_payment(loan, '2026-11-20', '2026-10-14', '233.34', accounts['cib'].id)
    assert c.planning.loan_progress(item)['still_to_pay'] == D('666.66')
    assert c.planning.loan_progress(item)['paid_amount'] == D('333.34')


def test_purchase_and_early_payment_have_preview_steps_and_no_new_tab(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-14')
    accounts, _ = setup
    client = TestClient(create_app(c))
    form = dict(name='Phone', price='3000', fee='60', months='3', first_date='2026-11-01', account_id=str(accounts['cib'].id))
    preview = client.post('/plan/purchases/new', data={**form, 'intent': 'preview'})
    assert preview.status_code == 200 and '1,020.00' in preview.text
    assert c.planning.items((PlanKind.LOAN,)) == []
    assert client.post('/plan/purchases/new', data={**form, 'intent': 'save'}).status_code == 200
    loan = c.planning.items((PlanKind.LOAN,))[0]
    preview = client.post(f'/plan/items/{loan.id}/early-payment', data=dict(principal='3060', fee='0', date_paid='2026-10-14', account_id=accounts['cib'].id, intent='preview'))
    assert preview.status_code == 200 and 'Paid off' in preview.text
    assert c.planning.loan_progress(loan)['still_to_pay'] == D('3060')
    assert client.post(f'/plan/items/{loan.id}/early-payment', data=dict(principal='3060', fee='0', date_paid='2026-10-14', account_id=accounts['cib'].id, intent='record', expected_remaining='3060')).status_code == 200
    assert c.planning.loan_progress(loan)['still_to_pay'] == 0
    assert 'Paid off' in client.get('/plan/loans').text


def test_overdue_instalments_are_paid_first_and_extra_cash_is_in_the_budget(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-14')
    accounts, _ = setup
    loan = c.planning.create(kind='LOAN', name='Old loan', amount='1000', frequency='MONTHLY',
                             start_date='2026-08-20', payment_count='4', account_id=accounts['cib'].id)
    record_early_payment(c.planning, loan, '1500', '50', '2026-10-14', accounts['cib'].id, '4000')
    item = c.planning.get(loan)
    progress = c.planning.loan_progress(item)
    assert (progress['next'].due_date, progress['next'].still_owed) == ('2026-09-20', D('500'))
    assert c.planning.what_you_owe().bills_due == D('500')
    assert c.planning.what_you_owe().other_bills_due == 0
    assert c.planning.loan_payments_by_category('2026-10')[item.category_id] == D('2550')


def test_a_reduced_final_instalment_matches_actual_cash_and_dated_history_survives(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-20')
    accounts, _ = setup
    loan = _loan(c, accounts)
    record_early_payment(c.planning, loan, '1500', '0', '2026-10-14', accounts['cib'].id, '4000')
    item = c.planning.get(loan)
    c.transactions.record_outflow('2026-12-20', accounts['cib'].id, '500', item.category_id)
    c.planning.match_payments()
    assert next(p for p in c.planning.payments(item, '2027-01-31') if p.due_date == '2026-12-20').still_owed == 0
    assert c.planning.loan_progress(item, date(2026, 12, 19))['still_to_pay'] == D('2500')
    # History is preserved if the plan is stopped after an extra payment.
    assert 'stopped' in c.planning.remove(loan)
    assert c.planning.get(loan).active is False


def test_export_works_on_a_read_only_profile_and_keeps_the_database_unchanged(c, setup):
    from lightning.bootstrap import build
    before = c.db.conn.total_changes
    export_all(c, 'csv')
    assert c.db.conn.total_changes == before
    readonly = build(c.db.path, read_only=True)
    try:
        data, _, _ = export_all(readonly, 'csv')
        with ZipFile(BytesIO(data)) as z:
            assert 'accounts.csv' in z.namelist()
    finally:
        readonly.db.close()


@pytest.mark.parametrize('phone', [False, True], ids=['pc', 'phone'])
def test_new_financial_forms_and_previews_are_translated(c, setup, phone):
    from test_arabic_no_english import _client, _english
    accounts, _ = setup
    loan = _loan(c, accounts)
    client = _client(c, phone)
    pages = [client.get('/setup/salary'), client.get(f'/plan/items/{loan}/early-payment'),
             client.post('/plan/purchases/new', data={'name': 'موبايل', 'price': '3000', 'fee': '50',
                         'months': '3', 'first_date': '2027-01-01', 'intent': 'preview'}),
             client.post(f'/plan/items/{loan}/early-payment', data={'principal': '1000', 'fee': '50',
                         'date_paid': '2026-12-31', 'account_id': accounts['cib'].id, 'intent': 'preview'})]
    for page in pages:
        assert page.status_code == 200
        assert not _english(page.text, {'CIB Current', 'Wallet', 'Car loan', 'THNDR', 'CIB CD'}), _english(page.text, {'CIB Current', 'Wallet', 'Car loan', 'THNDR', 'CIB CD'})


def test_ordinary_loan_receipts_reduce_debt_only_from_their_cash_date(c, setup):
    accounts, _ = setup
    loan = _loan(c, accounts)
    c.planning.record_payment(loan, '2026-10-20', '2026-10-21', '1000', accounts['cib'].id)
    item = c.planning.get(loan)
    assert c.planning.loan_progress(item, date(2026, 10, 20))['still_to_pay'] == D('4000')
    assert c.planning.loan_progress(item, date(2026, 10, 21))['still_to_pay'] == D('3000')
    before = c.position.at('2026-10-20', match_payments=False)
    after = c.position.at('2026-10-21', match_payments=False)
    assert before.net_worth == after.net_worth
    assert before.cash_you_own - after.cash_you_own == D('1000')
