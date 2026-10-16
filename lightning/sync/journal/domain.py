"""Typed financial graph effects. Only the home executes financial services.

The contract is a fixed, local schema, not SQL supplied by another device. All
integer storage values travel as decimal text (including full SQLite int64s).
References travel as UUIDs; each receiver owns its integer primary keys.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from uuid import UUID, uuid4, uuid5

from .codec import JournalError, canonical, digest, fields, hash_value, uuid
from .domain_schema import SCHEMA_VERSION, TABLES

ID_TABLES = frozenset(name for name, spec in TABLES.items()
                      if spec['columns'].get('id', {}).get('pk') == 1)
ID_SETTINGS = frozenset(('budget_income_categories', 'budget_one_off_exclusions',
                         'budget_tracked_categories'))
LOCAL_SETTINGS = frozenset(('locale', 'privacy_mode', 'rules_apply_undo'))
INTEGER = re.compile(r'(?:0|-[1-9][0-9]*|[1-9][0-9]*)\Z')
HISTORICAL_REFS = {('reserve_allocation_history', 'reserve_id'): 'cash_reserves'}


def financial_setting(key):
    # SMS cursors, dismissed hints, caches and legacy undo contain device-local
    # IDs/state. They are not part of a confirmed financial checkpoint.
    return (key.startswith(('budget_', 'financial_health_')) and key != 'budget_bulk_undo'
            or key in {'base_currency', 'profile_currencies', 'cash_funding_enabled',
                       'investment_planner_mode', 'investment_monthly_goal',
                       'income_from_recurring', 'income_raise_declined', 'zakat_enabled'})


def _root(table, column):
    """Follow a shared primary key, e.g. a physical item's asset_id."""
    seen = set()
    while (table, column) not in seen:
        seen.add((table, column))
        if table in ID_TABLES and column == 'id':
            return table
        ref = TABLES[table]['refs'].get(column)
        if ref is None:
            return None
        table, column = ref['table'], ref['column']
    raise JournalError('Cyclic reference schema')


def _reference(table, column):
    ref = TABLES[table]['refs'].get(column)
    return _root(ref['table'], ref['column']) if ref else None


def _integer(value):
    if type(value) is not str or len(value) > 20 or not INTEGER.fullmatch(value):
        raise JournalError('Invalid exact integer storage value')
    result = int(value)
    if not -(2**63) <= result < 2**63:
        raise JournalError('Integer exceeds ledger storage')
    return result


def _value(table, column, value):
    spec = TABLES[table]['columns'][column]
    if value is None:
        if not spec['nullable'] or spec['pk']:
            raise JournalError('Missing required financial value')
        return
    if (table in ID_TABLES and column == 'id') or _reference(table, column):
        uuid(value)
    elif spec['type'] == 'INTEGER':
        _integer(value)
    elif spec['type'] == 'REAL':
        if type(value) is not str or len(value) > 32:
            raise JournalError('Invalid real storage value')
        try:
            parsed = float(value)
        except ValueError as error:
            raise JournalError('Invalid real storage value') from error
        if not math.isfinite(parsed) or repr(parsed) != value:
            raise JournalError('Noncanonical real storage value')
    elif type(value) is not str or len(value) > 16384:
        raise JournalError('Invalid financial text')


def _key(table, values):
    return {column: values[column] for column, spec in TABLES[table]['columns'].items() if spec['pk']}


