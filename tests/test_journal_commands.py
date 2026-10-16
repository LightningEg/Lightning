"""Signed service commands never change a replica until the home confirms."""
import os
from decimal import Decimal
from uuid import uuid4

import pytest

from lightning.bootstrap import build
from lightning.sync.identity import load_or_create
from lightning.sync.journal.codec import JournalError, canonical, origin_id, unpack
from lightning.sync.journal.commands import COMMANDS, REFS, method, prepare
from lightning.sync.journal.domain import TABLES
from lightning.sync.journal.finance import initialize, attach
from lightning.sync.journal.full import enable
from lightning.sync.journal.home import JournalHome


@pytest.fixture
def full_devices(tmp_path):
    identities = [load_or_create(tmp_path / f'identity-{i}', f'Device {i}') for i in range(2)]
    containers = [build(tmp_path / f'ledger-{i}.db', key=os.urandom(32)) for i in range(2)]
    c = containers[0]
    c.currencies.register('USD')
    c.account_flows.open_account('Bank', 'BANK', '2026-01-01', '100000')
    c.account_flows.open_account('Broker', 'BROKERAGE', '2026-01-01', '10000')
    c.account_flows.open_account('Certificate', 'DEPOSIT', '2026-01-01', '0', institution='CIB')
    c.account_flows.open_account('Circle', 'GAMEYA', '2026-01-01', '0')
    c.assets.create_investment('Stock', 'STOCK', 'JRN')
    store = initialize(c, profile=str(uuid4()), generation=str(uuid4()), device=identities[0].device_id,
                       incarnation=str(uuid4()), home_key=identities[0].public_key, origin_key=identities[0].public_key,
                       role='home', dummy_profile=True)
    enable(store)
    c.db.conn.backup(containers[1].db.conn)
    config = store.config | dict(device=identities[1].device_id, incarnation=str(uuid4()), origin_key=identities[1].public_key, role='replica')
    containers[1].db.execute('UPDATE journal_meta SET config=?', (canonical(config).decode(),))
    from lightning.sync.journal.domain import ID_TABLES, _reference
    containers[1].db.execute('PRAGMA foreign_keys=OFF')
    with containers[1].db.transaction():
        for table, spec in TABLES.items():
            for column in spec['columns']:
                if table != 'zakat_settings' and ((table in ID_TABLES and column == 'id') or _reference(table, column)):
                    containers[1].db.execute(f'UPDATE {table} SET {column}={column}+1000')
        containers[1].db.execute("UPDATE journal_ids SET local_id=local_id+1000 WHERE entity!='zakat_settings'")
    containers[1].db.execute('PRAGMA foreign_keys=ON')
    peer = attach(containers[1])
    home = JournalHome(store, identities[0].sign)
    for s, identity in zip((store, peer), identities):
        home.approve_origin(identity.device_id, s.config['incarnation'], identity.public_key)
    yield home, peer, identities
    for container in containers:
        container.db.close()


def submit(full_devices, command_name, **arguments):
    home, peer, identities = full_devices
    before = peer.fingerprint()
    wire = peer.adapter.save_action([dict(command=command_name, arguments=arguments)], identities[1].sign)
    assert peer.fingerprint() == before
    home.receive(wire)
    commits = home.process()
    assert len(commits) == 1
    assert unpack(commits[0])['body']['outcome'] == 'accepted'
    peer.apply(commits[0])
    assert peer.fingerprint() == home.store.fingerprint()
    return wire


def test_registry_has_only_real_explicit_methods_and_tables(full_devices):
    home, peer, _ = full_devices
    assert len(COMMANDS) > 100
    for command in COMMANDS:
        assert callable(method(home.store.adapter.c, command))
    assert set(REFS.values()) <= set(TABLES)
    for command in ('db.execute', 'accounts.repo.delete', 'transactions._create', 'settings.set'):
        with pytest.raises(JournalError):
            prepare(peer.adapter.c, peer.adapter.graph, [dict(command=command, arguments={})])


