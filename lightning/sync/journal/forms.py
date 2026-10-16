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
from lightning.core.journal_hooks import recorder

from . import commands
from .codec import JournalError, hash_value, uuid
from .domain import DomainGraph, financial_setting
from .domain_schema import TABLES
from .finance import attach


def _ensure_forms(store):
    exists = store.db.has_table('journal_forms')
    if exists and any(row['name'] == 'basis_key' for row in store.db.all('PRAGMA table_info(journal_forms)')):
        return
    with store.db.transaction():
        store.db.conn.set_authorizer(None)
        try:
            if exists:
                store.db.execute('ALTER TABLE journal_forms ADD COLUMN basis_key TEXT')
            else:
                store.db.execute('CREATE TABLE journal_forms(form_id TEXT PRIMARY KEY,path TEXT NOT NULL,request_hash TEXT,proposal_id TEXT,basis_key TEXT)')
        finally:
            store.db.conn.set_authorizer(store.adapter._authorize)


def issue_form(store, path, *, basis_key=None):
    from uuid import uuid4
    store.require_origin_checkpoint()
    _ensure_forms(store)
    if basis_key is None:
        from .form_basis import capture
        basis_key = capture(store)
    hash_value(basis_key)
    token = str(uuid4())
    with store.db.transaction():
        # Unsubmitted render tokens may expire; saved submission pointers are
        # retained without duplicating their narrative payload or signed wire.
        store.db.execute('DELETE FROM journal_forms WHERE form_id IN '
                         '(SELECT form_id FROM journal_forms WHERE proposal_id IS NULL ORDER BY rowid DESC LIMIT -1 OFFSET 1023)')
        store.db.execute('INSERT INTO journal_forms(form_id,path,basis_key) VALUES(?,?,?)', (token, path, basis_key))
    return token


def submission_basis(store, token, path):
    uuid(token)
    row = store.db.one('SELECT * FROM journal_forms WHERE form_id=? AND path=?', (token, path))
    if row is None or 'basis_key' not in row.keys() or not row['basis_key']:
        raise JournalError('This older form expired; open it again')
    return row['basis_key']


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
            if self.capture.depth:
                return entry(*args, **kwargs)
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
            return self.capture.invoke(command, arguments, lambda: entry(*args, **kwargs))
        return record


class _Settings:
    def __init__(self, capture, settings):
        self.capture, self.settings = capture, settings

    def __getattr__(self, name):
        return getattr(self.settings, name)

    def set(self, key, value):
        if not financial_setting(key):
            error = JournalError('Local preferences must use the local settings lane')
            self.capture.error = error
            raise error
        if self.capture.depth:
            return self.settings.set(key, value)
        return self.capture.invoke('profile.set_financial_setting', dict(key=key, value=value), lambda: self.settings.set(key, value))