def _embedded(table, values):
    """Validate references in legacy text storage, rather than copying local IDs."""
    if table == 'settings':
        if not financial_setting(values['key']):
            raise JournalError('Device preferences cannot be replicated')
        if values['key'] in ID_SETTINGS:
            try:
                ids = json.loads(values['value'])
            except (TypeError, ValueError) as error:
                raise JournalError('Invalid category selection') from error
            if type(ids) is not list or len(ids) > 256 or any(type(i) is not str for i in ids):
                raise JournalError('Invalid category selection')
            for value in ids:
                uuid(value)
            if ids != sorted(set(ids)):
                raise JournalError('Invalid category selection')
        if values['key'] == 'budget_suppressed_categories':
            try:
                months = json.loads(values['value'])
            except (TypeError, ValueError) as error:
                raise JournalError('Invalid suppressed categories') from error
            if type(months) is not dict or len(months) > 256:
                raise JournalError('Invalid suppressed categories')
            for category, until in months.items():
                uuid(category)
                if type(until) is not str or until != 'never' and not re.fullmatch(r'[0-9]{4}-[0-9]{2}', until):
                    raise JournalError('Invalid suppressed categories')
    if table == 'rule_conditions' and values['field'] == 'account':
        uuid(values['value'])


def validate_effect(effect):
    fields(effect, ('schema', 'before', 'after', 'rows'))
    if type(effect['schema']) is not int or effect['schema'] != 2:
        raise JournalError('Unsupported financial graph schema')
    hash_value(effect['before'])
    hash_value(effect['after'])
    if type(effect['rows']) is not list or not 0 <= len(effect['rows']) <= 256:
        raise JournalError('Invalid financial graph effect count')
    seen = set()
    for row in effect['rows']:
        fields(row, ('table', 'key', 'before', 'values'))
        table = row['table']
        if type(table) is not str or table not in TABLES:
            raise JournalError('Unsupported financial table')
        columns = TABLES[table]['columns']
        fields(row['key'], [name for name, spec in columns.items() if spec['pk']])
        for name, value in row['key'].items():
            _value(table, name, value)
        identity = (table, canonical(row['key']))
        if identity in seen:
            raise JournalError('Duplicate financial graph effect')
        seen.add(identity)
        if row['before'] is not None:
            hash_value(row['before'])
        values = row['values']
        if values is None:
            if row['before'] is None:
                raise JournalError('Deletion needs an existing record')
            if table == 'settings' and not financial_setting(row['key']['key']):
                raise JournalError('Device preferences cannot be replicated')
            continue
        fields(values, columns)
        for name, value in values.items():
            _value(table, name, value)
        if _key(table, values) != row['key']:
            raise JournalError('Financial key differs from record')
        _embedded(table, values)
    canonical(effect)


