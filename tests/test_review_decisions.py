"""Needs you preferences clear reviewed reminders without altering financial records."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.ui.web import create_app
from lightning.workflows.review import ReviewInbox
from lightning.workflows.reminders import ReminderService


def _waiting(c, setup):
    accounts, _ = setup
    c.bank_imports.stage(accounts['cib'].id, 'example.csv', b'Date,Counterparty,Amount\n2026-10-03,Example,-5\n')
    inbox = ReviewInbox(c)
    item = next(item for item in inbox.items(date(2026, 12, 31)) if item['label'] == 'Imported activity needs a decision')
    return inbox, item


def test_reviewed_item_clears_every_consumer_and_can_be_restored(c, setup):
    inbox, item = _waiting(c, setup)
    count = c.db.scalar('SELECT count(*) FROM transactions')
    c.settings.set('reminders_enabled', '1')
    inbox.decide(item['review_id'], 'reviewed', date(2026, 12, 31))
    assert item['review_id'] not in {row['review_id'] for row in ReviewInbox(c).items(date(2026, 12, 31))}
    assert not any(row['label'] == item['label'] for row in ReminderService(c).due())
    client = TestClient(create_app(c))
    assert item['label'] not in client.get('/needs-you').text
    hidden = client.get('/needs-you?tab=handled').text
    assert item['label'] in hidden and 'Restore' in hidden and '1 reviewed' in hidden
    assert c.db.scalar('SELECT count(*) FROM transactions') == count
    inbox.decide(item['review_id'], 'restore', date(2026, 12, 31))
    assert item['review_id'] in {row['review_id'] for row in inbox.items(date(2026, 12, 31))}


def test_snooze_wakes_on_date_and_does_not_silence_changed_items(c, setup):
    inbox, item = _waiting(c, setup)
    inbox.decide(item['review_id'], 'snoozed', date(2026, 12, 31), '2027-01-07')
    assert item['review_id'] not in {row['review_id'] for row in inbox.items(date(2027, 1, 6))}
    assert item['review_id'] in {row['review_id'] for row in inbox.items(date(2027, 1, 7))}
    with pytest.raises(ValidationError, match='after today'):
        inbox.decide(item['review_id'], 'snoozed', date(2026, 12, 31), '2026-12-31')
    with pytest.raises(ValidationError, match='changed'):
        inbox.decide('stale', 'reviewed', date(2026, 12, 31))


def test_new_uncategorized_transaction_returns_even_when_count_stays_same(c, setup):
    accounts, _ = setup
    category = c.categories.get_by_code('EXP.UNACCOUNTED')
    first = c.transactions.record_outflow('2026-10-02', accounts['cib'].id, '40', category.id, allow_system_category=True)
    inbox = ReviewInbox(c)
    old = next(item for item in inbox.items(date(2026, 12, 31)) if item['label'] == '1 payment has no category')
    inbox.decide(old['review_id'], 'reviewed', date(2026, 12, 31))
    c.transactions.void(first.id, 'Corrected')
    c.transactions.record_outflow('2026-10-03', accounts['cib'].id, '40', category.id, allow_system_category=True)
    new = next(item for item in inbox.items(date(2026, 12, 31)) if item['label'] == old['label'])
    assert new['review_id'] != old['review_id']
    assert not any(item['review_id'] == old['review_id'] for item in inbox.items(date(2026, 12, 31), include_handled=True))


def test_actions_through_inbox_are_scoped_to_item_and_persist(c, setup):
    inbox, item = _waiting(c, setup)
    client = TestClient(create_app(c))
    page = client.get('/needs-you')
    assert page.status_code == 200 and 'Mark as reviewed' in page.text and 'Remind me on' in page.text
    result = client.post('/needs-you/state', data={'identity': item['review_id'], 'action': 'snoozed', 'until': '2027-01-07'})
    assert result.status_code == 200 and item['label'] not in result.text
    assert '2027-01-07' in client.get('/needs-you?tab=handled').text
    result = client.post('/needs-you/state', data={'identity': item['review_id'], 'action': 'restore', 'tab': 'handled'})
    assert result.status_code == 200
    assert item['label'] in client.get('/needs-you').text
