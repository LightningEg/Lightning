"""Salary review and funding decisions stay portable across encrypted journal devices."""
from datetime import date

from test_journal_finance import devices  # noqa: F401
from test_journal_screens import Screen
from lightning.sync.journal.proxy import JournalServices
from lightning.workflows.review import ReviewInbox


def _setup(home, replica):
    services = JournalServices(home)
    bank = next(a for a in home.c.accounts.list() if a.name == 'Bank')
    item_id = services.salary_setup.set_up_salary(bank.id, '200', '31')
    services.planning.record_payment(item_id, '2026-12-31', '2026-12-31', '200', bank.id)
    services.settings.set('cash_funding_enabled', '1')
    food = home.c.categories.get_by_code('EXP.PERSONAL.FOOD')
    services.budgets.set_budget(food.id, '2026-12', '300', schedule=home.c.schedules.view())
    reserve = services.reserves.create('Bill fund', '100')
    replica.sync_with(home.home)
    return reserve['id']


def _reminder(c, handled=False):
    return next((i for i in ReviewInbox(c).items(date(2026, 12, 31), include_handled=handled)
                 if i['label'] == 'Salary received'), None)


def _renumber(device, table, offset, old=None):
    old = old or device.c.db.scalar(f'SELECT id FROM {table} ORDER BY id DESC LIMIT 1')
    new = old + offset
    device.c.db.conn.execute('PRAGMA foreign_keys=OFF')
    try:
        with device.adapter.writing():
            with device.c.db.transaction():
                device.c.db.execute(f'UPDATE {table} SET id=? WHERE id=?', (new, old))
                device.c.db.execute('UPDATE journal_ids SET local_id=? WHERE entity=? AND local_id=?',
                                    (new, table, old))
                if table == 'cash_reserves':
                    device.c.db.execute('UPDATE reserve_allocation_history SET reserve_id=? WHERE reserve_id=?', (new, old))
                if table == 'categories':
                    device.c.db.execute('UPDATE budgets SET category_id=? WHERE category_id=?', (new, old))
    finally:
        device.c.db.conn.execute('PRAGMA foreign_keys=ON')
    return new


def test_salary_snooze_is_shared_despite_different_local_payment_ids(devices):  # noqa: F811
    home, replica = devices
    _setup(home, replica)
    _renumber(replica, 'planned_payments', 1000)
    old = _reminder(replica.c)
    assert old['review_id'] == _reminder(home.c)['review_id']
    response = Screen(replica).post('/needs-you/state', data={'identity': old['review_id'], 'action': 'snoozed',
                                                              'until': '2027-01-05'})
    assert response.status_code == 303
    replica.sync_with(home.home)
    assert _reminder(home.c) is None and _reminder(replica.c) is None
    assert _reminder(home.c, True)['review_state'] == 'snoozed'


def test_replica_payday_confirmation_marks_same_reminder_on_both_devices(devices):  # noqa: F811
    home, replica = devices
    _setup(home, replica)
    _renumber(replica, 'planned_payments', 1000)
    _renumber(replica, 'cash_reserves', 1000)
    food = replica.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    _renumber(replica, 'categories', 1000, old=food)
    assert _reminder(replica.c)['review_id'] == _reminder(home.c)['review_id']
    plan = replica.c.funding.preview()
    assert plan['token'] == home.c.funding.preview()['token']
    values = {'fingerprint': plan['token']}
    values.update({f"category_{r['id']}": str(r['suggested']) for r in plan['rows']})
    values.update({f"reserve_{r['id']}": str(r['suggested']) for r in plan['reserves']})
    before = home.c.db.scalar('SELECT count(*) FROM transactions')
    response = Screen(replica).post('/payday/apply', data=values)
    assert response.status_code == 303 and 'Saved+on+this+device' in response.headers['location']
    replica.sync_with(home.home)
    assert _reminder(home.c) is None and _reminder(replica.c) is None
    assert _reminder(home.c, True)['review_state'] == 'reviewed'
    assert home.c.db.scalar('SELECT count(*) FROM transactions') == before
    assert home.store.fingerprint() == replica.store.fingerprint()


def test_missing_portable_reserve_identity_refuses_funding_preview(devices):  # noqa: F811
    import pytest
    from lightning.core.errors import ValidationError
    home, replica = devices
    _setup(home, replica)
    reserve_id = replica.c.db.scalar('SELECT id FROM cash_reserves ORDER BY id DESC LIMIT 1')
    with replica.adapter.writing():
        replica.c.db.execute("DELETE FROM journal_ids WHERE entity='cash_reserves' AND local_id=?", (reserve_id,))
    with pytest.raises(ValidationError, match='not synchronized'):
        replica.c.funding.preview()
