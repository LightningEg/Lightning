from datetime import date
from decimal import Decimal as D

import pytest

from lightning.core.errors import ValidationError, ConflictError


def prepared(c, setup):
    bank = setup[0]['cib'].id
    category = setup[1]['EXP.PERSONAL.FOOD'].id
    bill = c.planning.create(kind='BILL', name='Annual cover', amount='1000', frequency='ONCE',
                             start_date='2026-12-20', account_id=bank, category_id=category)
    reserve = c.reserves.create('Cover fund', '1000')
    c.reserves.allocate(reserve['id'], '800')
    c.reserves.set_planned_item(reserve['id'], bill)
    return bank, category, bill, reserve['id']


def test_paid_bill_draws_only_available_cash_and_retry_does_not_draw_again(c, setup):
    bank, _, bill, reserve = prepared(c, setup)
    txn = c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1000', bank)
    assert c.reserves.get(reserve)['effective_allocated'] == 0
    assert c.reserves.links_for_transaction(txn)[0]['amount_e6'] == 800000000
    c.reserves.fund_bill_payment(bill, txn)
    assert len(c.reserves.links_for_transaction(txn)) == 1
    assert c.reporting.cash_flow('2026-12-01', '2026-12-31').outflows == 1000
    assert sum(c.budgets.plan_funded_spending('2026-12-01', '2026-12-31').values()) == 200


def test_due_bill_and_its_reserve_do_not_hold_the_same_cash_twice(c, setup):
    bank, _, bill, reserve = prepared(c, setup)
    before = c.position.at(date(2026, 12, 31))
    assert before.bill_reserve_coverage == 800
    assert before.free_cash == before.spendable_cash - before.reserves - 200
    c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1000', bank)
    after = c.position.at(date(2026, 12, 31))
    assert after.bill_reserve_coverage == 0
    assert after.free_cash == before.free_cash
    assert c.reserves.get(reserve)['effective_allocated'] == 0


def test_failed_reserve_link_rolls_back_bill_and_transaction(c, setup, monkeypatch):
    bank, _, bill, reserve = prepared(c, setup)
    count = c.db.scalar('SELECT COUNT(*) FROM transactions')
    def fail(*args):
        raise ValidationError('injected reserve failure')
    monkeypatch.setattr(c.reserves, '_set_expense_link', fail)
    with pytest.raises(ValidationError, match='injected'):
        c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1000', bank)
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == count
    assert c.reserves.get(reserve)['effective_allocated'] == 800
    assert c.planning.payments(c.planning.get(bill), '2026-12-31')[0].outstanding


def test_integrity_reconciles_linked_bill_and_detects_wrong_screen_cash(c, setup, monkeypatch):
    prepared(c, setup)
    check = c.integrity._free_cash_check('2026-12-31')
    assert check.status == 'PASS' and check.difference == 0
    real = c.reporting.owned_liquid_cash
    monkeypatch.setattr(c.reporting, 'owned_liquid_cash', lambda day: real(day) + D('100'))
    check = c.integrity._free_cash_check('2026-12-31')
    assert check.status == 'ISSUE' and check.difference == 100


def test_only_one_active_project_reserve_can_be_linked_to_a_bill(c, setup):
    _, _, bill, reserve = prepared(c, setup)
    other = c.reserves.create('Second fund', '1000')
    with pytest.raises(ConflictError):
        c.reserves.set_planned_item(other['id'], bill)
    c.reserves.set_planned_item(reserve, None)
    c.reserves.set_planned_item(other['id'], bill)
    assert c.reserves.bill_reserve(bill)['id'] == other['id']


