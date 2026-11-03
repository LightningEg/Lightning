"""Existing recurring and rule suggestions are actionable, read-only and snoozable in Needs you."""
from datetime import date
from decimal import Decimal

from lightning.workflows.review import ReviewInbox, group_of
from lightning.workflows.weekly import WeeklyReview


def test_existing_suggestions_share_inbox_visibility_and_do_not_post(c, setup, monkeypatch):
    accounts, _ = setup
    suggestion = dict(name='Internet', months=3, last_date='2026-09-12', counterparty_id=17,
                      account_id=accounts['cib'].id, amount=Decimal('400'))
    rule = dict(name='Shop', count=3, category='Food', href='/rules/new?category_id=7', id='offer')
    monkeypatch.setattr(c.planning, 'suggestions', lambda on: [suggestion])
    monkeypatch.setattr(WeeklyReview, 'rule_offers', lambda self: [rule])
    before = c.db.scalar('SELECT COUNT(*) FROM transactions')
    plans = c.db.scalar('SELECT COUNT(*) FROM planned_items')
    inbox, day = ReviewInbox(c), date(2026, 12, 31)
    items = inbox.items(day)
    recurring = next(i for i in items if i['label'] == 'Looks recurring')
    offered_rule = next(i for i in items if i['label'] == 'Make a rule')
    assert recurring['href'] == '/plan/recurring#recurring-suggest'
    assert recurring['action'] == 'Track' and '400 EGP' in recurring['detail']
    assert offered_rule['popup'] and offered_rule['href'] == rule['href']
    assert group_of(offered_rule) == 'activity'
    inbox.decide(recurring['review_id'], 'snoozed', day, '2027-01-02')
    assert recurring['review_id'] not in {i['review_id'] for i in inbox.items(day)}
    assert offered_rule['review_id'] in {i['review_id'] for i in inbox.items(day)}
    inbox.decide(recurring['review_id'], 'restore', day)
    assert recurring['review_id'] in {i['review_id'] for i in inbox.items(day)}
    inbox.decide(recurring['review_id'], 'reviewed', day)
    suggestion['amount'] = Decimal('500')
    assert any(i['label'] == 'Looks recurring' and i['review_id'] != recurring['review_id'] for i in inbox.items(day))
    assert c.db.scalar('SELECT COUNT(*) FROM transactions') == before
    assert c.db.scalar('SELECT COUNT(*) FROM planned_items') == plans


def test_rule_suggestion_can_be_reviewed_without_hiding_recurring(c, setup, monkeypatch):
    monkeypatch.setattr(c.planning, 'suggestions', lambda on: [])
    offers = [dict(name='Shop', count=3, category='Food', href='/rules/new?category_id=7', id='offer')]
    monkeypatch.setattr(WeeklyReview, 'rule_offers', lambda self: offers)
    inbox, day = ReviewInbox(c), date(2026, 12, 31)
    item = next(i for i in inbox.items(day) if i['label'] == 'Make a rule')
    inbox.decide(item['review_id'], 'reviewed', day)
    assert not any(i['label'] == 'Make a rule' for i in inbox.items(day))
    offers.clear()
    assert not any(i['label'] == 'Make a rule' for i in inbox.items(day, include_handled=True))


def test_used_emergency_reserve_is_offered_for_refill(c, setup):
    accounts, cats = setup
    reserve = c.reserves.set_emergency_fund('400', '400')
    txn = c.transactions.record_outflow('2026-09-13', accounts['cib'].id, '100', cats['EXP.PERSONAL.FOOD'].id)
    c.reserves.set_expense_link(reserve['id'], txn.id, '100')
    items = ReviewInbox(c).items(date(2026, 12, 31))
    refill = next(i for i in items if i['label'] == 'Refill a reserve')
    assert '100 EGP' in refill['detail'] and refill['href'] == '/plan/reserves'
    c.reserves.allocate(reserve['id'], '500')
    assert not any(i['label'] == 'Refill a reserve' for i in ReviewInbox(c).items(date(2026, 12, 31)))


def test_emergency_alert_uses_existing_health_band_and_ignores_unknown(c, setup, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(c.planning, 'suggestions', lambda on: [])
    monkeypatch.setattr(WeeklyReview, 'rule_offers', lambda self: [])
    fund = SimpleNamespace(months=Decimal('0.8'))
    monkeypatch.setattr(c.health, 'emergency_fund', lambda on: fund)
    inbox = ReviewInbox(c)
    assert any(i['label'] == 'Emergency fund needs you' for i in inbox._smart_suggestions(date(2026, 12, 31)))
    fund.months = None
    assert not any(i['label'] == 'Emergency fund needs you' for i in inbox._smart_suggestions(date(2026, 12, 31)))
