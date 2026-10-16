"""Capture existing form service calls in an isolated encrypted workspace.

No live financial write is permitted. A form becomes one normal-service action
only if replaying its recorded commands accounts for every financial change.
Native callers must separately gate file operations and local capture staging.
"""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
import inspect
import os
from pathlib import Path

from lightning.bootstrap import _wire_services
from lightning.database.connection import Database

from . import commands
from .codec import JournalError, hash_value, uuid
from .domain import financial_setting
from .domain_schema import TABLES
from .finance import attach


def _ensure_forms(store):
    if store.db.has_table('journal_forms'):
        return
    with store.db.transaction():
        store.db.conn.set_authorizer(None)
        try:
            store.db.execute('CREATE TABLE IF NOT EXISTS journal_forms(form_id TEXT PRIMARY KEY,path TEXT NOT NULL,request_hash TEXT,proposal_id TEXT)')
        finally:
            store.db.conn.set_authorizer(store.adapter._authorize)


def issue_form(store, path):
    from uuid import uuid4
    store.require_origin_checkpoint()
    _ensure_forms(store)
    token = str(uuid4())
    with store.db.transaction():
        # Unsubmitted render tokens may expire; saved submission pointers are
        # retained without duplicating their narrative payload or signed wire.
        store.db.execute('DELETE FROM journal_forms WHERE form_id IN '
                         '(SELECT form_id FROM journal_forms WHERE proposal_id IS NULL ORDER BY rowid DESC LIMIT -1 OFFSET 1023)')
        store.db.execute('INSERT INTO journal_forms(form_id,path) VALUES(?,?)', (token, path))
    return token


def prior_submission(store, token, path, request_hash):
    uuid(token)
    hash_value(request_hash)
    if not store.db.has_table('journal_forms'):
        raise JournalError('This form expired; open it again')
    row = store.db.one('SELECT * FROM journal_forms WHERE form_id=?', (token,))
    if row is None or row['path'] != path:
        raise JournalError('This form expired; open it again')
    if row['request_hash'] is None:
        return None
    if row['request_hash'] != request_hash:
        raise JournalError('This form was already saved with different values; open it again')
    wire = store.db.scalar('SELECT wire FROM journal_outbox WHERE proposal_id=?', (row['proposal_id'],))
    if wire is None:
        raise JournalError('The saved form is missing; explicit repair required')
    observer = store.require_origin_checkpoint()
    if observer is not None and not store.db.conn.in_transaction:
        # A prior encrypted commit may have survived an interrupted private
        # checkpoint. A retry must finish that checkpoint before claiming Saved.
        observer.reconcile()
    return bytes(wire)


def _financial_rows(db):
    # Both workspaces start from the same encrypted baseline, so their local
    # allocations are comparable. Only service-maintained wall-clock stamps
    # are excluded; amounts, references, dates and financial settings are exact.
    result = {}
    for table, specification in TABLES.items():
        columns = [column for column in specification['columns'] if column not in ('created_at', 'updated_at')]
        rows = []
        for row in db.all(f'SELECT {",".join(columns)} FROM {table}'):
            value = dict(row)
            if table == 'settings' and not financial_setting(value['key']):
                continue
            rows.append(value)
        result[table] = sorted(rows, key=lambda row: repr(sorted(row.items())))
    # This is a local comparison, not a transmitted financial payload. The
    # graph encoder owns canonical typed replication (including int64/REAL).
    return repr(result)


class _Service:
    def __init__(self, capture, name, service):
        self.capture, self.name, self.service = capture, name, service

    def __getattr__(self, name):
        entry = getattr(self.service, name)
        command = f'{self.name}.{name}'
        if command not in commands.COMMANDS:
            return entry

        @wraps(entry)
        def record(*args, **kwargs):
            before = _financial_rows(self.capture.db)
            signature = inspect.signature(entry)
            bound = signature.bind(*args, **kwargs)
            arguments = {}
            for key, value in bound.arguments.items():
                kind = signature.parameters[key].kind
                if kind is inspect.Parameter.VAR_KEYWORD:
                    arguments.update(deepcopy(value))
                elif kind is inspect.Parameter.VAR_POSITIONAL:
                    if value:
                        raise JournalError('This form needs an explicit journal workflow')
                else:
                    arguments[key] = deepcopy(value)
            result = entry(*args, **kwargs)
            if _financial_rows(self.capture.db) != before:
                self.capture.calls.append(dict(command=command, arguments=arguments))
            return result
        return record


