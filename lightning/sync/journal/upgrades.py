"""Explicit upgrades inside the experimental journal, never a v1 conversion.

Callers hold the profile/session lock and recreate device/UI runtime objects
after success. A replica upgrades only from a verified home checkpoint; it
cannot manufacture its own full-domain baseline from local integer IDs.
"""
from .codec import JournalError


def upgrade_home(store, *, fault=lambda phase: None):
    from .full import enable
    if store.config['role'] != 'home' or store.adapter is None:
        raise JournalError('Only an open journal home can upgrade its domain')
    if getattr(store.adapter, 'full_domain', False) and store.config['version'] == 3:
        return store.adapter
    old, config = store.adapter, dict(store.config)
    try:
        with store.confirming(), store.db.transaction():
            store.require_confirmation_authority()
            adapter = enable(store, _upgrade=True)
            adapter.fingerprint()
            fault('home_domain_prepared')
        fault('home_domain_committed')
        return adapter
    except BaseException:
        # A post-commit interruption is resumed by reopening the database. Do
        # not reinstall an old in-memory adapter over a committed new format.
        import json
        actual = json.loads(store.db.scalar('SELECT config FROM journal_meta WHERE id=1'))
        if actual['version'] == config['version']:
            store.adapter, store.config = old, config
            store.db.conn.set_authorizer(old._authorize)
            store.db.journal_guard = old._authorize
        raise


def upgrade_replica(store, source, manifest, *, source_key, fault=lambda phase: None):
    from .snapshots import repair
    if store.config['role'] != 'replica':
        raise JournalError('Only a replica installs a domain upgrade checkpoint')
    return repair(store, source, manifest, source_key=source_key, fault=fault, upgrade=True)
