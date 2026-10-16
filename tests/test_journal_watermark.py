"""Ordinary profile restores cannot rewind independently stored origin state."""
import json
import shutil

import pytest

from test_journal_finance import devices, groups
from test_journal_authority import memories
from lightning.bootstrap import build
from lightning.database.snapshot import snapshot
from lightning.sync.journal.authority import AuthorityMemory
from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.device import JournalDevice
from lightning.sync.journal.finance import attach


def backup(device, target):
    db = device.c.db
    db.conn.set_authorizer(None)
    try:
        snapshot(db, target)
    finally:
        db.conn.set_authorizer(device.adapter._authorize)


def restore(device, source):
    path, key = device.c.db.path, device.c.db.copy_key()
    device.c.db.close()
    shutil.copyfile(source, path)
    container = build(path, key=key, experimental_journal=True)
    return JournalDevice(attach(container), device.identity)


@pytest.mark.parametrize('which', ['origin', 'history', 'format'])
def test_restored_file_is_blocked_before_reusing_counters_or_confirming(devices, tmp_path, which):
    home, pc = devices
    _, controls = memories(devices, tmp_path)
    device = pc if which == 'origin' else home
    old = tmp_path/'old.db'
    backup(device, old)
    reopened = None
    try:
        if which == 'origin':
            pc.save(groups(pc))
        elif which == 'history':
            pc.save(groups(pc))
            pc.sync_with(home.home)
        else:
            from lightning.sync.journal.upgrades import upgrade_home
            upgrade_home(home.store)
        reopened = restore(device, old)
        control = controls[1 if which == 'origin' else 0]
        with pytest.raises(JournalError, match='behind its private checkpoint'):
            control.bind(reopened.store)
        with pytest.raises(JournalError, match='checkpoint is required'):
            reopened.save(groups(reopened))
        assert reopened.c.db.scalar('SELECT next_seq FROM journal_meta') == 1
    finally:
        if reopened:
            reopened.c.db.close()
        for control in controls:
            control.close()


def test_copied_origin_cannot_write_from_a_second_path(devices, tmp_path):
    home, pc = devices
    _, controls = memories(devices, tmp_path)
    target = tmp_path/'duplicate.db'
    backup(pc, target)
    clone = build(target, key=pc.c.db.copy_key(), experimental_journal=True)
    try:
        with pytest.raises(JournalError, match='another file'):
            controls[1].bind(attach(clone))
        assert controls[1].db.execute('SELECT document FROM origin_checkpoint').fetchone()[0]
    finally:
        clone.db.close()
        for control in controls:
            control.close()


def test_nested_save_does_not_checkpoint_until_outer_commit_and_rollback_reuses_no_saved_slot(devices, tmp_path):
    home, pc = devices
    _, controls = memories(devices, tmp_path)
    memory = controls[1]
    initial = memory.db.execute('SELECT document FROM origin_checkpoint').fetchone()[0]
    try:
        with pytest.raises(RuntimeError, match='cancel'):
            with pc.c.db.transaction():
                pc.save(groups(pc))
                assert memory.db.execute('SELECT document FROM origin_checkpoint').fetchone()[0] == initial
                raise RuntimeError('cancel')
        assert not pc.store.pending()
        assert memory.db.execute('SELECT document FROM origin_checkpoint').fetchone()[0] == initial
        with pc.c.db.transaction():
            first = pc.save(groups(pc))
            second = pc.save(groups(pc, '-8'))
            assert memory.db.execute('SELECT document FROM origin_checkpoint').fetchone()[0] == initial
        saved = json.loads(memory.db.execute('SELECT document FROM origin_checkpoint').fetchone()[0])
        assert saved['seq'] == 2
        assert pc.store.pending() == [first, second]
    finally:
        for control in controls:
            control.close()


def test_interrupted_private_commit_recovers_signed_durable_outbox_without_reusing_slot(devices, tmp_path, monkeypatch):
    from lightning.sync.journal.watermark import Watermark
    home, pc = devices
    _, controls = memories(devices, tmp_path)
    memory = controls[1]
    write = Watermark._write
    def fail(*args):
        raise OSError('private disk full')
    reopened = None
    try:
        monkeypatch.setattr(Watermark, '_write', fail)
        with pytest.raises(OSError, match='private disk full'):
            pc.save(groups(pc))
        wire = pc.store.pending()[0]
        assert json.loads(memory.db.execute('SELECT document FROM origin_checkpoint').fetchone()[0])['seq'] == 0
        monkeypatch.setattr(Watermark, '_write', write)
        path, key = pc.c.db.path, pc.c.db.copy_key()
        pc.c.db.close()
        memory.close()
        container = build(path, key=key, experimental_journal=True)
        reopened = JournalDevice(attach(container), pc.identity)
        controls[1] = AuthorityMemory(tmp_path/'control-1.db', profile=reopened.store.config['profile'])
        controls[1].bind(reopened.store)
        assert reopened.store.pending() == [wire]
        reopened.save(groups(reopened, '-8'))
        assert reopened.c.db.scalar('SELECT next_seq FROM journal_meta') == 3
        assert reopened.store.pending()[0] == wire
    finally:
        if reopened:
            reopened.c.db.close()
        for control in controls:
            if not control._closed:
                control.close()


@pytest.mark.parametrize('damage', ['missing', 'empty', 'invalid'])
def test_missing_checkpoint_and_closed_control_never_reset_an_enrolled_origin(devices, tmp_path, damage):
    home, pc = devices
    _, controls = memories(devices, tmp_path)
    try:
        if damage == 'missing':
            controls[1].db.execute('DELETE FROM origin_checkpoint')
        else:
            controls[1].db.execute('UPDATE origin_checkpoint SET document=?', (None if damage == 'empty' else '{}',))
        with pytest.raises(JournalError, match='damaged'):
            pc.save(groups(pc))
        assert pc.c.db.scalar('SELECT next_seq FROM journal_meta') == 1
        controls[0].close()
        with pytest.raises(JournalError, match='checkpoint is required'):
            home.save(groups(home))
        assert not controls[0].can_confirm(home.store)
    finally:
        for control in controls:
            if not control._closed:
                control.close()


def test_unrecorded_financial_change_is_detected_on_reopen(devices, tmp_path):
    home, pc = devices
    _, controls = memories(devices, tmp_path)
    container = None
    try:
        # Simulate an externally modified encrypted file, bypassing all runtime
        # guards. Matching cursor/counter values must not make it trusted.
        with pc.adapter.writing():
            pc.c.db.execute('UPDATE ledger_entries SET amount_e6=amount_e6+1000000, amount_base_e6=amount_base_e6+1000000 WHERE id=(SELECT MIN(id) FROM ledger_entries)')
        path, key = pc.c.db.path, pc.c.db.copy_key()
        pc.c.db.close()
        container = build(path, key=key, experimental_journal=True)
        with pytest.raises(JournalError, match='Financial state differs'):
            controls[1].bind(attach(container))
    finally:
        if container:
            container.db.close()
        for control in controls:
            control.close()
