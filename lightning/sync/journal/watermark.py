"""Per-origin restore fencing, stored outside ordinary profile backups.

The encrypted transaction commits first. The private checkpoint commits before
the operation returns. A crash between them is reconciled from signed history;
a private checkpoint ahead of the profile is never silently reset.
"""
import json
import sqlite3
from pathlib import Path

from .codec import (JournalError, authenticate, canonical, cursor, digest,
                    fields, hash_value, number, unpack, uuid)
from .retention import is_receipt, proposal_hash


class Watermark:
    def __init__(self, memory, store):
        self.memory, self.store = memory, store

    def _saved(self):
        try:
            row = self.memory.db.execute('SELECT document FROM origin_checkpoint WHERE id=1').fetchone()
            if row is None:
                raise ValueError
            if row[0] is None:
                if self.memory.state().get('origin_bound'):
                    raise ValueError
                return None
            value = json.loads(row[0])
            fields(value, ('path', 'profile', 'device', 'incarnation', 'origin_key', 'generation',
                           'format', 'seq', 'proposal_hash', 'cursor', 'fingerprint'))
            for key in ('profile', 'device', 'incarnation', 'generation'):
                uuid(value[key])
            number(value['format'], minimum=2)
            number(value['seq'])
            cursor(value['cursor'])
            hash_value(value['fingerprint'])
            if value['seq']:
                hash_value(value['proposal_hash'])
            elif value['proposal_hash'] is not None:
                raise ValueError
            if type(value['path']) is not str or not Path(value['path']).is_absolute():
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError, sqlite3.Error) as error:
            raise JournalError('Origin checkpoint is damaged; explicit repair required') from error

    def _current(self):
        store = self.store
        config = store.config
        seq = store.db.scalar('SELECT next_seq-1 FROM journal_meta WHERE id=1')
        wire = store.db.scalar('SELECT wire FROM journal_outbox WHERE seq=?', (seq,)) if seq else None
        if seq and wire is None:
            raise JournalError('Origin history is incomplete; explicit repair required')
        return dict(path=str(Path(store.db.path).resolve()), profile=config['profile'],
                    device=config['device'], incarnation=config['incarnation'], origin_key=config['origin_key'],
                    generation=config['generation'], format=config['version'], seq=seq,
                    proposal_hash=proposal_hash(wire) if wire else None, cursor=store.cursor())

    def check(self, *, financial=False):
        if self.memory._closed:
            raise JournalError('Authority memory is closed; reopen it before writing')
        saved, current = self._saved(), self._current()
        if saved is None:
            return current
        if any(saved[k] != current[k] for k in ('path', 'profile', 'device', 'incarnation', 'origin_key')):
            raise JournalError('Origin belongs to another file or device; explicit enrollment required')
        if saved['generation'] != current['generation']:
            if not self.memory._activating:
                raise JournalError('Origin generation changed without verified activation')
        if current['seq'] < saved['seq'] or current['cursor']['revision'] < saved['cursor']['revision'] or current['format'] < saved['format']:
            raise JournalError('Restored journal is behind its private checkpoint; explicit repair required')
        if saved['seq']:
            wire = self.store.db.scalar('SELECT wire FROM journal_outbox WHERE seq=?', (saved['seq'],))
            if wire is None or proposal_hash(wire) != saved['proposal_hash']:
                raise JournalError('Origin slot differs from its private checkpoint')
        self.store._check_cursor(saved['cursor'])
        if financial and saved['cursor'] == current['cursor'] and saved['format'] == current['format']:
            if saved['fingerprint'] != self.store.fingerprint():
                raise JournalError('Financial state differs from its private checkpoint')
        return current

    def _write(self, current):
        saved = self._saved()
        # Local drafts, mailbox caches and display acknowledgements do not
        # change confirmed money. Avoid rescanning the ledger for each one.
        fingerprint = (saved['fingerprint'] if saved and saved['cursor'] == current['cursor']
                       and saved['format'] == current['format'] else self.store.fingerprint())
        current = current | dict(fingerprint=fingerprint)
        db = self.memory.db
        own = not db.in_transaction
        if own:
            db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE origin_checkpoint SET document=? WHERE id=1', (canonical(current).decode(),))
            state = self.memory.state()
            if not state.get('origin_bound'):
                state['origin_bound'] = True
                db.execute('UPDATE authority SET document=? WHERE id=1', (canonical(state).decode(),))
            if own:
                db.execute('COMMIT')
        except BaseException:
            if own and db.in_transaction:
                db.execute('ROLLBACK')
            raise

    def reconcile(self):
        """Opening after a crash may advance only over authenticated history."""
        current = self.check(financial=True)
        saved = self._saved()
        if saved is not None:
            for row in self.store.db.all('SELECT wire FROM journal_outbox WHERE seq>? ORDER BY seq', (saved['seq'],)):
                envelope = unpack(bytes(row[0]))
                if is_receipt(envelope['body']):
                    # A receipt needs the original immutable slot already known
                    # to this device; never use one to invent a lost origin.
                    raise JournalError('Unknown compact origin slot; explicit queue repair required')
                authenticate(envelope, self.store.config['origin_key'])
            previous = saved['cursor']['hash']
            for row in self.store.db.all('SELECT revision,hash,wire FROM journal_commits WHERE revision>? ORDER BY revision',
                                         (saved['cursor']['revision'],)):
                envelope = unpack(bytes(row['wire']))
                body = envelope['body']
                authenticate(envelope, self.store.config['home_key'])
                if is_receipt(body) or body['previous'] != previous or digest(body) != row['hash']:
                    raise JournalError('Unverified history after private checkpoint; explicit repair required')
                previous = row['hash']
            if current['cursor'] != saved['cursor']:
                latest = unpack(bytes(self.store.db.scalar('SELECT wire FROM journal_commits ORDER BY revision DESC LIMIT 1')))['body']
                if latest.get('fingerprint') != self.store.fingerprint():
                    raise JournalError('Recovered ledger differs from signed history')
        self._write(current)

    def before_transaction(self):
        current = self.check()
        state = self.memory.state()
        if state['generation'] != current['generation'] and not self.memory._activating:
            raise JournalError('New authority observed; reconcile this device before writing')

    def after_commit(self):
        self._write(self.check())