def test_signed_investment_trade_and_duplicate_delivery_are_exactly_once(full_devices):
    home, peer, identities = full_devices
    c = peer.adapter.c
    broker, stock = c.accounts.find_by_text('Broker'), c.assets.get_asset_by_code('STK:JRN')
    wire = submit(full_devices, 'investments.buy', date='2026-09-01', account_id=broker.id,
                  asset_id=stock.id, quantity='10', price='100.01')
    assert c.reporting.account_balance(broker.id) == Decimal('8999.90')
    assert home.receive(wire) == 'accepted'
    assert home.process() == []
    assert c.reporting.account_balance(broker.id) == Decimal('8999.90')
    submit(full_devices, 'investments.sell', date='2026-09-02', account_id=broker.id,
           asset_id=stock.id, quantity='2', price='110.02')
    assert c.reporting.account_balance(broker.id) == Decimal('9219.94')


def test_bill_and_loan_payments_move_money_once(full_devices):
    home, peer, _ = full_devices
    c = peer.adapter.c
    bank = c.accounts.find_by_text('Bank').id
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    for kind, amount in [('BILL', '123.45'), ('LOAN', '200.01')]:
        submit(full_devices, 'planning.create', kind=kind, name=kind, amount=amount,
               start_date='2026-09-01', frequency='MONTHLY', payment_count='6', account_id=bank, category_id=food)
        item = c.db.scalar('SELECT id FROM planned_items WHERE name=?', (kind,))
        before = c.reporting.account_balance(bank)
        submit(full_devices, 'planning.record_payment', item_id=item, due_date='2026-09-01', date_paid='2026-09-01',
               amount=amount, account_id=bank)
        assert c.reporting.account_balance(bank) == before - Decimal(amount)
    assert c.reporting.account_balance(bank) == Decimal('99676.54')


def test_budget_reserve_fx_and_reconciliation_commands(full_devices):
    home, peer, _ = full_devices
    c = peer.adapter.c
    bank = c.accounts.find_by_text('Bank').id
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    submit(full_devices, 'budgets.set_budget', category_id=food, month='2026-09', amount='123.45')
    submit(full_devices, 'budgets.set_one_off', category_id=food, one_off=True)
    submit(full_devices, 'reserves.create', name='Trip', target='1000')
    reserve = c.db.scalar("SELECT id FROM cash_reserves WHERE name='Trip'")
    submit(full_devices, 'reserves.allocate', reserve_id=reserve, amount='10.01')
    assert c.reporting.account_balance(bank) == Decimal('100000')
    submit(full_devices, 'fx.save', currency='USD', day='2026-09-01', rate='50.12')
    submit(full_devices, 'reconciliation.adjust', account_id=bank, through='2026-09-01', bank_balance=Decimal('99999.99'))
    assert c.reporting.account_balance(bank) == Decimal('99999.99')


def test_certificate_and_gameya_use_normal_home_services(full_devices):
    home, peer, _ = full_devices
    c = peer.adapter.c
    bank = c.accounts.find_by_text('Bank').id
    cd, circle = c.accounts.find_by_text('Certificate').id, c.accounts.find_by_text('Circle').id
    submit(full_devices, 'deposits.purchase', account_id=cd, name='One year', start_date='2026-09-01',
           lockup_end_date='2026-10-01', maturity_date='2027-09-01', principal='5000', annual_rate='12',
           interest_method='SIMPLE', payout_frequency='AT_MATURITY', compounding_frequency='MONTHLY',
           destination_account_id=bank, funding_account_id=bank)
    assert c.reporting.account_balance(bank) == Decimal('95000')
    submit(full_devices, 'gameya.save_terms', account_id=circle, organiser='Office', members=10,
           installment='1000', first_date='2026-09-01', my_turn=3, funding_account_id=bank, payout_account_id=bank)
    submit(full_devices, 'gameya.record_instalment', account_id=circle, date_value='2026-09-01')
    assert c.reporting.account_balance(bank) == Decimal('94000')


def test_whole_multi_command_action_rolls_back_on_financial_refusal(full_devices):
    home, peer, identities = full_devices
    before = home.store.fingerprint()
    c = peer.adapter.c
    bank = c.accounts.find_by_text('Bank').id
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    calls = [dict(command='reserves.create', arguments=dict(name='Must roll back', target='10')),
             dict(command='transactions.record_outflow', arguments=dict(date='2026-09-01', account_id=bank,
                  category_id=food, amount='-1'))]
    wire = peer.adapter.save_action(calls, identities[1].sign)
    home.receive(wire)
    commit, = home.process()
    assert unpack(commit)['body']['outcome'] == 'rejected'
    peer.apply(commit)
    assert home.store.fingerprint() == before == peer.fingerprint()
    assert not c.db.scalar("SELECT 1 FROM cash_reserves WHERE name='Must roll back'")