def test_future_bill_uses_reserved_cash_once_in_forecast(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-01')
    prepared(c, setup)
    forecast = c.forecaster.forecast(date(2026, 12, 1), months=2)
    row = forecast.months[0]
    assert row.reserved_bills == 800 and row.commitments == 200
    assert row.closing == row.opening + row.money_in - row.money_out
    assert forecast.payments_before_income_total == 1000
    assert dict(forecast.safe_to_spend_parts)['Bill cash already set aside'] == 800
    assert sum((value for _, value in forecast.safe_to_spend_parts), D(0)) == forecast.safe_to_spend


def test_link_bill_through_ui_and_show_saved_amount_on_bill_and_payment(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    bank, category, bill, reserve = prepared(c, setup)
    c.reserves.set_planned_item(reserve, None)
    client = TestClient(create_app(c))
    page = client.get('/plan/reserves')
    assert page.status_code == 200 and 'Bill funded by this reserve' in page.text
    assert f'value="{bill}"' in page.text
    response = client.post(f'/reserves/{reserve}/bill', data={'planned_item_id': str(bill)}, follow_redirects=False)
    assert response.status_code == 303
    assert c.reserves.bill_reserve(bill)['id'] == reserve
    recurring = client.get('/plan/recurring')
    assert 'Saved for this bill: 800 EGP in Cover fund.' in recurring.text
    from test_phone_cash_planning import _phone
    assert 'Saved for this bill: 800 EGP in Cover fund.' in _phone(c).get('/plan/recurring').text
    payment = client.get(f'/plan/items/{bill}/pay?due=2026-12-20')
    assert 'Saved for this bill: 800 EGP in Cover fund.' in payment.text
    c.settings.set('locale', 'ar')
    assert 'محجوز للفاتورة دي' in client.get(f'/plan/items/{bill}/pay?due=2026-12-20').text
    c.settings.set('locale', 'en')
    invalid = client.post(f'/reserves/{reserve}/bill', data={'planned_item_id': '9' * 5000}, follow_redirects=False)
    assert invalid.status_code == 303 and c.reserves.bill_reserve(bill)['id'] == reserve
    client.post(f'/reserves/{reserve}/bill', data={'planned_item_id': ''})
    assert c.reserves.bill_reserve(bill) is None


def test_manual_and_automatic_matching_draw_once(c, setup):
    bank, category, bill, reserve = prepared(c, setup)
    txn = c.transactions.record_outflow('2026-12-20', bank, '1000', category)
    c.planning.mark_paid(bill, '2026-12-20', txn.id)
    c.planning.mark_paid(bill, '2026-12-20', txn.id)
    assert c.reserves.get(reserve)['effective_allocated'] == 0
    assert len(c.reserves.links_for_transaction(txn.id)) == 1


def test_automatic_match_draws_once(c, setup):
    bank, category, bill, reserve = prepared(c, setup)
    txn = c.transactions.record_outflow('2026-12-20', bank, '1000', category)
    assert c.planning.match_payments(date(2026, 12, 31)) == 1
    assert c.planning.match_payments(date(2026, 12, 31)) == 0
    assert c.reserves.get(reserve)['effective_allocated'] == 0
    assert len(c.reserves.links_for_transaction(txn.id)) == 1


def test_bill_payment_undo_redo_and_void_restore(c, setup):
    from lightning.undo import user_action
    bank, _, bill, reserve = prepared(c, setup)
    with user_action('Pay bill'):
        txn = c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1000', bank)
    assert c.reserves.get(reserve)['effective_allocated'] == 0
    c.undo.replay()
    assert c.reserves.get(reserve)['effective_allocated'] == 800
    c.undo.replay(redo=True)
    assert c.reserves.get(reserve)['effective_allocated'] == 0
    c.transactions.void(txn, 'Correction')
    assert c.reserves.get(reserve)['effective_allocated'] == 800
    c.transactions.restore(txn)
    assert c.reserves.get(reserve)['effective_allocated'] == 0


def test_reserve_coverage_is_allocated_once_across_future_occurrences(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-01')
    bank = setup[0]['cib'].id
    category = setup[1]['EXP.PERSONAL.FOOD'].id
    bill = c.planning.create(kind='BILL', name='Monthly cover', amount='300', frequency='MONTHLY',
                             start_date='2026-12-10', account_id=bank, category_id=category)
    reserve = c.reserves.create('Cover', '800')
    c.reserves.allocate(reserve['id'], '800')
    c.reserves.set_planned_item(reserve['id'], bill)
    second = c.planning.create(kind='BILL', name='Annual bill', amount='400', frequency='ONCE',
                               start_date='2027-01-15', account_id=bank, category_id=category)
    second_reserve = c.reserves.create('Annual fund', '250')
    c.reserves.allocate(second_reserve['id'], '250')
    c.reserves.set_planned_item(second_reserve['id'], second)
    covered = c.planning.bill_reserve_coverage(date(2026, 12, 1), date(2027, 3, 31))
    assert covered[(second, '2027-01-15')] == 250
    assert [covered.get((bill, day), D(0)) for day in ('2026-12-10', '2027-01-10', '2027-02-10', '2027-03-10')] == [300, 300, 200, 0]


from test_journal_finance import devices  # noqa: F401


def test_bill_reserve_and_payment_replay_by_uuid_on_home_and_replica(devices):
    from lightning.sync.journal.codec import origin_id, unpack
    from test_journal_area_plans import add_rent
    home, replica = devices
    bill_wire = add_rent(replica)
    bill_uuid = unpack(bill_wire)["body"]["record"]
    reserve_wire = replica.command("reserves.create", name="Rent fund", target="250", due_date=None,
                                   recurrence="NONE", counterparty_id=None, category_id=None,
                                   account_id=None, kind="PROJECT")
    reserve_uuid = unpack(reserve_wire)["body"]["record"]
    replica.sync_with(home.home)
    allocate = replica.command("reserves.allocate", reserve_id=reserve_uuid, amount="250")
    replica.sync_with(home.home)
    # Physical ids differ; the command and replicated foreign key must use UUIDs.
    old_id = replica.adapter.local("planned_items", bill_uuid)
    new_id = old_id + 1000
    replica.c.db.conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with replica.adapter.writing():
            with replica.c.db.transaction():
                replica.c.db.execute("UPDATE planned_items SET id=? WHERE id=?", (new_id, old_id))
                replica.c.db.execute("UPDATE journal_ids SET local_id=? WHERE entity='planned_items' AND local_id=?",
                                     (new_id, old_id))
    finally:
        replica.c.db.conn.execute("PRAGMA foreign_keys=ON")
    assert home.adapter.local("planned_items", bill_uuid) != replica.adapter.local("planned_items", bill_uuid)
    link = replica.command("reserves.set_planned_item", reserve_id=reserve_uuid, planned_item_id=bill_uuid)
    replica.sync_with(home.home)
    for wire in (bill_wire, reserve_wire, allocate, link):
        assert home.home.status(origin_id(unpack(wire)["body"]["origin"]))["status"] == "accepted"
    for device in (home, replica):
        reserve_id = device.adapter.local("cash_reserves", reserve_uuid)
        bill_id = device.adapter.local("planned_items", bill_uuid)
        assert device.c.reserves.get(reserve_id)["planned_item_id"] == bill_id
    paid = replica.command("plans.pay", item_id=bill_uuid, due_date="2026-09-05", date_paid="2026-09-05",
                           amount="300", account_id=None)
    replica.sync_with(home.home)
    assert home.home.status(origin_id(unpack(paid)["body"]["origin"]))["status"] == "accepted"
    for device in (home, replica):
        reserve = device.c.reserves.get(device.adapter.local("cash_reserves", reserve_uuid))
        assert reserve["effective_allocated"] == 0 and reserve["spent"] == 250
        assert len(device.c.reserves.links_for_reserve(reserve["id"])) == 1
    assert home.store.fingerprint() == replica.store.fingerprint() == replica.adapter.fingerprint(full=True)


def test_foreign_currency_draw_rounds_down_to_base_minor_unit(c, setup):
    from test_workflow_matching import _usd_account
    account = _usd_account(c)
    c.fx.save('USD', '2026-12-20', '50.123456')
    category = setup[1]['EXP.PERSONAL.FOOD'].id
    bill = c.planning.create(kind='BILL', name='USD bill', amount='1', frequency='ONCE',
                             start_date='2026-12-20', account_id=account.id, category_id=category)
    reserve = c.reserves.create('Foreign bill fund', '100')
    c.reserves.allocate(reserve['id'], '100')
    c.reserves.set_planned_item(reserve['id'], bill)
    txn = c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1', account.id)
    links = c.reserves.links_for_transaction(txn)
    assert len(links) == 1 and links[0]['amount_e6'] == 50120000
    assert c.reserves.get(reserve['id'])['effective_allocated'] == D('49.88')


def test_dated_association_survives_relink_and_unlink(c, setup, monkeypatch):
    bank = setup[0]['cib'].id
    category = setup[1]['EXP.PERSONAL.FOOD'].id
    first = c.planning.create(kind='BILL', name='First bill', amount='600', frequency='ONCE',
                              start_date='2026-12-02', account_id=bank, category_id=category)
    second = c.planning.create(kind='BILL', name='Second bill', amount='300', frequency='ONCE',
                               start_date='2026-12-03', account_id=bank, category_id=category)
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-11-30')
    reserve = c.reserves.create('Bill fund', '800')
    c.reserves.allocate(reserve['id'], '800')
    assert c.reserves.bill_savings('2026-11-30') == {}
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-01')
    c.reserves.set_planned_item(reserve['id'], first)
    old_position = c.position.at(date(2026, 12, 2))
    assert old_position.bill_reserve_coverage == 600
    old_free = old_position.free_cash
    assert c.reserves.bill_savings('2026-11-30') == {}
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-03')
    c.reserves.set_planned_item(reserve['id'], second)
    assert c.reserves.bill_savings('2026-12-02') == {first: D('800')}
    assert c.reserves.bill_savings('2026-12-03') == {second: D('800')}
    assert c.position.at(date(2026, 12, 2)).free_cash == old_free
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-05')
    c.reserves.set_planned_item(reserve['id'], None)
    assert c.reserves.bill_savings('2026-12-02') == {first: D('800')}
    assert c.reserves.bill_savings('2026-12-03') == {second: D('800')}
    assert c.reserves.bill_savings('2026-12-05') == {}
    assert c.position.at(date(2026, 12, 2)).free_cash == old_free
    assert c.position.at(date(2026, 12, 2)).bill_reserve_coverage == 600


def test_migration_keeps_existing_history_unlinked():
    import sqlite3
    from pathlib import Path
    db = sqlite3.connect(':memory:')
    try:
        db.executescript('CREATE TABLE planned_items(id INTEGER PRIMARY KEY);'
                         'CREATE TABLE cash_reserves(id INTEGER PRIMARY KEY, status TEXT);'
                         'CREATE TABLE reserve_allocation_history(id INTEGER PRIMARY KEY, effective_date TEXT);'
                         'CREATE TABLE reserve_transaction_links(id INTEGER PRIMARY KEY,transaction_id INTEGER,amount_e6 INTEGER);'
                         'INSERT INTO reserve_transaction_links VALUES(1,9,800000000);'
                         "INSERT INTO cash_reserves VALUES(1,'ACTIVE');"
                         "INSERT INTO reserve_allocation_history VALUES(1,'2026-09-01');")
        migration = Path(__file__).resolve().parents[1] / 'lightning/database/migrations/0073_reserve_bill.sql'
        db.executescript(migration.read_text())
        assert db.execute('SELECT planned_item_id FROM cash_reserves').fetchone() == (None,)
        assert db.execute('SELECT planned_item_id FROM reserve_allocation_history').fetchone() == (None,)
        assert db.execute('SELECT amount_e6,planned_item_id FROM reserve_transaction_links').fetchone() == (800000000,None)
    finally:
        db.close()


def test_linked_bill_cannot_be_changed_to_income_and_legacy_bad_kind_never_creates_cash(c, setup):
    bank, _, bill, _ = prepared(c, setup)
    with pytest.raises(ValidationError, match='Unlink the reserve'):
        c.planning.update(bill, kind='INCOME', name='Income', amount='1000', frequency='ONCE',
                          start_date='2026-12-20', account_id=bank,
                          category_id=setup[1]['EXP.WORK.SALARY'].id)
    # Defensive reading of older/damaged metadata never counts reserve coverage against income.
    c.db.execute("UPDATE planned_items SET kind='INCOME' WHERE id=?", (bill,))
    position = c.position.at(date(2026, 12, 31))
    assert position.bill_reserve_coverage == 0
    assert position.free_cash == position.spendable_cash - position.reserves - position.bills_due


def test_renewing_reserve_keeps_bill_association_without_assigning_new_cash(c, setup):
    payment_day = '2026-12-20'
    bank, category = setup[0]['cib'].id, setup[1]['EXP.PERSONAL.FOOD'].id
    bill = c.planning.create(kind='BILL', name='Annual policy', amount='1000', frequency='YEARLY',
                             start_date=payment_day, account_id=bank, category_id=category)
    reserve = c.reserves.create('Policy fund', '1000', due_date=payment_day, recurrence='YEARLY')
    c.reserves.allocate(reserve['id'], '1200')
    c.reserves.set_planned_item(reserve['id'], bill)
    c.planning.record_payment(bill, payment_day, payment_day, '1000', bank)
    following = c.reserves.bill_reserve(bill)
    assert following['id'] != reserve['id'] and following['due_date'] == '2027-12-20'
    assert following['effective_allocated'] == D('200')
    assert c.reserves.get(reserve['id'])['status'] == 'COMPLETE'


@pytest.mark.parametrize('allocated', ['800', '1000'])
@pytest.mark.parametrize('explicit_plan', [False, True])
@pytest.mark.parametrize('day', ['2026-12-14', '2026-12-31'])
def test_paying_a_linked_bill_preserves_safe_cash_and_plan_advice(c, setup, monkeypatch, allocated, explicit_plan, day):
    monkeypatch.setenv('LIGHTNING_TODAY', day)
    bank, category, bill, reserve = prepared(c, setup)
    c.reserves.allocate(reserve, allocated)
    c.db.execute("UPDATE cash_reserves SET due_date='2026-12-20' WHERE id=?", (reserve,))
    if explicit_plan:
        c.budgets.set_budget(category, '2026-12', '1000', schedule=c.schedules.view())
    as_of = date.fromisoformat(day)
    before = c.forecaster.forecast(as_of)
    plan_before = c.budgets.plan_summary('2026-12', schedule=c.schedules.view())
    expected_plan = D('1000') if explicit_plan else D('1000') - D(allocated)
    assert plan_before['planned'] == expected_plan
    assert c.forecaster.goal_needs('2026-12') == []  # its scheduled bill is the forecast home
    txn = c.planning.record_payment(bill, '2026-12-20', min(day, '2026-12-20'), '1000', bank)
    after = c.forecaster.forecast(as_of)
    assert after.safe_to_spend == before.safe_to_spend
    assert c.budgets.plan_summary('2026-12', schedule=c.schedules.view())['planned'] == expected_plan
    assert c.reporting.cash_flow('2026-12-01', '2026-12-31').outflows == 1000
    assert c.db.scalar('SELECT planned_item_id FROM reserve_transaction_links WHERE transaction_id=?', (txn,)) == bill
    c.transactions.void(txn)
    assert c.forecaster.forecast(as_of).safe_to_spend == before.safe_to_spend
    c.transactions.restore(txn)
    assert c.forecaster.forecast(as_of).safe_to_spend == before.safe_to_spend


def test_existing_fully_used_reserve_link_is_attributed_when_the_bill_settles(c, setup):
    bank, category, bill, reserve = prepared(c, setup)
    txn = c.transactions.record_outflow('2026-12-20', bank, '1000', category)
    c.reserves.set_expense_link(reserve, txn.id, '800')
    assert c.reserves.get(reserve)['effective_allocated'] == 0
    c.planning.mark_paid(bill, '2026-12-20', txn.id)
    assert c.reserves.bill_payment_funding()[(bill, txn.id)] == 800
    assert c.budgets.plan_summary('2026-12', schedule=c.schedules.view())['planned'] == 200


@pytest.mark.parametrize('funded', [False, True])
def test_payday_does_not_hold_linked_bill_cash_twice_or_consume_its_envelope(c, setup, monkeypatch, funded):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    bank, category, bill, reserve = prepared(c, setup)
    c.settings.set('cash_funding_enabled', '1')
    c.budgets.set_budget(category, '2026-12', '1000', schedule=c.schedules.view())
    if funded:
        preview = c.funding.preview()
        c.funding.apply(preview['token'], {str(category): '1000'}, {})
    before = c.funding.preview()
    row = next(row for row in before['rows'] if row['id'] == category)
    assert row['due'] == 200
    assert next(row for row in before['reserves'] if row['id'] == reserve)['suggested'] == 0
    c.planning.record_payment(bill, '2026-12-20', '2026-12-31', '1000', bank)
    after = c.funding.preview()
    assert after['ready'] == before['ready']
    row = next(row for row in after['rows'] if row['id'] == category)
    assert row['actual'] == 200 and row['remaining'] == (800 if funded else 0)
    assert c.budgets.plan_summary('2026-12', schedule=c.schedules.view())['planned'] == 1000


def test_register_edit_preserves_bill_funding_attribution(c, setup):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    bank, category, bill, _ = prepared(c, setup)
    txn = c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1000', bank)
    client = TestClient(create_app(c))
    reply = client.post(f'/accounts/{bank}/register/{txn}', data={
        'date': '2026-12-20', 'amount': '-900', 'category': c.categories.get(category).name,
        'counterparty': '', 'notes': 'Correction', 'revision': c.transactions.revision(txn)}, follow_redirects=False)
    assert reply.status_code == 303
    new_id = c.db.scalar("SELECT MAX(id) FROM transactions WHERE status='POSTED' AND type='OUT'")
    assert c.reserves.bill_payment_funding()[(bill, new_id)] == 800
    assert c.budgets.plan_summary('2026-12', schedule=c.schedules.view())['planned'] == 200


def test_activity_category_change_preserves_bill_funding_attribution(c, setup):
    bank, _, bill, _ = prepared(c, setup)
    txn = c.planning.record_payment(bill, '2026-12-20', '2026-12-20', '1000', bank)
    category = c.categories.get_by_code('EXP.PERSONAL.UTILITIES').id
    c.activity_review.apply(txn, c.activity_review.fingerprint(txn), category_id=category)
    assert c.reserves.bill_payment_funding()[(bill, txn)] == 800
    assert c.budgets.plan_funded_spending('2026-12-01', '2026-12-31')[category] == 200
