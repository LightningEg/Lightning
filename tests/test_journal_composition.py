"""Multi-step forms use normal services and explicit earlier result handles."""
from copy import deepcopy
import json
from uuid import uuid4

import pytest

from test_journal_commands import full_devices
from test_journal_forms import accept
from lightning.sync.journal.codec import JournalError, unpack
from lightning.sync.journal.commands import validate
from lightning.sync.journal.forms import FormCapture


def reserve_action(peer, signer):
    with FormCapture(peer) as form:
        reserve = form.container.reserves.create('Holiday', '1000')
        form.container.reserves.allocate(reserve['id'], '100')
        return form.finish(signer)


def test_new_reserve_and_initial_allocation_are_one_intent_with_no_replica_ids(full_devices):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    wire = reserve_action(peer, identities[1].sign)
    body = unpack(wire)['body']
    action = body['groups']['action']
    call, = action['calls']
    assert call['command'] == 'workflow.compose'
    assert len(call['arguments']['steps']) == 2
    binding, = call['arguments']['bindings'].values()
    assert binding == dict(entity='cash_reserves', slot='record', step=0)
    assert peer.fingerprint() == before
    accept(home, peer, wire)
    assert peer.db.scalar("SELECT allocated_e6 FROM cash_reserves WHERE name='Holiday'") == 100_000_000


def test_new_category_can_feed_later_budget_and_embedded_preference_in_same_action(full_devices):
    home, peer, identities = full_devices
    with FormCapture(peer) as form:
        parent = form.container.categories.get_by_code('EXP.PERSONAL')
        category = form.container.categories.create(parent.id, 'New category')
        form.container.budgets.set_budget(category.id, '2026-09', '450')
        form.container.settings.set('budget_tracked_categories', json.dumps([category.id]))
        wire = form.finish(identities[1].sign)
    accept(home, peer, wire)
    selected = json.loads(peer.adapter.c.settings.get('budget_tracked_categories'))
    category = peer.adapter.c.categories.get(selected[0])
    assert category.name == 'New category'
    assert peer.adapter.c.budgets.amounts_for('2026-09')[category.id][0] == 450


def test_module_loan_workflow_records_its_terms_and_can_feed_later_steps(full_devices):
    from lightning.planning.loan_actions import create_purchase
    home, peer, identities = full_devices
    bank = next(account for account in peer.adapter.c.accounts.list() if account.name == 'Bank')
    with FormCapture(peer) as form:
        item = create_purchase(form.container.planning, name='Laptop', price='12000', fee='600', months='12',
                               first_date='01/09/2026', account_id=bank.id)
        form.container.planning.set_amount(item, '1100')
        wire = form.finish(identities[1].sign)
    accept(home, peer, wire)
    assert peer.db.scalar("SELECT COUNT(*) FROM planned_items WHERE name='Laptop'") == 1
    assert peer.db.scalar('SELECT COUNT(*) FROM installment_purchases') == 1


def test_named_salary_workflow_is_not_duplicated_as_internal_planning_calls(full_devices):
    from lightning.workflows.salary_setup import set_up_salary
    home, peer, identities = full_devices
    bank = next(account for account in peer.adapter.c.accounts.list() if account.name == 'Bank')
    with FormCapture(peer) as form:
        set_up_salary(form.container, bank.id, '20000', '25')
        wire = form.finish(identities[1].sign)
    action = unpack(wire)['body']['groups']['action']
    assert [call['command'] for call in action['calls']] == ['salary.setup']
    accept(home, peer, wire)


@pytest.mark.parametrize('damage', ['forward', 'slot', 'entity', 'recursive'])
def test_workflow_cannot_choose_arbitrary_accessors_or_forward_references(full_devices, damage):
    home, peer, identities = full_devices
    wire = reserve_action(peer, identities[1].sign)
    action = deepcopy(unpack(wire)['body']['groups']['action'])
    arguments = action['calls'][0]['arguments']
    handle = next(iter(arguments['bindings']))
    if damage == 'forward':
        arguments['bindings'][handle]['step'] = 1
    elif damage == 'slot':
        arguments['bindings'][handle]['slot'] = '__class__'
    elif damage == 'entity':
        arguments['bindings'][handle]['entity'] = 'accounts'
    else:
        arguments['steps'][1] = dict(command='workflow.compose', arguments=deepcopy(arguments))
    with pytest.raises(JournalError):
        validate(peer.adapter.c, peer.adapter.graph, action)


def test_failure_after_a_created_result_rolls_back_all_money_and_has_one_decision(full_devices, tmp_path):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    wire = reserve_action(peer, identities[1].sign)
    original = deepcopy(unpack(wire)['body'])
    original['groups']['action']['calls'][0]['arguments']['steps'][1]['arguments']['amount'] = '-1'
    # A distinct fresh origin keeps the prefix contiguous for this fault case.
    from lightning.sync.identity import load_or_create
    from lightning.sync.journal.codec import seal
    identity = load_or_create(tmp_path/'composition-fault-identity', 'Fault test')
    origin = dict(device=identity.device_id, incarnation=str(uuid4()), seq=1)
    home.approve_origin(origin['device'], origin['incarnation'], identity.public_key)
    original['origin'] = origin
    bad = seal(original, identity.sign)
    home.receive(bad)
    commit, = home.process()
    assert unpack(commit)['body']['outcome'] == 'rejected'
    assert home.store.fingerprint() == before
    home.receive(bad)
    assert home.process() == []
    assert home.store.cursor()['revision'] == 1
