"""Bounded encrypted local baselines for already-rendered financial forms.

These files never travel over the sync channel. They preserve the exact local
IDs and confirmed values a form showed, while the live replica keeps receiving
commits. Only the live store allocates an origin number or saves an intent.
"""
import hashlib
import json
import os
from pathlib import Path
import time

from lightning.database.connection import Database
from lightning.database.snapshot import snapshot, verify_connection
from .codec import JournalError, canonical, digest, fields, hash_value, number
from .finance import inspect_adapter


MAX_IMAGE = 200 * 1024 * 1024
MAX_TOTAL = 400 * 1024 * 1024
MAX_IMAGES = 8
MAX_AGE = 30 * 60


def _directory(store):
    if not store.db.encrypted or store.db.path == ':memory:':
        raise JournalError('Editing forms requires a persistent encrypted profile')
    root = Path(store.db.path).resolve().parent/'.journal-forms'
    if root.is_symlink():
        raise JournalError('The form cache must not be a symbolic link')
    root.mkdir(mode=0o700, exist_ok=True)
    return root


def _file(store, key):
    hash_value(key)
    path = _directory(store)/(key+'.db')
    if path.is_symlink():
        raise JournalError('An encrypted form baseline must not be a symbolic link')
    return path


def _initialize(store):
    if store.db.has_table('journal_form_basis'):
        return
    with store.db.transaction():
        store.db.conn.set_authorizer(None)
        try:
            store.db.execute('CREATE TABLE IF NOT EXISTS journal_form_basis(id TEXT PRIMARY KEY,manifest TEXT NOT NULL,created_at INTEGER NOT NULL)')
        finally:
            store.db.conn.set_authorizer(store.adapter._authorize)


def _ids(db):
    result = hashlib.sha256(b'lightning-local-form-identities-v1\n')
    for row in db.all('SELECT entity,local_id,uuid FROM journal_ids ORDER BY entity,local_id'):
        result.update(canonical(dict(entity=row['entity'], local_id=str(row['local_id']), uuid=row['uuid']))+b'\n')
    return result.hexdigest()


def _scope(store):
    context = hashlib.sha256(b'lightning-local-form-context-v1\n')
    for table, ordering in (('settings', 'key'), ('saved_views', 'id')):
        if not store.db.has_table(table):
            continue
        context.update(table.encode()+b'\n')
        for row in store.db.all(f'SELECT * FROM {table} ORDER BY {ordering}'):
            for value in row:
                encoded = repr(value).encode('utf-8')
                context.update(len(encoded).to_bytes(8, 'big')+encoded)
    return dict(config=dict(store.config), cursor=store.cursor(), fingerprint=store.fingerprint(),
                ids=_ids(store.db), context=context.hexdigest())


def _remove(path):
    for candidate in (path, Path(str(path)+'-journal'), Path(str(path)+'-wal'), Path(str(path)+'-shm')):
        if candidate.is_symlink():
            raise JournalError('The form cache contains a symbolic link')
        candidate.unlink(missing_ok=True)


def _scrub(store, target, cursor):
    # A form needs financial rows, ID mappings and local view preferences, not
    # copies of queued proposals, RPCs, credentials or expired decision detail.
    db = Database(target, key=store.db.copy_key())
    keep = {'journal_meta', 'journal_ids', 'journal_deleted_ids', 'journal_retired_refs',
            'journal_history_refs', 'journal_domain_contract', 'journal_aliases', 'journal_records'}
    try:
        db.execute('PRAGMA secure_delete=ON')
        with db.transaction():
            for row in db.all("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'journal_*'"):
                if row['name'] not in keep:
                    db.execute('DELETE FROM "'+row['name'].replace('"', '""')+'"')
            db.execute('UPDATE journal_meta SET next_seq=1 WHERE id=1')
            db.execute('UPDATE journal_meta SET config=? WHERE id=1',
                       (canonical(store.config | dict(role='form-basis')).decode(),))
            db.execute("UPDATE journal_records SET groups_json='{}'")
            db.execute("INSERT INTO journal_local VALUES('authority_enrolled','1')")
            db.execute("INSERT INTO journal_local VALUES('form_basis_cursor',?)", (canonical(cursor).decode(),))
            db.execute("INSERT INTO journal_local VALUES('form_basis_config',?)", (canonical(store.config).decode(),))
        verify_connection(db.conn, encrypted=True)
    finally:
        db.close()
    with target.open('rb') as handle:
        os.fsync(handle.fileno())
    if os.name != 'nt':
        descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def workspace(db):
    """Only an encrypted in-memory preview may restore a basis's runtime role."""
    if not db.has_table('journal_meta'):
        return
    config = json.loads(db.scalar('SELECT config FROM journal_meta WHERE id=1'))
    if config.get('role') != 'form-basis':
        return
    if db.path != ':memory:' or not db.encrypted:
        raise JournalError('A form baseline cannot become a writable profile')
    original = json.loads(db.scalar("SELECT value FROM journal_local WHERE name='form_basis_config'"))
    if config != original | dict(role='form-basis') or original.get('role') not in ('home', 'replica'):
        raise JournalError('The form baseline identity is damaged')
    with db.transaction():
        db.execute('UPDATE journal_meta SET config=? WHERE id=1', (canonical(original).decode(),))


