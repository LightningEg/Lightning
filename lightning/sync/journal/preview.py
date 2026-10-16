"""Disposable encrypted in-memory command previews; never write the live ledger."""
import os
from pathlib import Path

from lightning.database.connection import Database
from lightning.bootstrap import _wire_services


def changes(container, action):
    from .finance import attach
    from .commands import execute
    db = Database(':memory:', key=os.urandom(32))
    try:
        container.db.conn.backup(db.conn)
        from .form_basis import workspace
        workspace(db)
        copy = _wire_services(db, Path('.'))
        store = attach(copy)
        before = store.adapter.graph.snapshot()
        with db.transaction(), store.adapter.writing():
            execute(copy, store.adapter.graph, action)
        after = store.adapter.graph.snapshot()
        return [(table, before.get((table, key)), after.get((table, key)))
                for table, key in sorted(before.keys() | after.keys())
                if before.get((table, key)) != after.get((table, key))]
    finally:
        db.close()