def test_stale_financial_form_requires_review_and_cannot_revert_new_values(full_devices):
    home, peer, identities = full_devices
    c = peer.adapter.c
    broker, stock = c.accounts.find_by_text('Broker'), c.assets.get_asset_by_code('STK:JRN')
    wire = peer.adapter.save_action([dict(command='investments.buy', arguments=dict(date='2026-09-01', account_id=broker.id,
                                    asset_id=stock.id, quantity='1', price='100'))], identities[1].sign)
    a = home.store.adapter
    local_broker = a.local('accounts', peer.adapter.uid('accounts', broker.id))
    own = a.save_action([dict(command='accounts.set_spendable', arguments=dict(account_id=local_broker, choice=False))], identities[0].sign)
    home.receive(own)
    commit, = home.process()
    peer.apply(commit)
    home.receive(wire)
    assert home.process() == []
    assert home.status(origin_id(unpack(wire)['body']['origin']))['status'] == 'review'
    assert c.reporting.account_balance(broker.id) == 10000


def test_direct_financial_writes_remain_blocked_on_both_roles(full_devices):
    home, peer, _ = full_devices
    for store in (home.store, peer):
        with pytest.raises(store.db.driver.DatabaseError):
            store.adapter.c.reserves.create('Bypass', '10')


def test_full_checkpoint_repairs_all_domains_and_preserves_pending_queue(full_devices, tmp_path):
    from lightning.sync.journal.snapshots import export, repair
    home, peer, identities = full_devices
    food = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    pending = peer.adapter.save_action([dict(command='budgets.set_budget', arguments=dict(category_id=food,
                                      month='2026-09', amount='10.01'))], identities[1].sign)
    for batch in range(9):
        wire = home.store.adapter.save_action([dict(command='reserves.create', arguments=dict(name=f'Trip {batch}-{i}', target='10.01'))
                                              for i in range(32)], identities[0].sign)
        home.receive(wire)
        commit, = home.process()
        assert unpack(commit)['body']['outcome'] == 'accepted'
    source = tmp_path / 'full-checkpoint.db'
    manifest = export(home.store, source, identities[0].sign)
    repair(peer, source, manifest, source_key=home.db.copy_key())
    assert peer.pending() == [pending]
    assert peer.db.scalar('SELECT next_seq FROM journal_meta') == 2
    assert peer.db.scalar('SELECT COUNT(*) FROM cash_reserves') == 288
    assert peer.fingerprint() == home.store.fingerprint()
    home.receive(pending)
    commit, = home.process()
    peer.apply(commit)
    assert peer.fingerprint() == home.store.fingerprint()


def test_full_checkpoint_fault_preserves_original_domain_and_queue(full_devices, tmp_path):
    from lightning.sync.journal.snapshots import export, repair
    home, peer, identities = full_devices
    wire = home.store.adapter.save_action([dict(command='reserves.create', arguments=dict(name='Trip', target='10'))], identities[0].sign)
    home.receive(wire)
    home.process()
    source = tmp_path / 'full-checkpoint.db'
    manifest = export(home.store, source, identities[0].sign)
    before = peer.fingerprint(), peer.cursor(), peer.pending()
    def fault(phase):
        if phase == 'snapshot_cursor':
            raise RuntimeError('power interruption')
    with pytest.raises(RuntimeError, match='power interruption'):
        repair(peer, source, manifest, source_key=home.db.copy_key(), fault=fault)
    assert (peer.fingerprint(), peer.cursor(), peer.pending()) == before
    repair(peer, source, manifest, source_key=home.db.copy_key())
    assert peer.fingerprint() == home.store.fingerprint()


def test_cash_only_device_cannot_accept_full_domain_effects(full_devices):
    from lightning.sync.journal.compatibility import capabilities, check, UpdateRequired
    home, peer, _ = full_devices
    full = capabilities(home.store)
    cash = full | dict(effects=[1], entry_kinds={'transaction.add': 1})
    with pytest.raises(UpdateRequired):
        check(cash, full, [])