class _Settings:
    def __init__(self, capture, settings):
        self.capture, self.settings = capture, settings

    def __getattr__(self, name):
        return getattr(self.settings, name)

    def set(self, key, value):
        if not financial_setting(key):
            raise JournalError('Local preferences must use the local settings lane')
        result = self.settings.set(key, value)
        self.capture.calls.append(dict(command='profile.set_financial_setting', arguments=dict(key=key, value=value)))
        return result


class _Container:
    def __init__(self, capture, container):
        self.capture, self.container = capture, container

    def __getattr__(self, name):
        value = getattr(self.container, name)
        if name == 'settings':
            return _Settings(self.capture, value)
        if name in commands.WRITES:
            return _Service(self.capture, name, value)
        return value


class FormCapture:
    """Owning-thread workspace; response bytes must wait until finish succeeds.

    The caller holds the native session gate throughout. It buffers the route
    response and discards it on refusal. Created-record detail redirects need a
    pending-action destination until confirmation; they cannot use shadow IDs.
    """
    def __init__(self, store):
        if not getattr(store.adapter, 'full_domain', False):
            raise JournalError('Ordinary forms require a full-domain journal')
        self.store, self.calls = store, []
        self.db = Database(':memory:', key=os.urandom(32))
        self.closed = False
        self.finished = False
        self.source_cursor = store.cursor()
        self.source_fingerprint = store.fingerprint()
        try:
            store.db.conn.backup(self.db.conn)
            self.shadow = _wire_services(self.db, Path('.'))
            self.shadow.backup_dir = None
            self.shadow_store = attach(self.shadow)
            self.baseline = _financial_rows(self.db)
            self.context = self.shadow_store.adapter.writing()
            self.context.__enter__()
            self.container = _Container(self, self.shadow)
        except BaseException:
            self.db.close()
            raise

    def finish(self, signer, *, record=None, submission=None):
        if self.closed or self.finished:
            raise JournalError('This form workspace has already ended')
        self.finished = True
        if submission is not None:
            prior = prior_submission(self.store, *submission)
            if prior is not None:
                return prior
        if self.store.cursor() != self.source_cursor or self.store.fingerprint() != self.source_fingerprint:
            raise JournalError('The confirmed ledger changed; reload this form before saving')
        expected = _financial_rows(self.db)
        if expected == self.baseline:
            return None
        if not self.calls:
            raise JournalError('This form has an unrecorded financial write')
        # Preparation uses confirmed records, never identifiers invented only
        # in the shadow. Workflows that create then refer to a new object need
        # a reviewed named command, rather than leaking a shadow's local ID.
        action = commands.prepare(self.store.adapter.c, self.store.adapter.graph, self.calls)
        replay = Database(':memory:', key=os.urandom(32))
        try:
            self.store.db.conn.backup(replay.conn)
            container = _wire_services(replay, Path('.'))
            container.backup_dir = None
            saved = attach(container)
            with replay.transaction(), saved.adapter.writing():
                commands.execute(container, saved.adapter.graph, action)
            if _financial_rows(replay) != expected:
                raise JournalError('This form has financial changes outside its journal commands')
        finally:
            replay.close()
        # Sign and allocate only after the isolated route and replay agree.
        from uuid import uuid4
        with self.store.db.transaction():
            if submission is not None:
                prior = prior_submission(self.store, *submission)
                if prior is not None:
                    return prior
            wire = self.store.save(kind='action.add', record=record or str(uuid4()), groups=dict(action=action),
                                   bases=dict(action=None), signer=signer)
            if submission is not None:
                from .codec import unpack, origin_id
                token, path, request_hash = submission
                proposal_id = origin_id(unpack(wire)['body']['origin'])
                self.store.db.execute('UPDATE journal_forms SET request_hash=?,proposal_id=? WHERE form_id=?',
                                      (request_hash, proposal_id, token))
            return wire

    def close(self):
        if not self.closed:
            self.context.__exit__(None, None, None)
            self.db.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()