def _hash(path):
    if not path.is_file() or path.stat().st_size > MAX_IMAGE:
        raise JournalError('The encrypted form baseline is missing or too large')
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def prune(store, *, reserve=0, protect=None):
    if not store.db.has_table('journal_form_basis'):
        return
    all_rows = list(store.db.all('SELECT * FROM journal_form_basis ORDER BY created_at,rowid'))
    rows = [row for row in all_rows if row['id'] != protect]
    root = _directory(store)
    known = {row['id'] for row in all_rows} | ({protect} if protect else set())
    # Exclusive-created cache exports that never acquired a committed manifest
    # contain no sole copy of any saved action. Remove only our exact filenames.
    for path in root.glob('*.db'):
        if len(path.stem) == 64 and all(character in '0123456789abcdef' for character in path.stem) and path.stem not in known:
            if path.is_symlink():
                raise JournalError('The form cache contains a symbolic link')
            _remove(path)
    sizes = {row['id']: (_file(store, row['id']).stat().st_size if _file(store, row['id']).exists() else 0) for row in rows}
    count, total = len(rows), sum(sizes.values())
    active = getattr(store, '_active_form_bases', set())
    for row in rows:
        if row['id'] in active:
            continue
        expired = row['created_at'] < int(time.time())-MAX_AGE
        if not expired and sizes[row['id']] and count+bool(reserve) <= MAX_IMAGES and total+reserve <= MAX_TOTAL:
            continue
        _remove(_file(store, row['id']))
        with store.db.transaction():
            store.db.execute('DELETE FROM journal_form_basis WHERE id=?', (row['id'],))
        count -= 1
        total -= sizes[row['id']]
    if count+bool(reserve) > MAX_IMAGES or total+reserve > MAX_TOTAL:
        raise JournalError('Finish the current edit before opening another form')


def capture(store):
    store.require_origin_checkpoint()
    if store.db.conn.in_transaction:
        raise JournalError('Prepare a form baseline before starting its metadata transaction')
    _initialize(store)
    scope = _scope(store)
    key = digest(scope)
    row = store.db.one('SELECT * FROM journal_form_basis WHERE id=?', (key,))
    if row and row['created_at'] >= int(time.time())-MAX_AGE and _file(store, key).is_file():
        try:
            if _hash(_file(store, key)) == json.loads(row['manifest'])['sha256']:
                return key
        except (ValueError, KeyError, TypeError):
            pass
    if key in getattr(store, '_active_form_bases', set()):
        raise JournalError('Finish the current edit before opening another form')
    prune(store, reserve=min(Path(store.db.path).stat().st_size, MAX_IMAGE), protect=key)
    target = _file(store, key)
    if target.exists():
        # The scope is still current, but its earlier cache entry expired.
        # This is a regenerable cache, never the live ledger or a user backup.
        _remove(target)
    store.db.conn.set_authorizer(None)
    try:
        snapshot(store.db, target)
    finally:
        store.db.conn.set_authorizer(store.adapter._authorize)
    try:
        _scrub(store, target, scope['cursor'])
        manifest = scope | dict(size=target.stat().st_size, sha256=_hash(target))
        prune(store, reserve=manifest['size'], protect=key)
        with store.db.transaction():
            store.db.execute('INSERT OR REPLACE INTO journal_form_basis VALUES(?,?,?)',
                             (key, canonical(manifest).decode(), int(time.time())))
    except BaseException:
        _remove(target)
        raise
    return key


def open_basis(store, key):
    """Return a verified read-only image; the caller owns and closes its key."""
    hash_value(key)
    if not store.db.has_table('journal_form_basis'):
        raise JournalError('This form expired; open it again')
    row = store.db.one('SELECT * FROM journal_form_basis WHERE id=?', (key,))
    if row is None or row['created_at'] < int(time.time())-MAX_AGE:
        raise JournalError('This form expired; open it again')
    try:
        manifest = json.loads(row['manifest'])
        fields(manifest, ('config', 'cursor', 'fingerprint', 'ids', 'context', 'size', 'sha256'))
        number(manifest['size'], minimum=1)
        hash_value(manifest['sha256'])
        scope = {name: manifest[name] for name in ('config', 'cursor', 'fingerprint', 'ids', 'context')}
        if digest(scope) != key or manifest['config'] != store.config:
            raise JournalError('The form belongs to an earlier device or authority; open it again')
        store._check_cursor(manifest['cursor'])
        path = _file(store, key)
        if path.stat().st_size != manifest['size'] or _hash(path) != manifest['sha256']:
            raise JournalError('The encrypted form baseline changed; open the form again')
        db = Database(path, key=store.db.copy_key(), read_only=True)
        try:
            verify_connection(db.conn, encrypted=True)
            config = json.loads(db.scalar('SELECT config FROM journal_meta WHERE id=1'))
            original = json.loads(db.scalar("SELECT value FROM journal_local WHERE name='form_basis_config'"))
            if original != manifest['config'] or config != original | dict(role='form-basis'):
                raise JournalError('The cached file is not a form baseline')
            cursor = json.loads(db.scalar("SELECT value FROM journal_local WHERE name='form_basis_cursor'"))
            from types import SimpleNamespace
            adapter = inspect_adapter(db, original)
            saved = SimpleNamespace(db=db, config=original, cursor=lambda: cursor, fingerprint=adapter.fingerprint)
            if _scope(saved) != scope:
                raise JournalError('The original form values could not be verified')
            if not hasattr(store, '_active_form_bases'):
                store._active_form_bases = set()
            store._active_form_bases.add(key)
            return db
        except BaseException:
            db.close()
            raise
    except (KeyError, TypeError, ValueError, OSError, store.db.driver.Error) as error:
        raise JournalError('The original form values are unavailable; open the form again') from error


def release(store, key):
    getattr(store, '_active_form_bases', set()).discard(key)
