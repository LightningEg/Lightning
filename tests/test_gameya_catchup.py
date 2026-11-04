"""Late circle setup shows both obligations; catch-up posts dated transfers atomically."""
from decimal import Decimal as D

import pytest

from lightning.core.errors import ValidationError
from test_gameya_screens import _circle, _client


def test_late_circle_shows_all_due_instalments_and_payout_on_both_screens(c, setup):
    circle = _circle(c, setup)
    progress = c.gameya.progress(circle.id)
    assert (progress.due_count, progress.due_amount, progress.payout_due) == (3, D('6000'), True)
    for phone in (False, True):
        page = _client(c, phone).get(f'/gameya/{circle.id}').text
        assert 'Instalments due (not recorded)' in page and '6,000' in page
        assert 'Payout due to you (not recorded)' in page and '20,000' in page
        assert 'Nothing owed either way.' not in page
    attention = c.gameya.attention(__import__('datetime').date(2026, 12, 31))[0]
    assert '3 instalments' in attention['detail'] and '20,000' in attention['detail']


def test_catchup_preserves_dates_and_net_worth_and_refuses_double_submit(c, setup):
    circle = _circle(c, setup)
    before = c.position.at('2026-12-31')
    client = _client(c)
    path = f'/gameya/{circle.id}/past-instalments'
    assert client.post(path, data={'expected_paid': '0'}).status_code == 303
    after = c.position.at('2026-12-31')
    assert c.gameya.progress(circle.id).paid == 3
    assert before.cash_you_own - after.cash_you_own == D('6000')
    assert after.net_worth == before.net_worth
    assert after.gameya_paid_in - before.gameya_paid_in == D('6000')
    dates = c.db.all("SELECT date FROM ledger_entries WHERE account_id=? AND effect='INTERNAL' ORDER BY date", (circle.id,))
    assert [row['date'] for row in dates] == ['2026-10-05', '2026-11-05', '2026-12-05']
    assert client.post(path, data={'expected_paid': '0'}).status_code == 400
    assert c.gameya.progress(circle.id).paid == 3


def test_one_unaffordable_instalment_rolls_back_the_entire_batch(c, setup):
    circle = _circle(c, setup, installment='20000')
    with pytest.raises(ValidationError, match='cash on'):
        c.gameya.record_past_instalments(circle.id, expected_paid=0)
    assert c.gameya.progress(circle.id).paid == 0
    assert c.reporting.account_value(circle.id, '2026-12-31') == 0


def test_pc_circle_distinguishes_passed_today_and_future_dates(c, setup, monkeypatch):
    circle = _circle(c, setup)
    client = _client(c)
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-04')
    future = client.get(f'/gameya/{circle.id}').text
    assert 'Next instalment' in future and 'Date passed · not recorded' not in future
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-05')
    due = client.get(f'/gameya/{circle.id}').text
    assert 'Next instalment' in due and 'Date passed · not recorded' not in due
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-12-31')
    past = client.get(f'/gameya/{circle.id}').text
    assert 'Oldest unrecorded instalment' in past and '2026-10-05' in past
    assert 'Date passed · not recorded' in past and 'Instalments due (not recorded)' in past
