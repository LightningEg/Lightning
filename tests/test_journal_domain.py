"""Full-domain replay: exact money, different local IDs and atomic refusal."""
import copy
import json
from decimal import Decimal
from uuid import uuid4

import pytest

from lightning.bootstrap import build
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.domain import DomainGraph, ID_TABLES, TABLES, validate_effect


@pytest.fixture
def graphs():
    home, replica = build(':memory:'), build(':memory:')
    home.account_flows.open_account('Bank', 'BANK', '2026-01-01', '100000')
    home.account_flows.open_account('Broker', 'BROKERAGE', '2026-01-01', '10000')
    home.assets.create_investment('Stock', 'STOCK', 'JRN')
    home.db.execute('CREATE TABLE journal_ids(entity TEXT,uuid TEXT,local_id INTEGER,PRIMARY KEY(entity,uuid),UNIQUE(entity,local_id))')
    profile = str(uuid4())
    a = DomainGraph(home.db, profile)
    a.initialize()
    home.db.conn.backup(replica.db.conn)
    # Rewrite every integer identity and every FK, retaining logical UUIDs.
    replica.db.execute('PRAGMA foreign_keys=OFF')
    with replica.db.transaction():
        from lightning.sync.journal.domain import _reference
        for table, spec in TABLES.items():
            for column in spec['columns']:
                if table != 'zakat_settings' and ((table in ID_TABLES and column == 'id') or _reference(table, column)):
                    replica.db.execute(f'UPDATE {table} SET {column}={column}+1000')
        replica.db.execute("UPDATE journal_ids SET local_id=local_id+1000 WHERE entity!='zakat_settings'")
    replica.db.execute('PRAGMA foreign_keys=ON')
    b = DomainGraph(replica.db, profile)
    assert not replica.db.all('PRAGMA foreign_key_check')
    assert a.fingerprint() == b.fingerprint()
    yield home, replica, a, b
    home.db.close()
    replica.db.close()


def replay(graphs, action):
    home, replica, a, b = graphs
    before = a.snapshot()
    with home.db.transaction():
        result = action(home)
        effect = a.difference(before)
    b.apply(effect)
    assert a.fingerprint() == b.fingerprint()
    assert not replica.db.all('PRAGMA foreign_key_check')
    return result, effect


def test_investment_buy_sell_exact_effects_never_execute_replica_services(graphs, monkeypatch):
    home, replica, a, b = graphs
    broker = home.accounts.find_by_text('Broker')
    stock = home.assets.get_asset_by_code('STK:JRN')
    monkeypatch.setattr(replica.investments, 'buy', lambda *args, **kw: pytest.fail('Replay called a service'))
    txn, effect = replay(graphs, lambda c: c.investments.buy('2026-09-01', broker.id, stock.id, '10', '100.01'))
    replica_broker = b.local('accounts', a.uid('accounts', broker.id))
    assert replica.reporting.account_balance(replica_broker) == Decimal('8999.90')
    replay(graphs, lambda c: c.investments.sell('2026-09-02', broker.id, stock.id, '2', '110.02'))
    assert replica.reporting.account_balance(replica_broker) == Decimal('9219.94')
    assert replica.investments.holding(replica_broker, b.local('financial_assets', a.uid('financial_assets', stock.id))) == 8
    assert {'transactions', 'ledger_entries'} <= {row['table'] for row in effect['rows']}


def test_budgets_embedded_category_ids_and_rule_account_ids(graphs):
    home, replica, a, b = graphs
    food = home.categories.get_by_code('EXP.PERSONAL.FOOD').id
    replay(graphs, lambda c: c.budgets.set_budget(food, '2026-09', '100.01'))
    replay(graphs, lambda c: c.budgets.set_one_off(food, True))
    replica_food = b.local('categories', a.uid('categories', food))
    assert replica_food in replica.budgets.one_off_ids()
    assert json.loads(replica.settings.get('budget_one_off_exclusions')) == [replica_food]
    bank = home.accounts.find_by_text('Bank').id
    values = {'match': 'all', 'counterparty_op': 'contains', 'counterparty': 'Shop',
              'account_id': str(bank), 'category_id': str(food)}
    replay(graphs, lambda c: c.rules.save(values))
    assert replica.rules.outcome('Shop', account_id=b.local('accounts', a.uid('accounts', bank))).category_id == replica_food


