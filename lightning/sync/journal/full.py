"""Opt-in full financial command adapter; no implicit production cutover."""
from __future__ import annotations

import sqlite3
from uuid import uuid4

from lightning.core.errors import LightningError, ValidationError

from . import commands
from .codec import JournalError, fields, digest, canonical
from .domain import DomainGraph, TABLES
from .finance import CashAdapter


def enable(store, *, _upgrade=False):
    """Upgrade an unused experimental baseline, before admitting any proposals."""
    if not _upgrade and (store.db.scalar('SELECT COUNT(*) FROM journal_outbox') or store.db.scalar('SELECT COUNT(*) FROM journal_inbox')):
        raise JournalError('Full-domain enrollment requires a verified unused baseline')
    store.db.conn.set_authorizer(None)
    old = store.adapter
    old_config = dict(store.config)
    try:
        with store.db.transaction():
            if not store.db.has_table('journal_domain_contract'):
                store.db.execute('CREATE TABLE journal_domain_contract(id INTEGER PRIMARY KEY CHECK(id=1),schema INTEGER NOT NULL CHECK(schema=2))')
                store.db.execute('INSERT INTO journal_domain_contract VALUES(1,2)')
            config = store.config | dict(version=3)
            store.db.execute('UPDATE journal_meta SET config=? WHERE id=1', (canonical(config).decode(),))
            store.config = config
            adapter = FullAdapter(old.c, store)
            store.adapter = adapter
            from .retention import initialize
            initialize(store)
        return adapter
    except BaseException:
        store.adapter = old
        store.config = old_config
        store.db.conn.set_authorizer(old._authorize)
        store.db.journal_guard = old._authorize
        raise


class FullAdapter(CashAdapter):
    full_domain = True

    def __init__(self, container, store):
        if store.config['version'] != 3 or container.db.scalar('SELECT schema FROM journal_domain_contract WHERE id=1') != 2:
            raise JournalError('Unsupported financial domain contract')
        self.graph = DomainGraph(container.db, store.config['profile'])
        self.graph.initialize()
        super().__init__(container, store)

    def _authorize(self, action, table, column, database, trigger):
        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            if table.startswith('journal_'):
                return sqlite3.SQLITE_OK
            if self.allowed and (table in TABLES or table in {'audit_log', 'bank_import_rows'} or table.startswith('transactions_fts')):
                return sqlite3.SQLITE_OK
            self.denied = table
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def uid(self, entity, local_id):
        return self.graph.uid(entity, local_id)

    def bind(self, entity, value, local_id):
        return self.graph.bind(entity, value, local_id)

    def local(self, entity, value):
        if entity == 'transactions' and value is not None:
            value = self.store.resolve(value)
        return self.graph.local(entity, value)

    def fingerprint(self):
        return self.graph.fingerprint()

    def validate_groups(self, groups, *, complete=False):
        if 'action' in groups:
            fields(groups, ('action',))
            commands.validate(self.c, self.graph, groups['action'])
        else:
            super().validate_groups(groups, complete=complete)

    def matches(self, proposal):
        return [] if proposal['kind'] == 'action.add' else super().matches(proposal)

    def confirm(self, proposal, effect):
        before = self.graph.snapshot()
        try:
            if proposal['kind'] == 'action.add':
                with self.writing():
                    commands.execute(self.c, self.graph, proposal['groups']['action'])
            else:
                super().confirm(proposal, effect)
            domain = self.graph.difference(before)
            self.refresh_records(domain)
            return domain
        except (JournalError, LightningError, ArithmeticError, self.db.IntegrityError) as error:
            raise ValidationError('The financial action could not be confirmed') from error

    def apply(self, domain):
        if domain.get('schema') != 2:
            raise JournalError('A full-domain device requires financial graph effects')
        with self.writing():
            self.graph.apply(domain)

    def refresh_records(self, domain):
        """Refresh cash field groups after any financial command changes them.

        Both roles derive the same metadata from the signed, exact graph effect.
        Old forms retain old tokens and therefore cannot overwrite a newer trade,
        reconciliation or register command through the earlier cash API.
        """
        from lightning.core.money import from_e6
        affected = set()
        for row in domain['rows']:
            if row['table'] == 'transactions':
                affected.add(row['key']['id'])
            elif row['table'] == 'ledger_entries' and row['values']:
                affected.add(row['values']['transaction_id'])
        for record_id in sorted(affected):
            record = self.store.record(record_id)
            if record is None or record['deleted'] or 'money' not in record['groups']:
                continue
            local = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity='transactions' AND uuid=?", (record_id,))
            transaction = self.db.one('SELECT * FROM transactions WHERE id=?', (local,)) if local else None
            if transaction is None or transaction['status'] == 'VOID':
                self.db.execute("UPDATE journal_records SET deleted=1,groups_json='{}',tokens_json='{}' WHERE record_id=?", (record_id,))
                continue
            lines = self.db.all('SELECT * FROM ledger_entries WHERE transaction_id=? ORDER BY line_no', (local,))
            if transaction['type'] not in {'IN', 'OUT', 'TRF'} or not lines:
                raise ValidationError('The cash record changed to an unsupported kind')
            if transaction['type'] == 'TRF':
                outgoing = next((line for line in lines if line['quantity_e6'] < 0), None)
                incoming = next((line for line in lines if line['quantity_e6'] > 0), None)
                if not outgoing or not incoming:
                    raise ValidationError('The transfer has no cash pair')
                account, other, amount, category = outgoing['account_id'], incoming['account_id'], outgoing['quantity_e6'], None
                splits = []
            else:
                if len({line['account_id'] for line in lines}) != 1:
                    raise ValidationError('The cash record has multiple accounts')
                account, other = lines[0]['account_id'], None
                amount = sum(line['quantity_e6'] for line in lines)
                category = self.uid('categories', lines[0]['category_id'])
                splits = [dict(category=self.uid('categories', line['category_id']), amount=format(abs(from_e6(line['quantity_e6'])), '.2f'))
                          for line in lines] if len(lines) > 1 else []
            groups = record['groups'] | dict(money=dict(account=self.uid('accounts', account), other_account=self.uid('accounts', other),
                date=transaction['date'], amount=format(from_e6(amount), '.2f')),
                category=dict(category=category, splits=splits), details={key: transaction[key] for key in ('counterparty', 'notes', 'description')})
            tokens = {group: record['tokens'][group] if record['groups'].get(group) == value else
                      digest(dict(domain=digest(domain), record=record_id, group=group)) for group, value in groups.items()}
            self.db.execute('UPDATE journal_records SET groups_json=?,tokens_json=? WHERE record_id=?',
                            (canonical(groups).decode(), canonical(tokens).decode(), record_id))

    def save_action(self, calls, signer, *, record=None, dependencies=()):
        action = commands.prepare(self.c, self.graph, calls)
        commands.validate(self.c, self.graph, action)
        return self.store.save(kind='action.add', record=record or str(uuid4()), groups={'action': action},
                               bases={'action': None}, signer=signer, dependencies=dependencies)