def test_original_values_are_bound_to_preconditions_and_old_command_queues_remain_valid(full_devices):
    from copy import deepcopy
    from lightning.sync.journal.commands import validate
    from lightning.sync.journal.compatibility import capabilities, check, UpdateRequired
    home, peer, identities = full_devices
    category = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD')
    action = prepare(peer.adapter.c, peer.adapter.graph, [dict(command='categories.update',
        arguments=dict(category_id=category.id, name='Coffee'))])
    original = deepcopy(action)
    assert any(row['table'] == 'categories' and row['values']['name'] == category.name for row in action['baseline'])
    next(row for row in action['baseline'] if row['table'] == 'categories')['values']['name'] = 'Forged baseline'
    with pytest.raises(JournalError, match='Original values'):
        validate(peer.adapter.c, peer.adapter.graph, action)
    legacy = {key: value for key, value in original.items() if key != 'baseline'}
    wire = peer.save(kind='action.add', record=str(uuid4()), groups=dict(action=legacy), bases=dict(action=None), signer=identities[1].sign)
    assert unpack(wire)['body']['kind_version'] == 1
    check(capabilities(peer), capabilities(home.store), [wire])
    home.receive(wire)
    assert home.process()
    modern = peer.adapter.save_action([dict(command='categories.update', arguments=dict(category_id=category.id, name='Dinner'))], identities[1].sign)
    assert unpack(modern)['body']['kind_version'] == 2
    old_home = capabilities(home.store)
    old_home['entry_kinds'] = old_home['entry_kinds'] | {'action.add': 1}
    with pytest.raises(UpdateRequired, match='Update the home'):
        check(capabilities(peer), old_home, [modern])


def test_cash_form_tokens_refresh_after_general_financial_command(full_devices):
    from lightning.sync.journal.device import JournalDevice
    home, peer, identities = full_devices
    device = JournalDevice(peer, identities[1])
    bank = peer.adapter.c.accounts.find_by_text('Bank').id
    food = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    values = dict(money=dict(account=peer.adapter.uid('accounts', bank), other_account=None, date='2026-09-01', amount='-10.00'),
                  category=dict(category=peer.adapter.uid('categories', food), splits=[]),
                  details=dict(counterparty='', notes='', description=''))
    wire = device.save(values)
    home.receive(wire)
    commit, = home.process()
    peer.apply(commit)
    record = unpack(wire)['body']['record']
    original = peer.record(record)
    txn = peer.adapter.local('transactions', record)
    draft = device.draft(record)
    submit(full_devices, 'transactions.update_in_account', txn_id=txn, date='2026-09-01', account_id=bank,
           amount='-20.01', category_id=food)
    updated = peer.record(record)
    assert updated['groups']['money']['amount'] == '-20.01'
    assert updated['tokens']['money'] != original['tokens']['money']
    assert updated == home.store.record(record)
    stale = device.submit_draft(draft, values | dict(money=values['money'] | dict(amount='-12.00')))
    home.receive(stale)
    assert home.process() == []
    assert home.status(origin_id(unpack(stale)['body']['origin']))['status'] == 'review'
    assert peer.adapter.c.reporting.account_balance(bank) == Decimal('99979.99')


def test_full_domain_settings_normalize_embedded_id_lists(full_devices):
    home, peer, _ = full_devices
    import json
    category = peer.adapter.c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    submit(full_devices, 'profile.set_financial_setting', key='budget_tracked_categories', value=json.dumps([category]))
    home_id = home.store.adapter.local('categories', peer.adapter.uid('categories', category))
    assert json.loads(peer.adapter.c.settings.get('budget_tracked_categories')) == [category]
    assert json.loads(home.store.adapter.c.settings.get('budget_tracked_categories')) == [home_id]
    submit(full_devices, 'profile.set_financial_setting', key='budget_suppressed_categories', value=json.dumps({str(category): 'never'}))
    assert json.loads(home.store.adapter.c.settings.get('budget_suppressed_categories')) == {str(home_id): 'never'}


def test_installment_purchase_and_early_payment_are_journal_commands(full_devices):
    home, peer, _ = full_devices
    c = peer.adapter.c
    bank = c.accounts.find_by_text('Bank').id
    submit(full_devices, 'loans.create_purchase', name='Laptop', price='12000', fee='0', months=12,
           first_date='2026-09-01', account_id=bank)
    item = c.db.scalar("SELECT id FROM planned_items WHERE name='Laptop'")
    assert c.db.scalar('SELECT COUNT(*) FROM installment_purchases') == 1
    submit(full_devices, 'loans.record_early_payment', item_id=item, principal='100.01', fee='1.00',
           date_paid='2026-09-01', account_id=bank, expected_remaining='12000')
    assert c.reporting.account_balance(bank) == Decimal('99898.99')