def test_deleted_primary_key_reuse_does_not_resurrect_uuid(graphs):
    home, replica, a, b = graphs
    reserve, effect = replay(graphs, lambda c: c.reserves.create('First', '10'))
    first = home.db.scalar('SELECT id FROM cash_reserves WHERE name=?', ('First',))
    old_uuid = a.uid('cash_reserves', first)
    replay(graphs, lambda c: c.reserves.delete(first))
    assert home.db.scalar('SELECT local_id FROM journal_ids WHERE uuid=?', (old_uuid,)) is None
    replay(graphs, lambda c: c.reserves.create('Second', '20'))
    second = home.db.scalar('SELECT id FROM cash_reserves WHERE name=?', ('Second',))
    assert second > first  # Historical references reserve the deleted ID.
    assert a.uid('cash_reserves', second) != old_uuid
    with pytest.raises(JournalError, match='Missing confirmed'):
        b.local('cash_reserves', old_uuid)


def test_new_reserve_does_not_change_past_allocations(monkeypatch):
    from datetime import date
    import lightning.reserves as module
    c = build(':memory:')
    current = [date(2026, 9, 1)]
    monkeypatch.setattr(module, 'today', lambda: current[0])
    monkeypatch.setattr(module, 'now_iso', lambda: current[0].isoformat() + 'T12:00:00')
    try:
        first = c.reserves.create('First', '10')['id']
        c.reserves.allocate(first, '10')
        current[0] = date(2026, 9, 2)
        c.reserves.delete(first)
        current[0] = date(2026, 9, 3)
        second = c.reserves.create('Second', '20')['id']
        c.reserves.allocate(second, '20')
        assert second != first
        assert c.reserves.allocation_at('2026-09-01') == Decimal('10')
        assert c.reserves.allocation_at('2026-09-02') == Decimal('0')
        assert c.reserves.allocation_at('2026-09-03') == Decimal('20')
    finally:
        c.db.close()


def test_effect_refuses_unknown_fields_sql_and_wrong_before_without_changes(graphs):
    home, replica, a, b = graphs
    before = a.snapshot()
    home.budgets.set_budget(home.categories.get_by_code('EXP.PERSONAL.FOOD').id, '2026-09', '12.34')
    effect = a.difference(before)
    fingerprint = b.fingerprint()
    for mutate in (lambda e: e['rows'][0].update(table='settings; DROP TABLE accounts'),
                   lambda e: e['rows'][0]['values'].update(sql='DELETE FROM accounts'),
                   lambda e: e.update(before='0' * 64),
                   lambda e: e['rows'].append(copy.deepcopy(e['rows'][0]))):
        bad = copy.deepcopy(effect)
        mutate(bad)
        with pytest.raises(JournalError):
            b.apply(bad)
        assert b.fingerprint() == fingerprint
    b.apply(effect)
    with pytest.raises(JournalError, match='differs'):
        b.apply(effect)


def test_int64_and_real_columns_round_trip_without_float_money(graphs):
    home, replica, a, b = graphs
    def change(c):
        c.investments.set_liquidation_factor(c.assets.get_class_by_code('STOCK').id, '73.25')
        c.db.execute("INSERT INTO budgets(category_id,month,amount_e6,created_at,updated_at) VALUES(?,?,?,?,?)",
                     (c.categories.get_by_code('EXP.PERSONAL.FOOD').id, '2026-09', 2**60 + 1, 'now', 'now'))
    _, effect = replay(graphs, change)
    assert replica.db.scalar('SELECT amount_e6 FROM budgets') == 2**60 + 1
    row = next(row for row in effect['rows'] if row['table'] == 'budgets')
    row['values']['amount_e6'] = str(2**63)
    with pytest.raises(JournalError, match='exceeds'):
        validate_effect(effect)


def test_replay_failure_rolls_back_rows_and_new_uuid_allocations(graphs):
    home, replica, a, b = graphs
    before = a.snapshot()
    home.reserves.create('Trip', '20')
    effect = a.difference(before)
    effect['after'] = '0' * 64
    ids = [tuple(row) for row in replica.db.all('SELECT * FROM journal_ids ORDER BY entity,uuid')]
    fingerprint = b.fingerprint()
    with pytest.raises(JournalError, match='failed verification'):
        b.apply(effect)
    assert b.fingerprint() == fingerprint
    assert [tuple(row) for row in replica.db.all('SELECT * FROM journal_ids ORDER BY entity,uuid')] == ids


def test_local_preferences_and_sms_cursors_are_not_financial_state(graphs):
    home, replica, a, b = graphs
    fingerprint = b.fingerprint()
    replica.settings.set('locale', 'ar')
    replica.settings.set('sms_seen', '[123]')
    replica.settings.set('budget_bulk_undo', '{"local_ids":[12]}')
    assert b.fingerprint() == fingerprint
    replay(graphs, lambda c: c.budgets.set_budget(c.categories.get_by_code('EXP.PERSONAL.FOOD').id, '2026-09', '20'))
    assert replica.settings.get('locale') == 'ar'
