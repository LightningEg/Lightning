"""Generic preference commands cannot bypass the financial input limits."""
from uuid import uuid4

import pytest

from test_journal_commands import full_devices
from lightning.core.errors import ValidationError
from lightning.sync.journal.codec import JournalError, unpack
from lightning.sync.journal.commands import prepare


@pytest.mark.parametrize('key,value', [
    ('investment_monthly_goal', 'NaN'), ('investment_monthly_goal', '1e999999'),
    ('investment_monthly_goal', '-1'), ('budget_manual_monthly_income', 'not money'),
    ('budget_overall_ceiling', '-0.01'), ('cash_funding_enabled', 'yes'),
    ('budget_income_months', '999'), ('investment_planner_mode', 'unknown'),
    ('budget_carryover_month', '2026-99'), ('budget_suppressed_categories', '{"1":"2026-99"}'),
    ('budget_tracked_categories', '[true]'), ('financial_health_unknown', '1'),
])
def test_invalid_preference_is_refused_locally_without_allocating_an_origin(full_devices, key, value):
    _, peer, identities = full_devices
    before = peer.fingerprint()
    with pytest.raises((JournalError, ValidationError)):
        peer.adapter.save_action([dict(command='profile.set_financial_setting', arguments=dict(key=key, value=value))], identities[1].sign)
    assert peer.fingerprint() == before
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 1
    assert not peer.pending()


def test_old_invalid_preference_gets_one_terminal_refusal_and_no_financial_write(full_devices):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    action = prepare(peer.adapter.c, peer.adapter.graph, [dict(command='profile.set_financial_setting',
                     arguments=dict(key='investment_monthly_goal', value='700'))])
    action['calls'][0]['arguments']['value'] = 'NaN'
    wire = peer.save(kind='action.add', record=str(uuid4()), groups=dict(action=action), bases=dict(action=None), signer=identities[1].sign)
    home.receive(wire)
    commit, = home.process()
    assert unpack(commit)['body']['outcome'] == 'rejected'
    assert unpack(commit)['body']['reason'] == 'financial-validation'
    peer.apply(commit)
    assert peer.fingerprint() == before == home.store.fingerprint()
    home.receive(wire)
    assert home.process() == []
    assert home.store.cursor()['revision'] == 1
    assert not peer.pending()
