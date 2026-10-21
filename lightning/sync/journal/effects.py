"""Exact row effects for every synchronized table (J6a).

The home records which rows a confirmation touched (temporary triggers), and
publishes their final values with references as UUIDs. A replica applies those
rows exactly: no service, rule or automation runs there. Each row has a stable
identity: integer `id` keys map through `journal_ids`; any other key is its key
columns with references mapped. Per-row hashes give an incremental fingerprint.
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4, uuid5

from lightning.core.errors import ValidationError

from .codec import JournalError, canonical, fields, uuid

SCHEMA = 2
# Synchronized tables of the areas enabled so far. A table joins when its area
# does; any write to a table outside this set is refused during confirmation.
def _synced():
    from .areas import AREAS
    return tuple(dict.fromkeys(table for area in AREAS for table in area.TABLES))


SYNCED = _synced()
# Services clear these as a no-op on uncovered records; changing a row aborts.
GUARDED = ()
# Baseline catalog rows are referenced by UUID but not replicated yet.
CATALOG = ()
# Replicas start from the home's checkpoint (J6b), so identities are copied. A
# natural key still keeps an identity stable when a service rewrites a row
# (a reposted line keeps its UUID); other new rows get random UUIDs.
def _from_areas(name):
    from .areas import AREAS
    return {key: value for area in AREAS for key, value in getattr(area, name, {}).items()}


NATURAL = {"transactions": ("ref",), "counterparties": ("normalized_name",), "accounts": ("code",),
           "financial_assets": ("code",), "categories": ("code",), "asset_classes": ("code",)} | _from_areas("NATURAL")
# References an area's table keeps without a declared foreign key: {table: {column: target}}.
EXTRA_REFS = _from_areas("REFS")
MAX_ROWS = 64
# An action too large to carry inline (a statement import) travels as hashed chunks
# beside its commit, applied only once all have arrived (proposal §6).
CHUNK_BYTES = 24 * 1024
MAX_CHUNKS = 44  # About 1 MiB of rows for one action.
WALL_CLOCK = {"created_at", "updated_at"}


class Table:
    def __init__(self, db, name):
        info = db.all(f"PRAGMA table_info({name})")
        if not info:
            raise JournalError(f"Unknown synchronized table {name}")
        self.name = name
        self.types = {row["name"]: row["type"].upper() for row in info}
        self.notnull = {row["name"] for row in info if row["notnull"]}
        self.key = [row["name"] for row in sorted(info, key=lambda row: row["pk"]) if row["pk"]]
        self.rowid = self.key == ["id"] and self.types["id"] == "INTEGER"
        self.columns = [row["name"] for row in info if not (self.rowid and row["name"] == "id")]
        keys = db.all(f"PRAGMA foreign_key_list({name})")
        self.refs = {row["from"]: row["table"] for row in keys} | EXTRA_REFS.get(name, {})
        # A child row deleted with its parent belongs to it: a transaction's lines, a rule's conditions.
        self.owners = {row["from"]: row["table"] for row in keys if row["on_delete"].upper() == "CASCADE"}
        if set(self.types.values()) - {"INTEGER", "TEXT", "REAL"}:
            raise JournalError(f"{name} has a column type the journal cannot carry yet")


class Replicator:
    def __init__(self, db, namespace, *, resolve=lambda value: value, tables=SYNCED):
        self.db, self.namespace, self.resolve = db, UUID(namespace), resolve
        self.tables = {name: Table(db, name) for name in tables}
        for table in self.tables.values():
            for column, target in table.refs.items():
                if target not in self.tables and target not in CATALOG:
                    raise JournalError(f"{table.name}.{column} refers to an unsynchronized table")
        # Parents before children; self references are ordered by the home's row order.
        order, seen = [], set()
        def visit(name):
            if name not in seen:
                seen.add(name)
                for target in self.tables[name].refs.values():
                    if target in self.tables and target != name:
                        visit(target)
                order.append(name)
        for name in sorted(self.tables):
            visit(name)
        self.order = order
        self.owned = {}
        for table in self.tables.values():
            for column, parent in table.owners.items():
                if parent in self.tables and parent != table.name:
                    self.owned.setdefault(parent, []).append((table.name, column))

    def record_hashes(self, name, local_id, depth=0):
        """Fingerprint hashes of the rows a record owns, recursively; an unmapped row counts as changed."""
        result = []
        for child, column in self.owned.get(name, ()):
            table = self.tables[child]
            for row in self.db.all(f"SELECT * FROM {child} WHERE {column}=? ORDER BY rowid", (local_id,)):
                if table.rowid:
                    identity = self.db.scalar("SELECT uuid FROM journal_ids WHERE entity=? AND local_id=?", (child, row["id"]))
                else:
                    try:
                        identity = [self._mapped(table.refs[key], row[key]) if key in table.refs else row[key] for key in table.key]
                    except LookupError:
                        identity = None
                if identity is None:
                    result.append(child + ":unmapped")
                    continue
                slot = child + ":" + canonical(identity).decode()
                result.append(slot + "=" + str(self.db.scalar("SELECT hash FROM journal_fp WHERE uuid=?", (slot,))))
                if table.rowid and depth < 4:
                    result.extend(self.record_hashes(child, row["id"], depth + 1))
        return result

    def _mapped(self, entity, local_id):
        if local_id is None:
            return None
        value = self.db.scalar("SELECT uuid FROM journal_ids WHERE entity=? AND local_id=?", (entity, local_id))
        if value is None:
            raise LookupError(entity)
        return value

    # -- identity -----------------------------------------------------------
    def uid(self, entity, local_id):
        if local_id is None:
            return None
        known = self.db.scalar("SELECT uuid FROM journal_ids WHERE entity=? AND local_id=?", (entity, local_id))
        if known:
            return known
        row = self.db.one(f"SELECT * FROM {entity} WHERE id=?", (local_id,))
        if row is None:
            raise ValidationError("A referenced record is missing")
        if entity == "ledger_entries":
            value = str(uuid5(self.namespace, f"ledger_entries:{self.uid('transactions', row['transaction_id'])}:{row['line_no']}"))
        elif entity in NATURAL:
            value = str(uuid5(self.namespace, f"{entity}:" + ":".join(str(row[column]) for column in NATURAL[entity])))
        else:
            value = str(uuid4())
        if self.db.scalar("SELECT 1 FROM journal_ids WHERE entity=? AND uuid=?", (entity, value)):
            value = str(uuid4())  # A natural key reused after its row was removed.
        self.bind(entity, value, local_id)
        return value

    def bind(self, entity, value, local_id):
        self.db.execute("INSERT INTO journal_ids VALUES(?,?,?)", (entity, value, local_id))

    def local(self, entity, value):
        if value is None:
            return None
        uuid(value)
        if entity == "transactions":
            value = self.resolve(value)
        result = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (entity, value))
        if result is None:
            raise ValidationError("A referenced record is not in the confirmed copy")
        return result

    def identity(self, table, row):
        if table.rowid:
            return self.uid(table.name, row["id"])
        return [self.uid(table.refs[column], row[column]) if column in table.refs else row[column] for column in table.key]

    def _ref(self, table, column, value):
        target = table.refs[column]
        if (column in EXTRA_REFS.get(table.name, {}) and value is not None
                and not self.db.scalar("SELECT 1 FROM journal_ids WHERE entity=? AND local_id=?", (target, value))
                and not self.db.scalar(f"SELECT 1 FROM {target} WHERE id=?", (value,))):
            # An undeclared reference left by a removed record (reserve history): a stable placeholder.
            return str(uuid5(self.namespace, f"orphan:{target}:{value}"))
        return self.uid(target, value)

    def encode(self, table, row):
        return {column: self._ref(table, column, row[column]) if column in table.refs
                else _real(row[column]) if table.types[column] == "REAL" else row[column] for column in table.columns}

    # -- capture --------------------------------------------------------------
    def install(self):
        """Temporary triggers; the caller lifts the authorizer for this fixed DDL."""
        self.db.execute("CREATE TEMP TABLE IF NOT EXISTS journal_touched_rows(tbl TEXT NOT NULL,rid INTEGER,gone TEXT,"
                        "UNIQUE(tbl,rid,gone))")
        for table in self.tables.values():
            old = "json_array(" + ",".join(f"OLD.{column}" for column in table.key) + ")"
            for event, body in (("insert", "INSERT OR IGNORE INTO journal_touched_rows VALUES('{t}',NEW.rowid,NULL);"),
                                ("update", "INSERT OR IGNORE INTO journal_touched_rows VALUES('{t}',NEW.rowid,NULL);"
                                           "INSERT OR IGNORE INTO journal_touched_rows VALUES('{t}',NULL,{old});"),
                                ("delete", "INSERT OR IGNORE INTO journal_touched_rows VALUES('{t}',NULL,{old});")):
                self.db.execute(f"CREATE TEMP TRIGGER IF NOT EXISTS journal_row_{table.name}_{event} AFTER {event.upper()} "
                                f"ON main.{table.name} BEGIN {body.format(t=table.name, old=old)} END")
        for name in GUARDED:
            for event in ("insert", "update", "delete"):
                self.db.execute(f"CREATE TEMP TRIGGER IF NOT EXISTS journal_guard_{name}_{event} AFTER {event.upper()} ON main.{name} "
                                "BEGIN SELECT RAISE(ABORT,'journal: area not covered'); END")

    def reset(self):
        self.db.execute("DELETE FROM journal_touched_rows")

    def capture(self):
        """Final values of every touched row, net of intermediate changes."""
        rows, released = {}, []
        for name in self.order:
            table = self.tables[name]
            # Removed identities first. Their id mappings are released only once all are
            # named (a child key refers to a removed parent) and before a reused row id
            # or natural key can be bound to a new row.
            for (gone,) in self.db.all("SELECT gone FROM journal_touched_rows WHERE tbl=? AND gone IS NOT NULL", (name,)):
                key = json.loads(gone)
                if self._find(table, key) is not None and not table.rowid:
                    continue  # Same key still present (an update): handled below.
                if table.rowid:
                    if self.db.scalar(f"SELECT 1 FROM {name} WHERE id=?", (key[0],)):
                        continue
                    identity = self.db.scalar("SELECT uuid FROM journal_ids WHERE entity=? AND local_id=?", (name, key[0]))
                    if identity is None:
                        continue  # Created and removed inside one action.
                    released.append((name, key[0]))
                else:
                    identity = [self.uid(table.refs[column], value) if column in table.refs else value
                                for column, value in zip(table.key, key)]
                rows[(name, canonical(identity))] = dict(table=name, key=identity, values=None)
        for entity, local_id in released:
            self.db.execute("DELETE FROM journal_ids WHERE entity=? AND local_id=?", (entity, local_id))
        for name in self.order:
            table = self.tables[name]
            for (rid,) in self.db.all(f"SELECT t.rid FROM journal_touched_rows t JOIN main.{name} r ON r.rowid=t.rid "
                                      "WHERE t.tbl=? ORDER BY t.rid", (name,)):
                row = self.db.one(f"SELECT * FROM {name} WHERE rowid=?", (rid,))
                identity = self.identity(table, row)
                rows[(name, canonical(identity))] = dict(table=name, key=identity, values=self.encode(table, row))
        return list(rows.values())

    def _find(self, table, key):
        where = " AND ".join(f"{column} IS ?" for column in table.key)
        return self.db.scalar(f"SELECT rowid FROM {table.name} WHERE {where}", tuple(key))

    # -- validation and replay ------------------------------------------------
    def validate(self, effect, *, bounded=True):
        fields(effect, ("schema", "rows"))
        if type(effect["schema"]) is not int or effect["schema"] != SCHEMA:
            raise JournalError("Unsupported effect schema; update this device")
        rows = effect["rows"]
        if type(rows) is not list or not 1 <= len(rows) <= (MAX_ROWS if bounded else 10**7):
            raise JournalError("Invalid row effects")
        seen = set()
        for item in rows:
            fields(item, ("table", "key", "values"))
            table = self.tables.get(item["table"]) if type(item["table"]) is str else None
            if table is None:
                raise JournalError("Effect writes an area this device does not support; update it")
            if table.rowid:
                uuid(item["key"])
            elif type(item["key"]) is not list or len(item["key"]) != len(table.key):
                raise JournalError("Invalid row key")
            identity = (table.name, canonical(item["key"]))
            if identity in seen:
                raise JournalError("Duplicate row effect")
            seen.add(identity)
            if item["values"] is not None:
                fields(item["values"], table.columns)
                for column, value in item["values"].items():
                    self._typed(table, column, value)
            for column, value in zip(table.key, [] if table.rowid else item["key"]):
                self._typed(table, column, value)

    @staticmethod
    def _typed(table, column, value):
        if value is None:
            if column in table.notnull:
                raise JournalError("Missing required row value")
        elif column in table.refs:
            uuid(value)
        elif table.types[column] == "INTEGER":
            if type(value) is not int:
                raise JournalError("Row integers must be exact")
        elif table.types[column] == "REAL":
            try:
                if type(value) is not str or _real(float(value)) != value:
                    raise ValueError
            except ValueError as error:
                raise JournalError("Row decimals must be exact text") from error
        elif type(value) is not str:
            raise JournalError("Row text must be text")

    def apply(self, effect, *, bounded=True):
        """Exact replay: deletes children first, then upserts parents first.
        Unbounded only for a verified checkpoint repair."""
        self.validate(effect, bounded=bounded)
        rank = {name: index for index, name in enumerate(self.order)}
        rows = effect["rows"]
        for item in sorted((item for item in rows if item["values"] is None), key=lambda item: -rank[item["table"]]):
            table = self.tables[item["table"]]
            if table.rowid:
                local_id = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (table.name, item["key"]))
                if local_id is not None:
                    self.db.execute(f"DELETE FROM {table.name} WHERE id=?", (local_id,))
                    self.db.execute("DELETE FROM journal_ids WHERE entity=? AND local_id=?", (table.name, local_id))
                    if self.db.has_table("journal_fp"):  # The mapping is gone, so capture cannot forget this row's hash.
                        self.db.execute("DELETE FROM journal_fp WHERE uuid=?", (table.name + ":" + canonical(item["key"]).decode(),))
            else:
                key = self._local_key(table, item["key"])
                self.db.execute(f"DELETE FROM {table.name} WHERE " + " AND ".join(f"{column} IS ?" for column in table.key), key)
        for item in sorted((item for item in rows if item["values"] is not None), key=lambda item: rank[item["table"]]):
            table = self.tables[item["table"]]
            values = {column: self.local(table.refs[column], value) if column in table.refs
                      else float(value) if table.types[column] == "REAL" and value is not None else value
                      for column, value in item["values"].items()}
            columns = table.columns
            if table.rowid:
                local_id = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (table.name, item["key"]))
                if local_id is None:
                    cursor = self.db.execute(f"INSERT INTO {table.name}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                             tuple(values[column] for column in columns))
                    self.bind(table.name, item["key"], cursor.lastrowid)
                else:
                    self.db.execute(f"UPDATE {table.name} SET {','.join(column + '=?' for column in columns)} WHERE id=?",
                                    (*[values[column] for column in columns], local_id))
            else:
                key = dict(zip(table.key, self._local_key(table, item["key"])))
                if any(values[column] != value for column, value in key.items()):
                    raise JournalError("Row key and values disagree")
                updates = [column for column in columns if column not in table.key] or table.key[:1]
                self.db.execute(f"INSERT INTO {table.name}({','.join(columns)}) VALUES({','.join('?' for _ in columns)}) "
                                f"ON CONFLICT({','.join(table.key)}) DO UPDATE SET "
                                + ",".join(f"{column}=excluded.{column}" for column in updates),
                                tuple(values[column] for column in columns))

    def read(self, item):
        """The stored values of one effect row, encoded as an effect would carry them."""
        table = self.tables[item["table"]]
        if table.rowid:
            local_id = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (table.name, item["key"]))
            row = self.db.one(f"SELECT * FROM {table.name} WHERE id=?", (local_id,)) if local_id is not None else None
        else:
            row = self.db.one(f"SELECT * FROM {table.name} WHERE " + " AND ".join(f"{column} IS ?" for column in table.key),
                              self._local_key(table, item["key"]))
        return None if row is None else self.encode(table, row)

    def _local_key(self, table, key):
        return tuple(self.local(table.refs[column], value) if column in table.refs else value
                     for column, value in zip(table.key, key))

    # -- fingerprint ------------------------------------------------------------
    def row_hash(self, name, identity, values):
        # Wall-clock metadata is copied exactly in effects, but not fingerprinted.
        values = {column: value for column, value in values.items() if column not in WALL_CLOCK}
        return hashlib.sha256(canonical(dict(table=name, key=identity, values=values))).hexdigest()

    def remember(self, rows):
        for item in rows:
            slot = item["table"] + ":" + canonical(item["key"]).decode()
            if item["values"] is None:
                self.db.execute("DELETE FROM journal_fp WHERE uuid=?", (slot,))
            else:
                self.db.execute("INSERT OR REPLACE INTO journal_fp VALUES(?,?)",
                                (slot, self.row_hash(item["table"], item["key"], item["values"])))

    def all_rows(self):
        for name in self.order:
            table = self.tables[name]
            for row in self.db.all(f"SELECT * FROM {name} ORDER BY rowid"):
                yield dict(table=name, key=self.identity(table, row), values=self.encode(table, row))

    @staticmethod
    def combine(hashes):
        # A sum of per-row hashes: order-free, so one change updates it in place.
        total = sum(int(value, 16) for value in hashes) % 2**256
        return hashlib.sha256(b"lightning-journal-rows-v1\n" + total.to_bytes(32, "big")).hexdigest()

    def fingerprint(self, *, cached):
        if cached:
            return self.combine(row[0] for row in self.db.all("SELECT hash FROM journal_fp"))
        return self.combine(self.row_hash(item["table"], item["key"], item["values"]) for item in self.all_rows())


def _real(value):
    """A stored float as the shortest text that reads back as the same float."""
    return None if value is None else repr(float(value))
