"""Connection-local action history. Backups and phone copies never contain undo data."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
from uuid import uuid4

from lightning.core.errors import ValidationError

_ACTION = ContextVar("lightning_undo_action", default=None)
_EXCLUDED = {"schema_migrations", "audit_log", "profile_identity"}


def recording_action():
    return _ACTION.get() is not None


@contextmanager
def user_action(label):
    token = _ACTION.set((uuid4().hex, str(label)[:120]))
    try:
        yield
    finally:
        _ACTION.reset(token)


def _name(value):
    return '"' + value.replace('"', '""') + '"'


class UndoService:
    def __init__(self, db, audit=None):
        self.db, self.audit = db, audit
        self.validate = None
        self._tables = None

    def prepare(self, conn):
        if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE name='undo_control'").fetchone():
            return
        conn.execute("CREATE TEMP TABLE undo_control(group_id INTEGER)")
        conn.execute("INSERT INTO undo_control VALUES(NULL)")
        conn.execute("CREATE TEMP TABLE undo_groups(id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT UNIQUE, label TEXT, undone INTEGER DEFAULT 0)")
        conn.execute("CREATE TEMP TABLE undo_records(id INTEGER PRIMARY KEY, group_id INTEGER, table_name TEXT, before_json TEXT, after_json TEXT)")
        tables = conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table'").fetchall()
        for table in tables:
            name, sql = table["name"], table["sql"] or ""
            if self._tables is not None and name not in self._tables:
                continue
            if (name in _EXCLUDED or name.startswith(("sqlite_", "transactions_fts", "undo_"))
                    or "VIRTUAL TABLE" in sql.upper()):
                continue
            columns = conn.execute(f"PRAGMA table_info({_name(name)})").fetchall()
            if not any(c["pk"] for c in columns) or any("BLOB" in c["type"].upper() for c in columns):
                continue
            def row_json(prefix):
                values = []
                for column in columns:
                    col = column["name"]
                    values.extend(("'" + col.replace("'", "''") + "'", f"{prefix}.{_name(col)}"))
                return "json_object(" + ",".join(values) + ")"
            for operation, before, after in (("INSERT", "NULL", row_json("NEW")),
                                             ("UPDATE", row_json("OLD"), row_json("NEW")),
                                             ("DELETE", row_json("OLD"), "NULL")):
                conn.execute(f"CREATE TEMP TRIGGER {_name('undo_' + name + '_' + operation)} "
                             f"AFTER {operation} ON main.{_name(name)} "
                             "WHEN (SELECT group_id FROM undo_control) IS NOT NULL BEGIN "
                             "INSERT INTO undo_records(group_id,table_name,before_json,after_json) "
                             f"VALUES((SELECT group_id FROM undo_control),'{name}',{before},{after}); END")

    def prepare_for_tables(self, conn, tables):
        """Install temporary capture triggers for a caller's explicit table allowlist."""
        if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE name='undo_control'").fetchone():
            return
        self._tables = frozenset(tables)
        self.prepare(conn)

    def begin(self, conn, label=None):
        action = _ACTION.get()
        if label and action is None:
            action = (uuid4().hex, str(label)[:120])
        self.prepare(conn)
        if action is None:
            conn.execute("UPDATE undo_control SET group_id=NULL")
            return
        token, label = action
        group = conn.execute("SELECT id FROM undo_groups WHERE token=?", (token,)).fetchone()
        if group is None:
            cursor = conn.execute("INSERT INTO undo_groups(token,label) VALUES(?,?)", (token, label))
            group_id = cursor.lastrowid
        else:
            group_id = group["id"]
        conn.execute("UPDATE undo_control SET group_id=?", (group_id,))

    def finish(self, conn):
        active = conn.execute("SELECT group_id FROM undo_control").fetchone()[0]
        if active is not None and conn.execute("SELECT 1 FROM undo_records WHERE group_id=?", (active,)).fetchone():
            conn.execute("DELETE FROM undo_records WHERE group_id IN (SELECT id FROM undo_groups WHERE undone=1)")
            conn.execute("DELETE FROM undo_groups WHERE undone=1")
        conn.execute("UPDATE undo_control SET group_id=NULL")
        conn.execute("DELETE FROM undo_groups WHERE id NOT IN (SELECT group_id FROM undo_records)")
        conn.execute("DELETE FROM undo_groups WHERE id NOT IN (SELECT id FROM undo_groups ORDER BY id DESC LIMIT 20)")
        conn.execute("DELETE FROM undo_records WHERE group_id NOT IN (SELECT id FROM undo_groups)")

    def cancel(self, conn):
        """Leave no active capture group when a command fails."""
        if conn.execute("SELECT 1 FROM sqlite_temp_master WHERE name='undo_control'").fetchone():
            conn.execute("UPDATE undo_control SET group_id=NULL")

    def available(self):
        self.prepare(self.db.conn)
        undo = self.db.one("SELECT id,label FROM undo_groups WHERE undone=0 ORDER BY id DESC LIMIT 1")
        redo = self.db.one("SELECT id,label FROM undo_groups WHERE undone=1 ORDER BY id ASC LIMIT 1")
        return {"undo": dict(undo) if undo else None, "redo": dict(redo) if redo else None}

    def current_fingerprint(self):
        """The synchronized ledger fingerprint, or None outside a journal profile."""
        fingerprint = getattr(self, "journal_fingerprint", None)
        return fingerprint() if fingerprint is not None else None

    def replay(self, *, redo=False, expected_id=None, expected_fingerprint=None):
        # Pick the top group and its records only after BEGIN IMMEDIATE. Otherwise a second
        # request can commit a newer group between the stale-form check and the replay.
        with self.db.transaction():
            if expected_fingerprint is not None:
                # A journal history command is tied to the exact synchronized ledger the
                # user saw. Local undo ids are meaningful only on the home, so never let a
                # stale command overwrite rows changed since it was submitted.
                row = self.db.one("SELECT config FROM journal_meta WHERE id=1")
                if row is None:
                    raise ValidationError("This history action is only available on the journal home.")
                fingerprint = self.current_fingerprint()
                if fingerprint != expected_fingerprint:
                    raise ValidationError("The ledger changed. Open history again before undoing this action.")
            choice = self.available()["redo" if redo else "undo"]
            if choice is None or (expected_id is not None and int(expected_id) != choice["id"]):
                raise ValidationError("History changed. Open the page again before undoing this action.")
            records = self.db.all(
                "SELECT * FROM undo_records WHERE group_id=? ORDER BY id " + ("ASC" if redo else "DESC"),
                (choice["id"],),
            )
            self.db.execute("UPDATE undo_control SET group_id=NULL")
            self.db.execute("PRAGMA defer_foreign_keys=ON")
            # Verify the action's entire starting state before executing anything.
            # During replay, a recorded cascade can then be encountered already
            # applied by its parent trigger without hiding a stale outside edit.
            metadata, verified = {}, set()
            for record in records:
                table = record["table_name"]
                if table not in metadata:
                    metadata[table] = [c["name"] for c in self.db.all(f"PRAGMA table_info({_name(table)})") if c["pk"]]
                before = json.loads(record["before_json"]) if record["before_json"] else None
                after = json.loads(record["after_json"]) if record["after_json"] else None
                expected = before if redo else after
                reference = expected if expected is not None else (after if redo else before)
                keys = metadata[table]
                params = tuple(reference[key] for key in keys)
                identity = (table, params)
                if identity in verified:
                    continue
                verified.add(identity)
                where = " AND ".join(f"{_name(key)} IS ?" for key in keys)
                current = self.db.one(f"SELECT * FROM {_name(table)} WHERE {where}", params)
                if (dict(current) if current else None) != expected:
                    raise ValidationError("This action has changed since it was saved and cannot be undone safely.")
            for record in records:
                before = json.loads(record["before_json"]) if record["before_json"] else None
                after = json.loads(record["after_json"]) if record["after_json"] else None
                expected, target = (before, after) if redo else (after, before)
                table = record["table_name"]
                keys = metadata[table]
                reference = expected if expected is not None else target
                where = " AND ".join(f"{_name(key)} IS ?" for key in keys)
                params = tuple(reference[key] for key in keys)
                current = self.db.one(f"SELECT * FROM {_name(table)} WHERE {where}", params)
                current_data = dict(current) if current else None
                if current_data != expected and current_data == target:
                    continue  # a recorded child deletion already ran through its parent
                if current_data != expected:
                    raise ValidationError("This action has changed since it was saved and cannot be undone safely.")
                if target is None:
                    self.db.execute(f"DELETE FROM {_name(table)} WHERE {where}", params)
                elif expected is None:
                    cols = list(target)
                    self.db.execute(f"INSERT INTO {_name(table)} ({','.join(map(_name, cols))}) "
                                    f"VALUES({','.join('?' for _ in cols)})", tuple(target[c] for c in cols))
                else:
                    cols = list(target)
                    self.db.execute(f"UPDATE {_name(table)} SET " + ",".join(f"{_name(c)}=?" for c in cols)
                                    + f" WHERE {where}", tuple(target[c] for c in cols) + params)
            if self.db.all("PRAGMA foreign_key_check"):
                raise ValidationError("Undo would leave an incomplete link. No changes were made.")
            if self.validate:
                self.validate(records)
            self.db.execute("UPDATE undo_groups SET undone=? WHERE id=?", (0 if redo else 1, choice["id"]))
            if self.audit:
                self.audit.record("history", choice["id"], "redo" if redo else "undo", choice["label"])
        return choice["label"]

    def clear(self):
        self.prepare(self.db.conn)
        self.db.execute("DELETE FROM undo_records")
        self.db.execute("DELETE FROM undo_groups")