class DomainGraph:
    def __init__(self, db, profile):
        self.db, self.namespace = db, UUID(profile)
        if db.scalar('SELECT MAX(version) FROM schema_migrations') != SCHEMA_VERSION:
            raise JournalError('A compatible financial schema is required')
        for table, spec in TABLES.items():
            actual = {row['name']: (row['type'], row['pk']) for row in db.all(f'PRAGMA table_info({table})')}
            expected = {name: (column['type'], column['pk']) for name, column in spec['columns'].items()}
            if actual != expected:
                raise JournalError('Financial schema differs from the replication contract')

    def initialize(self):
        """Run once on a verified baseline; subsequent snapshots carry these IDs."""
        with self.db.transaction():
            self.db.execute('CREATE TABLE IF NOT EXISTS journal_history_refs('
                            'entity TEXT,row_uuid TEXT,column_name TEXT,ref_uuid TEXT,local_id INTEGER,'
                            'PRIMARY KEY(entity,row_uuid,column_name))')
            self.db.execute('CREATE TABLE IF NOT EXISTS journal_retired_refs('
                            'entity TEXT,uuid TEXT,local_id INTEGER CHECK(local_id<0),'
                            'PRIMARY KEY(entity,uuid),UNIQUE(entity,local_id))')
            self.db.execute('CREATE TABLE IF NOT EXISTS journal_deleted_ids('
                            'entity TEXT,uuid TEXT,local_id INTEGER,PRIMARY KEY(entity,uuid))')
            for table in sorted(ID_TABLES):
                # A deleted row's physical ID may be reused by ordinary SQLite
                # services. Preserve its UUID tombstone while detaching that ID.
                self.db.execute(f'CREATE TRIGGER IF NOT EXISTS journal_detach_{table} AFTER DELETE ON {table} '
                                f"BEGIN INSERT OR IGNORE INTO journal_deleted_ids SELECT entity,uuid,local_id FROM journal_ids WHERE entity='{table}' AND local_id=OLD.id; "
                                f"UPDATE journal_ids SET local_id=NULL WHERE entity='{table}' AND local_id=OLD.id; END")
                for ordinal, row in enumerate(self.db.all(f'SELECT id FROM {table} ORDER BY id')):
                    if self.db.scalar('SELECT 1 FROM journal_ids WHERE entity=? AND local_id=?', (table, row['id'])):
                        continue
                    value = str(uuid5(self.namespace, f'baseline:{table}:{ordinal}'))
                    # An old tombstone must never become a newly created row.
                    if self.db.scalar('SELECT 1 FROM journal_ids WHERE entity=? AND uuid=?', (table, value)):
                        value = str(uuid4())
                    self.bind(table, value, row['id'])
            if self.db.scalar("SELECT 1 FROM reserve_allocation_history h JOIN cash_reserves r ON r.id=h.reserve_id WHERE h.status='DELETED' LIMIT 1"):
                raise JournalError('Reused reserve history needs comparison before enrollment')
            for row in self.db.all('SELECT DISTINCT reserve_id FROM reserve_allocation_history WHERE reserve_id NOT IN (SELECT id FROM cash_reserves)'):
                if self.db.scalar("SELECT 1 FROM journal_deleted_ids WHERE entity='cash_reserves' AND local_id=?", (row['reserve_id'],)):
                    continue
                value = str(uuid5(self.namespace, f"baseline:retired:cash_reserves:{row['reserve_id']}"))
                self.db.execute("INSERT INTO journal_ids VALUES('cash_reserves',?,NULL)", (value,))
                self.db.execute("INSERT INTO journal_deleted_ids VALUES('cash_reserves',?,?)", (value, row['reserve_id']))

    def bind(self, table, value, local_id):
        if table not in ID_TABLES or type(local_id) is not int or local_id <= 0:
            raise JournalError('Invalid local financial identity')
        uuid(value)
        self.db.execute('INSERT INTO journal_ids VALUES(?,?,?)', (table, value, local_id))

    def uid(self, table, local_id):
        if local_id is None:
            return None
        if table not in ID_TABLES:
            raise JournalError('Unsupported identity table')
        value = self.db.scalar('SELECT uuid FROM journal_ids WHERE entity=? AND local_id=?', (table, local_id))
        if value is None:
            if not self.db.scalar(f'SELECT 1 FROM {table} WHERE id=?', (local_id,)):
                raise JournalError('Missing financial reference')
            value = str(uuid4())
            self.bind(table, value, local_id)
        return value

    def local(self, table, value):
        if value is None:
            return None
        if table not in ID_TABLES:
            raise JournalError('Unsupported identity table')
        uuid(value)
        local_id = self.db.scalar('SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?', (table, value))
        if local_id is None:
            raise JournalError('Missing confirmed financial reference')
        return local_id

    def _encode(self, table, row):
        values = {}
        for column, spec in TABLES[table]['columns'].items():
            value = row[column]
            reference = table if column == 'id' and table in ID_TABLES else _reference(table, column)
            if value is not None:
                if (table, column) in HISTORICAL_REFS:
                    owner = self.uid(table, row['id'])
                    pin = self.db.one('SELECT ref_uuid,local_id FROM journal_history_refs WHERE entity=? AND row_uuid=? AND column_name=?',
                                      (table, owner, column))
                    if pin:
                        if pin['local_id'] != value:
                            raise JournalError('An immutable historical reference changed')
                        value = pin['ref_uuid']
                    else:
                        local_id = value
                        if self.db.scalar(f'SELECT 1 FROM {reference} WHERE id=?', (value,)):
                            value = self.uid(reference, value)
                        else:
                            value = self.db.scalar('SELECT uuid FROM journal_deleted_ids WHERE entity=? AND local_id=? ORDER BY rowid DESC LIMIT 1',
                                                   (reference, value))
                            if value is None:
                                raise JournalError('Historical reference has no identity evidence')
                        self.db.execute('INSERT INTO journal_history_refs VALUES(?,?,?,?,?)', (table, owner, column, value, local_id))
                else:
                    value = self.uid(reference, value) if reference else str(value) if spec['type'] == 'INTEGER' else repr(value) if spec['type'] == 'REAL' else value
            values[column] = value
        if table == 'settings' and values['key'] in ID_SETTINGS:
            ids = json.loads(values['value'])
            if type(ids) is not list or any(type(i) is not int for i in ids):
                raise JournalError('Invalid stored category selection')
            values['value'] = canonical(sorted({self.uid('categories', i) for i in ids})).decode()
        if table == 'rule_conditions' and values['field'] == 'account':
            values['value'] = self.uid('accounts', int(values['value']))
        if table == 'settings' and values['key'] == 'budget_suppressed_categories':
            months = json.loads(values['value'])
            if type(months) is list:
                months = {str(i): 'never' for i in months}
            values['value'] = canonical({self.uid('categories', int(category)): until
                                         for category, until in months.items()}).decode()
        return values

    def snapshot(self):
        result = {}
        for table in TABLES:
            for row in self.db.all(f'SELECT * FROM {table}'):
                if table == 'settings' and not financial_setting(row['key']):
                    continue
                values = self._encode(table, row)
                result[(table, canonical(_key(table, values)))] = values
        return result

    @staticmethod
    def fingerprint_of(snapshot):
        result = hashlib.sha256(b'lightning-financial-graph-v2\n')
        for (table, key), values in sorted(snapshot.items()):
            result.update(canonical(dict(table=table, key=json.loads(key), values=values)) + b'\n')
        return result.hexdigest()

    def fingerprint(self):
        return self.fingerprint_of(self.snapshot())

    def difference(self, before):
        after = self.snapshot()
        rows = [dict(table=table, key=json.loads(key), before=digest(before[(table, key)]) if (table, key) in before else None,
                     values=after.get((table, key)))
                for table, key in sorted(before.keys() | after.keys()) if before.get((table, key)) != after.get((table, key))]
        effect = dict(schema=2, before=self.fingerprint_of(before), after=self.fingerprint_of(after), rows=rows)
        validate_effect(effect)
        return effect

    def _decode(self, table, values):
        decoded = {}
        for column, value in values.items():
            reference = table if column == 'id' and table in ID_TABLES else _reference(table, column)
            kind = TABLES[table]['columns'][column]['type']
            if value is not None and (table, column) in HISTORICAL_REFS:
                local_id = self.db.scalar('SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?', (reference, value))
                if local_id is None:
                    local_id = self.db.scalar('SELECT local_id FROM journal_deleted_ids WHERE entity=? AND uuid=?', (reference, value))
                if local_id is None:
                    local_id = self.db.scalar('SELECT local_id FROM journal_retired_refs WHERE entity=? AND uuid=?', (reference, value))
                    if local_id is None:
                        local_id = self.db.scalar('SELECT COALESCE(MIN(local_id),0)-1 FROM journal_retired_refs WHERE entity=?', (reference,))
                        self.db.execute('INSERT INTO journal_retired_refs VALUES(?,?,?)', (reference, value, local_id))
                self.db.execute('INSERT INTO journal_history_refs VALUES(?,?,?,?,?) ON CONFLICT(entity,row_uuid,column_name) '
                                'DO UPDATE SET ref_uuid=excluded.ref_uuid,local_id=excluded.local_id',
                                (table, values['id'], column, value, local_id))
                decoded[column] = local_id
                continue
            decoded[column] = (None if value is None else self.local(reference, value) if reference else
                               _integer(value) if kind == 'INTEGER' else float(value) if kind == 'REAL' else value)
        if table == 'settings' and values.get('key') in ID_SETTINGS and 'value' in values:
            decoded['value'] = json.dumps(sorted(self.local('categories', value) for value in json.loads(values['value'])))
        if table == 'rule_conditions' and values.get('field') == 'account' and 'value' in values:
            decoded['value'] = str(self.local('accounts', values['value']))
        if table == 'settings' and values.get('key') == 'budget_suppressed_categories' and 'value' in values:
            decoded['value'] = json.dumps({str(self.local('categories', category)): until
                                           for category, until in json.loads(values['value']).items()})
        return decoded

    def apply(self, effect):
        """Call under the journal's transaction and financial write guard."""
        validate_effect(effect)
        self._apply(effect)

    def replace_verified(self, snapshot):
        """Install an already authenticated checkpoint, within the repair lock.

        Checkpoints may contain more rows than a bounded command effect. Validate
        their typed rows in batches, then install all of them atomically, including
        forward references across batches. This is never a proposal operation.
        """
        before = self.snapshot()
        rows = [dict(table=table, key=json.loads(key), before=digest(before[(table, key)]) if (table, key) in before else None,
                     values=snapshot.get((table, key)))
                for table, key in sorted(before.keys() | snapshot.keys())
                if before.get((table, key)) != snapshot.get((table, key))]
        effect = dict(schema=2, before=self.fingerprint_of(before), after=self.fingerprint_of(snapshot), rows=rows)
        for start in range(0, len(rows), 256):
            validate_effect(effect | dict(rows=rows[start:start + 256]))
        self._apply(effect, repair=True)

    def _apply(self, effect, *, repair=False):
        with self.db.transaction():
            before = self.snapshot()
            if self.fingerprint_of(before) != effect['before']:
                raise JournalError('Financial graph differs; verified repair required')
            for row in effect['rows']:
                prior = before.get((row['table'], canonical(row['key'])))
                if (digest(prior) if prior is not None else None) != row['before']:
                    raise JournalError('Financial precondition differs')
            # Reserve every new UUID before decoding references, including cycles.
            for row in effect['rows']:
                table = row['table']
                if row['before'] is None and table in ID_TABLES:
                    known = self.db.one('SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?', (table, row['key']['id']))
                    if known and not (repair and known['local_id'] is None):
                        raise JournalError('A retired financial identity cannot be reused')
                    last = max(self.db.scalar(f'SELECT COALESCE(MAX(id),0) FROM {table}'),
                               self.db.scalar('SELECT COALESCE(MAX(local_id),0) FROM journal_ids WHERE entity=?', (table,)),
                               self.db.scalar('SELECT COALESCE(MAX(local_id),0) FROM journal_deleted_ids WHERE entity=?', (table,)))
                    if known:
                        self.db.execute('UPDATE journal_ids SET local_id=? WHERE entity=? AND uuid=?', (last + 1, table, row['key']['id']))
                    else:
                        self.bind(table, row['key']['id'], last + 1)
            self.db.execute('PRAGMA defer_foreign_keys=ON')
            # Posting services replace lines under the same (transaction,line_no)
            # unique key. Remove old identities before inserting replacements.
            # Decode all keys first: a cascade may detach a parent's UUID.
            deletions = [(row['table'], self._decode(row['table'], row['key']))
                         for row in effect['rows'] if row['values'] is None]
            for table, values in deletions:
                self.db.execute(f"DELETE FROM {table} WHERE {' AND '.join(column+'=?' for column in values)}", tuple(values.values()))
            for row in effect['rows']:
                if row['values'] is None:
                    continue
                table = row['table']
                values = self._decode(table, row['values'])
                columns = list(values)
                key_columns = list(row['key'])
                nonkeys = [column for column in columns if column not in key_columns]
                update = ','.join(f'{column}=excluded.{column}' for column in nonkeys)
                conflict = f'DO UPDATE SET {update}' if nonkeys else 'DO NOTHING'
                self.db.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)}) "
                                f"ON CONFLICT({','.join(key_columns)}) {conflict}", tuple(values.values()))
            if self.db.all('PRAGMA foreign_key_check') or self.fingerprint() != effect['after']:
                raise JournalError('Financial replay failed verification')
