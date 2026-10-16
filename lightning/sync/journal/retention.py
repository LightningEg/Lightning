"""Acknowledged history compaction without forgetting origin identities.

Undecided slots are never pruned. Compact home-signed receipts retain the
original stream hash, proposal hash, outcome, dependency tokens and aliases.
An old stream reader must install a verified checkpoint before catching up.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from .codec import (JournalError, authenticate, canonical, digest, fields,
                    hash_value, number, origin_id, seal, unpack, uuid)

SCHEMA = (
    'CREATE TABLE IF NOT EXISTS journal_commit_times(revision INTEGER PRIMARY KEY,confirmed_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS journal_acks(device TEXT,incarnation TEXT,generation TEXT,revision INTEGER NOT NULL,hash TEXT NOT NULL,PRIMARY KEY(device,incarnation))',
    'CREATE TABLE IF NOT EXISTS journal_compacted(revision INTEGER PRIMARY KEY)',
)


class SnapshotRequired(JournalError):
    def __init__(self):
        super().__init__('Detailed history expired; a verified checkpoint is required')


def now():
    return datetime.now(timezone.utc)


def initialize(store, *, clock=now):
    with store.db.transaction():
        for statement in SCHEMA:
            table = statement.split('(')[0].split()[-1]
            if store.db.has_table(table):
                continue
            # SQLite authorizes a CREATE's sqlite_master writes even when it is
            # an IF NOT EXISTS. Only these fixed protocol DDL statements bypass
            # the financial guard, on the owning thread under its transaction.
            store.db.conn.set_authorizer(None)
            try:
                store.db.execute(statement)
            finally:
                store.db.conn.set_authorizer(store.adapter._authorize if store.adapter else None)
        stamp = clock().isoformat()
        store.db.execute('INSERT OR IGNORE INTO journal_commit_times SELECT revision,? FROM journal_commits', (stamp,))


def committed(db, revision):
    if db.has_table('journal_commit_times'):
        db.execute('INSERT OR IGNORE INTO journal_commit_times VALUES(?,?)', (revision, now().isoformat()))


def is_receipt(body):
    return body.get('type') == 'compact-receipt'


def validate_receipt(body):
    fields(body, ('version', 'type', 'profile', 'generation', 'revision', 'commit_hash',
                  'proposal_id', 'proposal_hash', 'outcome', 'reason', 'effects'))
    if type(body['version']) is not int or body['version'] != 2 or body['type'] != 'compact-receipt':
        raise JournalError('Unsupported compact receipt')
    uuid(body['profile'])
    uuid(body['generation'])
    number(body['revision'], minimum=1)
    hash_value(body['commit_hash'])
    hash_value(body['proposal_hash'])
    try:
        device, incarnation, seq = body['proposal_id'].split('/')
        if origin_id(dict(device=device, incarnation=incarnation, seq=int(seq))) != body['proposal_id']:
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise JournalError('Invalid compact proposal identity') from error
    from .store import _commit
    # Reuse the normal outcome/reason checks; compact effects are separately
    # typed because they deliberately contain tokens without financial values.
    if type(body['effects']) is not list or len(body['effects']) > 1:
        raise JournalError('Invalid compact receipt effects')
    effects = []
    for effect in body['effects']:
        if type(effect) is not dict:
            raise JournalError('Invalid compact effect')
        fields(effect, {'record', 'tokens', 'groups', 'deleted'} | (effect.keys() & {'alias'}))
        uuid(effect['record'])
        if effect['groups'] != {} or type(effect['deleted']) is not bool or type(effect['tokens']) is not dict:
            raise JournalError('Compact receipts contain no financial payload')
        if 'alias' in effect:
            uuid(effect['alias'])
        from .codec import GROUP
        if len(effect['tokens']) > 16:
            raise JournalError('Invalid compact token count')
        for key, value in effect['tokens'].items():
            if not GROUP.fullmatch(key):
                raise JournalError('Invalid compact group')
            hash_value(value)
        # Placeholder group values are used only for schema validation.
        effects.append(effect | dict(groups={} if 'alias' in effect else dict.fromkeys(effect['tokens'])))
    _commit(dict(version=2, type='commit', profile=body['profile'], generation=body['generation'],
                 revision=body['revision'], previous='0' * 64, proposal_id=body['proposal_id'],
                 proposal_hash=body['proposal_hash'], outcome=body['outcome'], reason=body['reason'],
                 effects=effects, fingerprint='0' * 64))
    canonical(body)


def proposal_hash(wire):
    body = unpack(bytes(wire))['body']
    if is_receipt(body):
        validate_receipt(body)
        return body['proposal_hash']
    if body.get('type') == 'commit':
        from .store import _commit
        _commit(body)
        return body['proposal_hash']
    from .codec import proposal
    proposal(body)
    return digest(body)


class Retention:
    def __init__(self, store, *, signer=None, clock=now):
        self.store, self.db, self.signer, self.clock = store, store.db, signer, clock
        initialize(store, clock=clock)

    def acknowledge(self, device, incarnation, cursor):
        """Called only after authenticating this approved member's control lane."""
        uuid(device)
        uuid(incarnation)
        from .codec import cursor as validate_cursor
        validate_cursor(cursor)
        with self.db.transaction():
            if self.store.config['role'] != 'home' or not self.db.scalar(
                    'SELECT 1 FROM journal_origins WHERE device=? AND incarnation=? AND revoked=0', (device, incarnation)):
                raise JournalError('Only an approved member can acknowledge history')
            self.store._check_cursor(cursor)
            existing = self.db.one('SELECT generation,revision,hash FROM journal_acks WHERE device=? AND incarnation=?', (device, incarnation))
            if existing and existing['generation'] == self.store.config['generation']:
                if cursor['revision'] < existing['revision']:
                    return False
                if cursor['revision'] == existing['revision']:
                    if cursor['hash'] != existing['hash']:
                        raise JournalError('Acknowledgement changed its checkpoint')
                    return False
            self.db.execute('INSERT INTO journal_acks VALUES(?,?,?,?,?) ON CONFLICT(device,incarnation) '
                            'DO UPDATE SET generation=excluded.generation,revision=excluded.revision,hash=excluded.hash',
                            (device, incarnation, self.store.config['generation'], cursor['revision'], cursor['hash']))
            return True

    def compact(self, *, limit=100):
        if self.store.config['role'] != 'home' or self.signer is None:
            raise JournalError('Only the authorized home compacts confirmed history')
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise JournalError('Invalid compaction budget')
        with self.store.confirming(), self.db.transaction():
            self.store.require_confirmation_authority()
            minimum = self.store.cursor()['revision']
            for member in self.db.all('SELECT device,incarnation FROM journal_origins WHERE revoked=0'):
                if member['device'] == self.store.config['device'] and member['incarnation'] == self.store.config['incarnation']:
                    continue
                ack = self.db.scalar('SELECT revision FROM journal_acks WHERE device=? AND incarnation=? AND generation=?',
                                     (member['device'], member['incarnation'], self.store.config['generation']))
                minimum = min(minimum, ack or 0)
            count, cutoff = 0, self.clock() - timedelta(days=30)
            for row in self.db.all('SELECT c.*,t.confirmed_at FROM journal_commits c JOIN journal_commit_times t USING(revision) '
                                   'WHERE revision<=? AND revision NOT IN (SELECT revision FROM journal_compacted) '
                                   'AND t.confirmed_at<=? ORDER BY revision LIMIT ?', (minimum, cutoff.isoformat(), limit)):
                if datetime.fromisoformat(row['confirmed_at']) > cutoff:
                    continue
                old = bytes(row['wire'])
                body = unpack(old)['body']
                if is_receipt(body):
                    self.db.execute('INSERT OR IGNORE INTO journal_compacted VALUES(?)', (row['revision'],))
                    continue
                compact = {key: body[key] for key in ('version', 'profile', 'generation', 'revision', 'proposal_id', 'proposal_hash', 'outcome', 'reason')}
                compact.update(type='compact-receipt', commit_hash=row['hash'], effects=[
                    {key: effect[key] for key in ('record', 'tokens', 'deleted')} | dict(groups={}) |
                    ({'alias': effect['alias']} if 'alias' in effect else {}) for effect in body['effects']])
                validate_receipt(compact)
                wire = seal(compact, self.signer)
                authenticate(unpack(wire), self.store.config['home_key'])
                self.db.execute('UPDATE journal_commits SET wire=? WHERE revision=?', (wire, row['revision']))
                self.db.execute('UPDATE journal_inbox SET wire=? WHERE proposal_id=? AND status IN (\'accepted\',\'accepted-as-existing\',\'rejected\')',
                                (wire, row['proposal_id']))
                self.db.execute('UPDATE journal_reviews SET result=? WHERE result=?', (wire, old))
                self.db.execute('INSERT INTO journal_compacted VALUES(?)', (row['revision'],))
                record = body['effects'][0]['record'] if body['effects'] else None
                current = self.store.record(record) if record else None
                if current and 'action' in current['groups'] and current['tokens'] == body['effects'][0]['tokens']:
                    self.db.execute('UPDATE journal_records SET groups_json=? WHERE record_id=?', ('{"action":null}', record))
                count += 1
            return count

    def expired_revisions(self, *, limit=8):
        return [row['revision'] for row in self.db.all('SELECT revision FROM journal_commit_times '
                'WHERE confirmed_at<=? AND revision NOT IN (SELECT revision FROM journal_compacted) ORDER BY revision LIMIT ?',
                ((self.clock() - timedelta(days=30)).isoformat(), limit))]

    def accept_receipt(self, wire):
        envelope = unpack(wire)
        authenticate(envelope, self.store.config['home_key'])
        body = envelope['body']
        validate_receipt(body)
        if body['profile'] != self.store.config['profile']:
            raise JournalError('Compact receipt belongs to another profile')
        with self.db.transaction():
            row = self.db.one('SELECT * FROM journal_commits WHERE revision=?', (body['revision'],))
            if row is None or row['hash'] != body['commit_hash'] or row['proposal_id'] != body['proposal_id']:
                raise JournalError('Compact receipt differs from the confirmed stream')
            original = unpack(bytes(row['wire']))['body']
            if any(original[key] != body[key] for key in ('profile', 'generation', 'proposal_id', 'proposal_hash', 'outcome', 'reason')):
                raise JournalError('Compact receipt changes its decision')
            expected = [{key: effect[key] for key in ('record', 'tokens', 'deleted')} | dict(groups={}) |
                        ({'alias': effect['alias']} if 'alias' in effect else {}) for effect in original['effects']]
            if body['effects'] != expected:
                raise JournalError('Compact receipt changes dependency tokens')
            timestamp = self.db.scalar('SELECT confirmed_at FROM journal_commit_times WHERE revision=?', (body['revision'],))
            if timestamp is None or datetime.fromisoformat(timestamp) > self.clock() - timedelta(days=30):
                return False
            old = bytes(row['wire'])
            self.db.execute('UPDATE journal_commits SET wire=? WHERE revision=?', (wire, body['revision']))
            self.db.execute('INSERT OR IGNORE INTO journal_compacted VALUES(?)', (body['revision'],))
            self.db.execute('UPDATE journal_reviews SET result=? WHERE result=?', (wire, old))
            current = self.store.record(body['effects'][0]['record']) if body['effects'] else None
            if current and 'action' in current['groups'] and current['tokens'] == body['effects'][0]['tokens']:
                self.db.execute('UPDATE journal_records SET groups_json=? WHERE record_id=?', ('{"action":null}', current['record']))
            return True

    def prune_local(self, *, limit=100):
        """Clear displayed terminal payloads; retain every numbered origin slot."""
        count = 0
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise JournalError('Invalid local retention budget')
        with self.db.transaction():
            last = int(self.db.scalar("SELECT value FROM journal_local WHERE name='retention_scan_seq'") or 0)
            rows = self.db.all('SELECT o.*,s.first_display_at FROM journal_outbox o JOIN journal_seen s USING(proposal_id) '
                               'WHERE decision IS NOT NULL AND seq>? ORDER BY seq LIMIT ?', (last, limit))
            for row in rows:
                if unpack(bytes(row['wire']))['body'].get('type') != 'proposal':
                    continue
                decision = unpack(bytes(row['decision']))['body']
                if decision['outcome'] == 'rejected':
                    if datetime.fromisoformat(row['first_display_at']) > self.clock() - timedelta(days=7):
                        continue
                    # A rejection has no financial effects, so its original
                    # signed commit itself is already a compact outcome proof.
                    proof = bytes(row['decision'])
                else:
                    retained = self.db.scalar('SELECT wire FROM journal_commits WHERE proposal_id=?', (row['proposal_id'],))
                    if retained is None or not is_receipt(unpack(bytes(retained))['body']):
                        continue
                    proof = bytes(retained)
                if proposal_hash(row['wire']) != decision['proposal_hash']:
                    raise JournalError('Local decision differs from its saved proposal')
                self.db.execute('DELETE FROM journal_drafts WHERE wire=?', (row['wire'],))
                self.db.execute('DELETE FROM journal_candidates WHERE proposal_id=?', (row['proposal_id'],))
                self.db.execute('UPDATE journal_outbox SET wire=?,decision=? WHERE seq=?', (proof, proof, row['seq']))
                count += 1
            last = rows[-1]['seq'] if rows else 0
            if last >= self.db.scalar('SELECT COALESCE(MAX(seq),0) FROM journal_outbox'):
                last = 0
            self.db.execute("INSERT INTO journal_local VALUES('retention_scan_seq',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (str(last),))
            if self.db.has_table('journal_mail_in'):
                self.db.execute('DELETE FROM journal_mail_in WHERE rowid IN '
                                '(SELECT rowid FROM journal_mail_in WHERE processed=1 ORDER BY rowid LIMIT ?)', (limit,))
            if self.db.has_table('journal_rpc'):
                rpc_cursor = self.db.scalar("SELECT value FROM journal_local WHERE name='retention_rpc_scan'") or ''
                markers = self.db.all("SELECT name,value FROM journal_local WHERE (name LIKE 'rpc_proposal:%' OR name LIKE 'rpc_changes:%') "
                                      'AND name>? ORDER BY name LIMIT ?', (rpc_cursor, limit))
                for marker in markers:
                    kind, identifier = marker['name'].split(':', 1)
                    if kind == 'rpc_proposal':
                        original = self.db.scalar('SELECT wire FROM journal_outbox WHERE proposal_id=? AND decision IS NOT NULL', (marker['value'],))
                        eligible = original is not None and unpack(bytes(original))['body'].get('type') != 'proposal'
                    else:
                        eligible = bool(self.db.scalar('SELECT 1 FROM journal_compacted WHERE revision=?', (int(marker['value']),)))
                    if eligible:
                        self.db.execute('DELETE FROM journal_mail_out WHERE wire IN (SELECT wire FROM journal_rpc WHERE id=?)', (identifier,))
                        self.db.execute('DELETE FROM journal_rpc WHERE id=?', (identifier,))
                        self.db.execute('DELETE FROM journal_local WHERE name=?', (marker['name'],))
                next_marker = markers[-1]['name'] if len(markers) == limit else ''
                self.db.execute("INSERT INTO journal_local VALUES('retention_rpc_scan',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (next_marker,))
        from .form_basis import prune
        prune(self.store)
        return count