class _SourceReferences:
    def __init__(self, capture):
        self.capture = capture

    def uid(self, entity, local_id):
        handle = self.capture.result_handles.get((entity, local_id))
        if handle is not None:
            self.capture.used_handles.add(handle)
            return handle
        return self.capture.base_graph.uid(entity, local_id)

    def _encode(self, table, values):
        if table != 'settings':
            raise JournalError('Unsupported embedded form reference')
        return DomainGraph._encode(self, table, values)


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
    def __init__(self, store, *, basis_key=None):
        if not getattr(store.adapter, 'full_domain', False):
            raise JournalError('Ordinary forms require a full-domain journal')
        self.store, self.calls = store, []
        self.steps, self.bindings, self.result_handles, self.used_handles = [], {}, {}, set()
        self.depth = 0
        self.error = None
        self.db = Database(':memory:', key=os.urandom(32))
        self.closed = False
        self.finished = False
        self.source_cursor = store.cursor()
        self.source_fingerprint = store.fingerprint()
        self.source_config = dict(store.config)
        self.basis_key = basis_key
        self.basis_db = None
        self.base_c, self.base_graph = store.adapter.c, store.adapter.graph
        try:
            if basis_key is not None:
                from .form_basis import open_basis
                self.basis_db = open_basis(store, basis_key)
                self.base_c = _wire_services(self.basis_db, Path('.'))
                self.base_c.backup_dir = None
                self.base_graph = DomainGraph(self.basis_db, store.config['profile'])
            (self.basis_db or store.db).conn.backup(self.db.conn)
            from .form_basis import workspace
            workspace(self.db)
            self.shadow = _wire_services(self.db, Path('.'))
            self.shadow.backup_dir = None
            self.shadow_store = attach(self.shadow)
            self.baseline = _financial_rows(self.db)
            self.context = self.shadow_store.adapter.writing()
            self.context.__enter__()
            self.container = _Container(self, self.shadow)
            self.recorder_token = recorder.set(self)
        except BaseException:
            self.db.close()
            self._close_basis()
            raise

    def named(self, command, receiver, arguments, invoke):
        # Replay/preview workspaces run normal workflows too. Never record a
        # different database or an internal call beneath the current root.
        if getattr(receiver, 'db', None) is not self.db or self.depth:
            return invoke()
        return self.invoke(command, deepcopy(arguments), invoke)

    def invoke(self, command, arguments, invoke):
        if self.finished or self.closed:
            raise JournalError('This form workspace has already ended')
        from .composition import RESULTS, result_id
        contracts = RESULTS.get(command, {})
        existing = {entity: {row[0] for row in self.db.all(f'SELECT id FROM {entity}')}
                    for entity, _ in contracts.values()}
        before = _financial_rows(self.db)
        self.depth += 1
        try:
            result = invoke()
        except BaseException as error:
            self.error = error
            raise
        finally:
            self.depth -= 1
        if _financial_rows(self.db) == before:
            return result
        try:
            encoded = commands.translate(self.base_c, _SourceReferences(self), command, arguments, encode=True)
        except BaseException as error:
            self.error = error
            raise
        index = len(self.calls)
        self.calls.append(dict(command=command, arguments=arguments))
        self.steps.append(dict(command=command, arguments=encoded))
        for slot in contracts:
            try:
                entity, local_id = result_id(command, slot, result)
            except JournalError:
                # Optional/empty returns need no handle. Any later attempt to
                # refer to an unrecognized new record fails before allocation.
                continue
            if local_id not in existing[entity]:
                from uuid import uuid4
                handle = str(uuid4())
                self.result_handles[(entity, local_id)] = handle
                self.bindings[handle] = dict(step=index, entity=entity, slot=slot)
        return result

    def finish(self, signer, *, record=None, submission=None):
        if self.closed or self.finished:
            raise JournalError('This form workspace has already ended')
        self.finished = True
        if submission is not None:
            prior = prior_submission(self.store, *submission)
            if prior is not None:
                return prior
            if self.basis_key is None:
                from .form_basis import _scope
                from .codec import digest
                if submission_basis(self.store, submission[0], submission[1]) != digest(_scope(self.store)):
                    raise JournalError('This form must use its original confirmed values')
        if self.error is not None:
            raise JournalError('This form could not be completed. Correct the fields before saving again') from self.error
        if self.store.config != self.source_config:
            raise JournalError('The journal authority changed; open this form again')
        if self.basis_key is None and (self.store.cursor() != self.source_cursor or self.store.fingerprint() != self.source_fingerprint):
            raise JournalError('The confirmed ledger changed; reload this form before saving')
        expected = _financial_rows(self.db)
        if expected == self.baseline:
            return None
        if not self.calls:
            raise JournalError('This form has an unrecorded financial write')
        calls = self.calls
        if self.used_handles:
            calls = [dict(command='workflow.compose', arguments=dict(steps=self.steps,
                          bindings={handle: self.bindings[handle] for handle in sorted(self.used_handles)}))]
        action = commands.prepare(self.base_c, self.base_graph, calls)
        replay = Database(':memory:', key=os.urandom(32))
        try:
            (self.basis_db or self.store.db).conn.backup(replay.conn)
            from .form_basis import workspace
            workspace(replay)
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
            recorder.reset(self.recorder_token)
            self.context.__exit__(None, None, None)
            self.db.close()
            self._close_basis()
            self.closed = True

    def _close_basis(self):
        if self.basis_db is not None:
            self.basis_db.close()
            from .form_basis import release
            release(self.store, self.basis_key)
            self.basis_db = None

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()