def test_large_confirmed_register_does_not_exhaust_command_preconditions(full_devices, tmp_path):
    from lightning.sync.journal.snapshots import export, repair
    home, peer, identities = full_devices
    c = home.store.adapter.c
    bank = c.accounts.find_by_text('Bank').id
    food = c.categories.get_by_code('EXP.PERSONAL.FOOD').id
    # A privileged dummy fixture representing a long baseline, not a write API.
    with home.db.transaction(), home.store.adapter.writing():
        for index in range(300):
            c.transactions.record_outflow('2026-09-01', bank, '1', food, description=f'Baseline {index}')
        home.store.fingerprint()
    source = tmp_path / 'large-baseline.db'
    manifest = export(home.store, source, identities[0].sign)
    repair(peer, source, manifest, source_key=home.db.copy_key())
    pc = peer.adapter.c
    before = pc.reporting.account_balance(pc.accounts.find_by_text('Bank').id)
    wire = submit(full_devices, 'transactions.record_outflow', date='2026-09-02', account_id=pc.accounts.find_by_text('Bank').id,
                  category_id=pc.categories.get_by_code('EXP.PERSONAL.FOOD').id, amount='1.01')
    assert len(unpack(wire)['body']['groups']['action']['preconditions']) < 10
    assert pc.reporting.account_balance(pc.accounts.find_by_text('Bank').id) == before - Decimal('1.01')


def test_concurrent_creation_of_same_fx_point_requires_review(full_devices):
    home, peer, identities = full_devices
    args = dict(currency='USD', day='2026-09-01', rate='50.12')
    wire = peer.adapter.save_action([dict(command='fx.save', arguments=args)], identities[1].sign)
    own = home.store.adapter.save_action([dict(command='fx.save', arguments=args | dict(rate='51.23'))], identities[0].sign)
    home.receive(own)
    commit, = home.process()
    peer.apply(commit)
    home.receive(wire)
    assert home.process() == []
    assert home.status(origin_id(unpack(wire)['body']['origin']))['status'] == 'review'
    assert peer.adapter.c.fx.list()[0]['rate'] == Decimal('51.23')


def test_typed_decimal_arguments_use_normal_financial_input_bounds(full_devices):
    from lightning.core.errors import ValidationError
    home, peer, identities = full_devices
    bank = peer.adapter.c.accounts.find_by_text('Bank').id
    before = peer.db.scalar('SELECT next_seq FROM journal_meta'), peer.fingerprint()
    for value in ('1e999999999', 'NaN', '99999999999999999999999'):
        with pytest.raises((JournalError, ValidationError)):
            peer.adapter.save_action([dict(command='reconciliation.adjust', arguments=dict(account_id=bank,
                                     through='2026-09-01', bank_balance=value))], identities[1].sign)
    assert (peer.db.scalar('SELECT next_seq FROM journal_meta'), peer.fingerprint()) == before


def test_numeric_overflow_after_a_financial_write_rolls_back_and_gets_one_decision(full_devices, monkeypatch):
    home, peer, identities = full_devices
    wire = peer.adapter.save_action([dict(command='reserves.create', arguments=dict(name='Overflow', target='10'))], identities[1].sign)
    before = home.store.fingerprint()
    original = home.store.adapter.c.reserves.create
    calls = []
    def overflow(*args, **kwargs):
        original(*args, **kwargs)
        calls.append(True)
        raise OverflowError('scaled amount exceeds storage')
    monkeypatch.setattr(home.store.adapter.c.reserves, 'create', overflow)
    home.receive(wire)
    commit, = home.process()
    assert unpack(commit)['body']['outcome'] == 'rejected'
    peer.apply(commit)
    assert home.store.fingerprint() == before == peer.fingerprint()
    assert not home.db.scalar("SELECT COUNT(*) FROM cash_reserves WHERE name='Overflow'")
    assert home.receive(wire) == 'rejected'
    assert home.process() == []
    assert calls == [True]
