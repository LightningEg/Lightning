"""Owner-signed legacy retirement fence, before native journal publication.

The caller holds the profile/session gate. Retirement is deliberately permanent:
the frozen v1 record cannot be reopened by v1's ordinary take-back operation.
The original encrypted baseline and any explicitly stranded copy are retained.
Native publication and interrupted-cutover UI consume this primitive separately.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

from lightning.sync.copies import content_fingerprint, sha256_file, verify_copy
from lightning.sync.state import HomeState
from lightning.sync.identity import verify_signature

from .codec import JournalError, authenticate, canonical, fields, hash_value, number, seal, unpack, uuid


def validate(body):
    fields(body, ('type', 'version', 'profile', 'legacy_home', 'lineage', 'checkpoint', 'legacy_epoch',
                  'generation', 'home', 'home_key', 'owner_key', 'baseline_sha256', 'baseline_fingerprint', 'stranded', 'legacy_signature'))
    if type(body['version']) is not int or body['version'] != 1 or body['type'] != 'legacy-journal-cutover':
        raise JournalError('Unsupported legacy cutover certificate')
    for key in ('profile', 'legacy_home', 'lineage', 'checkpoint', 'generation', 'home'):
        uuid(body[key])
    for key in ('baseline_sha256', 'baseline_fingerprint'):
        hash_value(body[key])
    number(body['legacy_epoch'])
    if type(body['stranded']) is not list or len(body['stranded']) > 1:
        raise JournalError('Choose the exact stranded checkout to retain')
    for value in body['stranded']:
        uuid(value)
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        for key in ('home_key', 'owner_key'):
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(body[key]))
    except (ValueError, TypeError) as error:
        raise JournalError('Invalid cutover authority key') from error
    if body['home'] != body['legacy_home'] or body['home_key'] == body['owner_key']:
        raise JournalError('Initial cutover needs the existing home and an independent owner key')
    signed = {key: value for key, value in body.items() if key != 'legacy_signature'}
    if not verify_signature(body['home_key'], canonical(signed), body['legacy_signature']):
        raise JournalError('The existing home did not sign this cutover')
    canonical(body)


def _intent(body):
    return {key: value for key, value in body.items() if key != 'legacy_signature'}


def prepare(node, baseline, *, owner, identity, generation, retained_checkout=None):
    """Prepare a reviewable ticket without retiring or changing either ledger."""
    uuid(generation)
    baseline = Path(baseline)
    if baseline.is_symlink() or not baseline.is_file() or baseline.resolve() == node.live.resolve():
        raise JournalError('Keep a separate verified encrypted baseline')
    with node._owner_step():
        model = node.model
        if identity.device_id != model.home_id or owner.public_key == identity.public_key:
            raise JournalError('Cut over on the existing home with an independent owner credential')
        if node.store.unresolved_promotion() is not None:
            raise JournalError('Finish the received legacy return before cutover')
        stranded = []
        if model.state is not HomeState.AT_HOME:
            if (model.state is not HomeState.LENT or model.active is None or
                    retained_checkout != model.active.grant.checkout_id):
                raise JournalError('Receive the legacy return or explicitly retain the stranded checkout')
            stranded = [retained_checkout]
        elif retained_checkout is not None:
            raise JournalError('The selected stranded checkout is no longer active')
        key = node._key()
        verify_copy(baseline, key, model.profile_id)
        fingerprint = content_fingerprint(baseline, key)
        if content_fingerprint(node.live, key) != fingerprint:
            raise JournalError('The ledger changed; take a fresh baseline before cutover')
        body = dict(type='legacy-journal-cutover', version=1, profile=model.profile_id,
                    legacy_home=model.home_id, lineage=model.lineage_id, checkpoint=model.checkpoint_id,
                    legacy_epoch=model.epoch, generation=generation, home=identity.device_id,
                    home_key=identity.public_key, owner_key=owner.public_key,
                    baseline_sha256=sha256_file(baseline), baseline_fingerprint=fingerprint, stranded=stranded)
        body['legacy_signature'] = identity.sign(canonical(body))
        validate(body)
        return seal(body, owner.sign)


def retirement(control):
    """Read the saved ticket without decoding a deliberately retired v1 model."""
    connection = control._connect()
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='journal_retirement'").fetchone():
            return None
        row = connection.execute('SELECT wire FROM journal_retirement WHERE id=1').fetchone()
        if row is None:
            raise JournalError('Legacy retirement memory is incomplete; keep writes blocked')
        wire = bytes(row[0])
        body = unpack(wire)['body']
        validate(body)
        authenticate(unpack(wire), body['owner_key'])
        return wire
    finally:
        connection.close()


def retire(node, baseline, wire, *, owner_key, fault=lambda phase: None):
    """Commit the immutable fence under the same lock used by lending/returns."""
    envelope = unpack(wire)
    authenticate(envelope, owner_key)
    body = envelope['body']
    validate(body)
    if body['owner_key'] != owner_key:
        raise JournalError('Cutover belongs to another owner credential')
    baseline = Path(baseline)
    with node._owner_step():
        saved = retirement(node.store)
        if saved is not None:
            if _intent(unpack(saved)['body']) != _intent(body):
                raise JournalError('Legacy authority was already retired by a different cutover')
            return saved
        model = node.model
        if node.store.unresolved_promotion() is not None:
            raise JournalError('A legacy promotion must finish before retirement')
        expected = dict(profile=model.profile_id, legacy_home=model.home_id, lineage=model.lineage_id,
                        checkpoint=model.checkpoint_id, legacy_epoch=model.epoch)
        if any(body[key] != value for key, value in expected.items()):
            raise JournalError('The legacy authority changed; prepare cutover again')
        active = model.active.grant.checkout_id if model.state is HomeState.LENT and model.active else None
        if model.state is not HomeState.AT_HOME and (active is None or body['stranded'] != [active]):
            raise JournalError('The active legacy checkout has not been retained explicitly')
        if model.state is HomeState.AT_HOME and body['stranded']:
            raise JournalError('A retained checkout changed before retirement')
        if baseline.is_symlink() or not baseline.is_file() or sha256_file(baseline) != body['baseline_sha256']:
            raise JournalError('The verified legacy baseline changed')
        key = node._key()
        verify_copy(baseline, key, body['profile'])
        if (content_fingerprint(baseline, key) != body['baseline_fingerprint'] or
                content_fingerprint(node.live, key) != body['baseline_fingerprint']):
            raise JournalError('The ledger changed after cutover review')
        with node.store._transaction() as connection:
            row = node.store._authority_row(connection)
            if row is None or row[0] != 'home' or json.loads(row[3]) != model.to_record():
                raise JournalError('Legacy authority changed during retirement')
            connection.execute('CREATE TABLE journal_retirement(id INTEGER PRIMARY KEY CHECK(id=1),wire BLOB NOT NULL)')
            connection.execute('INSERT INTO journal_retirement VALUES(1,?)', (wire,))
            # v1 is frozen: its decoder accepts only integer RECORD_VERSION=1.
            # An unknown string permanently blocks both old and current v1
            # loaders, including their normal owner take-back path.
            record = model.to_record() | dict(version='journal-retired')
            connection.execute('UPDATE authority SET revision=revision+1,record=? WHERE singleton=1',
                               (json.dumps(record, sort_keys=True),))
            fault('legacy_fence_prepared')
        fault('legacy_fence_committed')
        return wire


def _financial_inventory(db):
    from .domain_schema import TABLES
    result = hashlib.sha256(b'lightning-legacy-financial-baseline-v1\n')
    for table, spec in sorted(TABLES.items()):
        keys = [name for name, column in spec['columns'].items() if column['pk']]
        result.update(table.encode() + b'\n')
        for row in db.all(f"SELECT * FROM {table} ORDER BY {','.join(keys)}"):
            result.update(repr(tuple(row)).encode('utf-8') + b'\n')
    return result.hexdigest()


def prepare_candidate(baseline, target, wire, *, key, identity, incarnation, owner_key, fault=lambda phase: None):
    """Build a verified new file; confirmation stays blocked without authority.

    This preflight may run before retirement. It never replaces the live file,
    enrolls owner authority, or edits the immutable recovery baseline.
    """
    from lightning.bootstrap import _wire_services
    from lightning.database.connection import Database
    from lightning.database.snapshot import snapshot, verify_connection
    from .finance import _initialize_metadata
    from .full import enable
    from .device import JournalDevice
    from .home import JournalHome
    from .membership import Membership
    envelope = unpack(wire)
    authenticate(envelope, owner_key)
    body = envelope['body']
    validate(body)
    uuid(incarnation)
    if body['owner_key'] != owner_key or (body['home'], body['home_key']) != (identity.device_id, identity.public_key):
        raise JournalError('Candidate identity differs from the approved cutover')
    baseline, target = Path(baseline), Path(target)
    if (baseline.is_symlink() or not baseline.is_file() or
            baseline.resolve() == target.resolve() or sha256_file(baseline) != body['baseline_sha256']):
        raise JournalError('Use the immutable baseline and a new candidate file')
    verify_copy(baseline, key, body['profile'])
    if content_fingerprint(baseline, key) != body['baseline_fingerprint']:
        raise JournalError('The baseline differs from the cutover review')
    if os.path.lexists(target):
        return inspect_candidate(baseline, target, wire, key=key, identity=identity,
                                 incarnation=incarnation, owner_key=owner_key)
    source = Database(baseline, key=key, read_only=True)
    candidate = None
    try:
        financial = _financial_inventory(source)
        snapshot(source, target)
        candidate = Database(target, key=key)
        candidate.execute('PRAGMA synchronous=FULL')
        c = _wire_services(candidate, target.parent)
        with candidate.transaction():
            store = _initialize_metadata(c, profile=body['profile'], generation=body['generation'], device=identity.device_id,
                incarnation=incarnation, home_key=identity.public_key, origin_key=identity.public_key, role='home')
            enable(store)
            home = JournalHome(store, identity.sign)
            home.approve_origin(identity.device_id, incarnation, identity.public_key)
            device = JournalDevice(store, identity, home)
            Membership(device).initialize({identity.device_id: dict(key=identity.public_key, incarnation=incarnation)}, os.urandom(32))
            candidate.execute("INSERT INTO journal_local VALUES('authority_enrolled','1')")
            candidate.execute("INSERT INTO journal_local VALUES('legacy_cutover',?)", (wire.decode('utf-8'),))
            if _financial_inventory(candidate) != financial:
                raise JournalError('Candidate preparation changed financial records')
            fingerprint = store.fingerprint()
            fault('cutover_candidate_prepared')
        verify_connection(candidate.conn, encrypted=True)
        candidate.close()
        candidate = None
        from lightning.sync.copies import fsync_file
        fsync_file(target)
        fault('cutover_candidate_committed')
        manifest = dict(type='journal-cutover-candidate', version=1, profile=body['profile'], generation=body['generation'],
                        home=identity.device_id, incarnation=incarnation, cutover=digest_intent(body),
                        fingerprint=fingerprint, size=target.stat().st_size, sha256=sha256_file(target))
        return seal(manifest, identity.sign)
    finally:
        if candidate is not None:
            candidate.close()
        source.close()


def digest_intent(body):
    from .codec import digest
    return digest(_intent(body))


def inspect_candidate(baseline, target, wire, *, key, identity, incarnation, owner_key):
    """Resume only a complete, unchanged, never-activated candidate; read only."""
    from lightning.database.connection import Database
    from lightning.database.snapshot import verify_connection
    from .finance import inspect_adapter
    envelope = unpack(wire)
    authenticate(envelope, owner_key)
    body = envelope['body']
    validate(body)
    uuid(incarnation)
    baseline, target = Path(baseline), Path(target)
    if (baseline.is_symlink() or target.is_symlink() or not target.is_file() or
            not baseline.is_file() or baseline.resolve() == target.resolve() or sha256_file(baseline) != body['baseline_sha256']):
        raise JournalError('Candidate or immutable baseline is missing or changed')
    source, candidate = Database(baseline, key=key, read_only=True), Database(target, key=key, read_only=True)
    try:
        verify_connection(candidate.conn, encrypted=True)
        verify_copy(baseline, key, body['profile'])
        if content_fingerprint(baseline, key) != body['baseline_fingerprint']:
            raise JournalError('The recovery baseline differs from its certificate')
        if not candidate.has_table('journal_domain_contract'):
            raise JournalError('Candidate preparation was incomplete; preserve it and use a new staging file')
        config = json.loads(candidate.scalar('SELECT config FROM journal_meta WHERE id=1') or '{}')
        expected = dict(version=3, profile=body['profile'], generation=body['generation'], device=identity.device_id,
                        incarnation=incarnation, home_key=identity.public_key, origin_key=identity.public_key, role='home')
        if (config != expected or (body['home'], body['home_key']) != (identity.device_id, identity.public_key)
                or body['owner_key'] != owner_key):
            raise JournalError('Existing candidate has another identity or authority')
        if (candidate.scalar('SELECT COUNT(*) FROM journal_outbox') or candidate.scalar('SELECT COUNT(*) FROM journal_commits')
                or candidate.scalar('SELECT next_seq FROM journal_meta') != 1
                or candidate.scalar("SELECT value FROM journal_local WHERE name='authority_enrolled'") != '1'):
            raise JournalError('A used or unfenced candidate cannot resume as a new home')
        saved = candidate.scalar("SELECT value FROM journal_local WHERE name='legacy_cutover'")
        if saved is None:
            raise JournalError('Candidate cutover memory is missing')
        old = unpack(saved.encode('utf-8'))
        authenticate(old, owner_key)
        validate(old['body'])
        if digest_intent(old['body']) != digest_intent(body) or _financial_inventory(source) != _financial_inventory(candidate):
            raise JournalError('Candidate differs from its approved financial baseline')
        adapter = inspect_adapter(candidate, config)
        fingerprint = adapter.fingerprint()
    finally:
        source.close()
        candidate.close()
    manifest = dict(type='journal-cutover-candidate', version=1, profile=body['profile'], generation=body['generation'],
                    home=identity.device_id, incarnation=incarnation, cutover=digest_intent(body),
                    fingerprint=fingerprint, size=target.stat().st_size, sha256=sha256_file(target))
    return seal(manifest, identity.sign)


def verify_ready(node, baseline, target, wire, manifest, *, key, identity, incarnation, owner_key):
    """Verify the durable v1 fence and staged file before a native publisher acts."""
    with node._owner_step():
        saved = retirement(node.store)
        if saved is None or digest_intent(unpack(saved)['body']) != digest_intent(unpack(wire)['body']):
            raise JournalError('Retire legacy authority before publishing the journal home')
        current = inspect_candidate(baseline, target, wire, key=key, identity=identity,
                                    incarnation=incarnation, owner_key=owner_key)
        submitted = unpack(manifest)
        authenticate(submitted, identity.public_key)
        if submitted['body'] != unpack(current)['body']:
            raise JournalError('Staged candidate changed after preparation')
        if content_fingerprint(node.live, key) != unpack(saved)['body']['baseline_fingerprint']:
            raise JournalError('The retired live file changed; preserve both copies for comparison')
        return submitted['body']
