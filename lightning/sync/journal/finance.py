"""Experimental cash-register adapter using the normal Python financial services.

Only explicitly created dummy journal profiles may use this adapter. Other money
areas have no endpoints and the connection denies writes outside confirmation.
Wire effects have fixed typed columns and UUID references, never SQL/local IDs.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from datetime import date

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine, validate_posting
from lightning.core.money import from_e6

from .codec import JournalError, canonical, digest, fields, hash_value, number, uuid
from . import commands
from .effects import CHUNK_BYTES, GUARDED, MAX_CHUNKS, MAX_ROWS, SCHEMA, Replicator
from .store import JournalStore, SCHEMA as STORE_SCHEMA



def validate_domain(value):
    """Shape only; `Replicator.validate` checks every row against this device's schema."""
    if type(value) is dict and "chunks" in value:
        fields(value, ("schema", "chunks"))
        if type(value["chunks"]) is not list or not 1 <= len(value["chunks"]) <= MAX_CHUNKS:
            raise JournalError("Invalid chunked effect")
        for item in value["chunks"]:
            hash_value(item)
        if value["schema"] != SCHEMA:
            raise JournalError("Unsupported effect schema; update this device")
        return
    fields(value, ("schema", "rows"))
    if type(value["schema"]) is not int or value["schema"] != SCHEMA:
        raise JournalError("Unsupported effect schema; update this device")
    if type(value["rows"]) is not list or not 1 <= len(value["rows"]) <= MAX_ROWS:
        raise JournalError("Invalid row effects")
    for row in value["rows"]:
        fields(row, ("table", "key", "values"))


def initialize(container, *, profile, generation, device, incarnation, home_key, origin_key, role,
               dummy_profile=False):
    """Explicit opt-in; never converts a user's existing profile implicitly."""
    db = container.db
    if not dummy_profile or not db.encrypted or db.has_table("journal_meta"):
        raise JournalError("Create a fresh encrypted dummy journal profile")
    if db.scalar("SELECT COUNT(*) FROM transactions WHERE type!='OPN'"):
        raise JournalError("Only a fresh baseline with opening balances can enroll")
    if db.scalar("SELECT COUNT(*) FROM ledger_entries WHERE ABS(quantity_e6)>=9007199254740992 OR ABS(amount_base_e6)>=9007199254740992"):
        raise JournalError("This baseline exceeds the experimental wire amount limit")
    for value in (profile, generation, device, incarnation):
        uuid(value)
    if role != "home":
        raise JournalError("A replica starts from the home's verified checkpoint")
    with db.transaction():
        for statement in STORE_SCHEMA:
            db.execute(statement)
        config = dict(version=2, profile=profile, generation=generation, device=device,
                      incarnation=incarnation, home_key=home_key, origin_key=origin_key, role=role)
        db.execute("INSERT INTO journal_meta VALUES(1,?,1)", (canonical(config).decode(),))
        db.execute("CREATE TABLE journal_ids(entity TEXT,uuid TEXT,local_id INTEGER,PRIMARY KEY(entity,uuid),UNIQUE(entity,local_id))")
    return attach(container)


def attach(container):
    store = JournalStore(container.db)
    store.db.conn.execute("PRAGMA synchronous=FULL")
    store.adapter = CashAdapter(container, store)
    return store


class ChunksMissing(JournalError):
    """A chunked commit waits for these chunk hashes; nothing was applied."""
    def __init__(self, missing):
        super().__init__("Effect chunks are still arriving")
        self.missing = missing


class CashAdapter:
    def __init__(self, container, store):
        self.c, self.store, self.db = container, store, container.db
        self.allowed = False
        self.denied = None
        self.captured = []
        # The home's own screens get back what the service returned, or its refusal.
        self.results, self.errors = {}, {}
        self.c.db.undo = None  # Journal undo is a new proposal; legacy row restoration is disabled.
        self.rows = Replicator(self.db, store.config["profile"], resolve=store.resolve)
        self.db.conn.set_authorizer(None)  # Fixed local DDL below; protection returns at the end.
        for row in self.db.all("SELECT name FROM sqlite_temp_master WHERE type='trigger' AND name LIKE 'undo_%'"):
            self.db.execute('DROP TRIGGER "' + row[0].replace('"', '""') + '"')
        # Every write records the rows it touched, so a confirmation publishes and
        # fingerprints only those, never the whole ledger.
        self.rows.install()
        with self.db.transaction():
            self.db.execute("CREATE TABLE IF NOT EXISTS journal_fp(uuid TEXT PRIMARY KEY,hash TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS journal_chunks(hash TEXT PRIMARY KEY,data BLOB NOT NULL)")
            rows = list(self.rows.all_rows())  # Binds every baseline row's identity.
            if (self.db.scalar("SELECT COUNT(*) FROM journal_fp") != len(rows)
                    or self.db.scalar("SELECT 1 FROM journal_fp WHERE uuid NOT LIKE '%:%' LIMIT 1")):
                self.db.execute("DELETE FROM journal_fp")
                self.rows.remember(rows)
        self.cached = True
        self.db.conn.set_authorizer(self._authorize)

    def _authorize(self, action, table, column, database, trigger):
        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            if table.startswith("journal_"):
                return sqlite3.SQLITE_OK
            if self.allowed and (table in self.rows.tables or table in GUARDED or table == "audit_log" or table.startswith("transactions_fts")):
                return sqlite3.SQLITE_OK
            self.denied = table
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    @contextmanager
    def writing(self):
        self.denied = None
        self.allowed = True
        self.captured = []
        self.db.conn.set_authorizer(self._authorize)
        try:
            self.rows.reset()
            yield
            self.captured = self.rows.capture()
            self.rows.remember(self.captured)
            self.rows.reset()
        except self.db.driver.DatabaseError as error:
            if self.denied or "journal: area not covered" in str(error):
                raise ValidationError("This action writes an area not covered by the experimental journal") from error
            raise
        finally:
            self.allowed = False
            # Resetting the authorizer invalidates prepared statements, so a cached
            # statement authorized inside confirmation cannot bypass the guard later.
            self.db.conn.set_authorizer(self._authorize)

    def uid(self, entity, local_id):
        return self.rows.uid(entity, local_id)

    def bind(self, entity, value, local_id):
        self.rows.bind(entity, value, local_id)

    def local(self, entity, value):
        return self.rows.local(entity, value)

    def fingerprint(self, *, full=False):
        """Cached per-row hashes on an attached adapter; `full` (and any unattached
        checkpoint reader) recomputes every synchronized row from the ledger."""
        if getattr(self, "cached", False):
            return self.rows.fingerprint(cached=not full)
        return Replicator(self.db, self.store.config["profile"]).fingerprint(cached=False)

    def verify(self):
        """The whole copy against its cached row hashes, after a catch-up (proposal §4)."""
        if self.fingerprint(full=True) != self.fingerprint():
            raise JournalError("Ledger fingerprint mismatch; verified snapshot required")

    def supports(self, kind):
        return kind.startswith("transaction.") or kind in commands.KINDS

    def check(self, kind, groups, *, complete=False):
        if kind.startswith("command."):
            commands.validate(kind, groups)
        else:
            self.validate_groups(groups, complete=complete)

    def validate_groups(self, groups, *, complete=False):
        if set(groups) - {"money", "category", "details", "source"}:
            raise ValidationError("Unsupported transaction fields")
        if complete and not {"money", "category", "details"} <= groups.keys():
            raise ValidationError("A transaction needs money, category and details")
        if "money" in groups:
            money = groups["money"]
            fields(money, ("account", "other_account", "date", "amount"))
            uuid(money["account"])
            if money["other_account"] is not None:
                uuid(money["other_account"])
            if type(money["amount"]) is not str:
                raise ValidationError("Amounts must be decimal text")
            try:
                if type(money["date"]) is not str or date.fromisoformat(money["date"]).isoformat() != money["date"]:
                    raise ValueError
            except ValueError as error:
                raise ValidationError("Enter a valid date") from error
            try:
                amount = Decimal(money["amount"])
                if not amount.is_finite() or amount == 0 or abs(amount) > Decimal("9000000000") or amount.as_tuple().exponent < -2:
                    raise ValueError
            except (ValueError, ArithmeticError) as error:
                raise ValidationError("Enter a nonzero amount up to 9 billion with at most two decimal places") from error
        if "category" in groups:
            fields(groups["category"], ("category", "splits"))
            if groups["category"]["category"] is not None:
                uuid(groups["category"]["category"])
            splits = groups["category"]["splits"]
            if type(splits) is not list or len(splits) > 16:
                raise ValidationError("Use at most sixteen split lines")
            for split in splits:
                fields(split, ("category", "amount"))
                uuid(split["category"])
        if "details" in groups:
            fields(groups["details"], ("counterparty", "notes", "description"))
            if any(type(value) is not str or len(value) > 1000 for value in groups["details"].values()):
                raise ValidationError("Transaction text is too long")
        if "source" in groups:
            fields(groups["source"], ("namespace", "id"))
            if any(type(value) is not str or not 1 <= len(value) <= 128 for value in groups["source"].values()):
                raise ValidationError("Invalid capture source identity")

    def matches(self, proposal):
        if not proposal["kind"].endswith(".add"):
            return []
        groups = proposal["groups"]
        source = groups.get("source")
        if source:
            known = self.db.one("SELECT record,payload_hash FROM journal_sources WHERE namespace=? AND source_id=?", (source["namespace"], source["id"]))
            if known:
                existing = self.store.record(known["record"])
                collision = known["payload_hash"] != self.source_token(groups["money"])
                return [dict(record=existing["record"], proven=not collision, collision=collision, tokens=existing["tokens"])]
        result = []
        new_money = groups.get("money", {})
        # A look-alike is only suspicious when a capture is involved; two manual
        # entries with the same amount on one day are usually two real payments.
        for row in self.db.all("""SELECT record_id FROM journal_records WHERE deleted=0
                AND json_extract(groups_json,'$.money.date') IS ? AND json_extract(groups_json,'$.money.account') IS ?
                AND (? OR json_extract(groups_json,'$.source') IS NOT NULL)""",
                (new_money.get("date"), new_money.get("account"), bool(source))):
            existing = self.store.record(row[0])
            same_source = bool(groups.get("source") and groups["source"] == existing["groups"].get("source"))
            old_money = existing["groups"].get("money", {})
            same_money = all(old_money.get(key) == new_money.get(key) for key in ("account", "other_account", "date"))
            try:
                same_money = same_money and Decimal(old_money["amount"]) == Decimal(new_money["amount"])
            except (KeyError, ArithmeticError, TypeError):
                same_money = False
            if not same_money and not same_source:
                continue
            collision = same_source and not same_money
            result.append(dict(record=row[0], proven=same_source and not collision, collision=collision, tokens=existing["tokens"]))
        return sorted(result, key=lambda match: (not match["proven"], match["record"]))[:4]

    def source_token(self, money):
        return digest(money | {"amount": format(Decimal(money["amount"]), ".2f")})

    def confirm(self, proposal, effect):
        if proposal["kind"].startswith("command."):
            commands.validate(proposal["kind"], proposal["groups"])
            with self.writing():
                result = commands.run(self, proposal["kind"], proposal["record"], proposal["groups"])
            effect_rows = self._result() if self.captured else None
            self._keep(self.results, proposal, result)
            return effect_rows
        if not proposal["kind"].startswith("transaction."):
            raise ValidationError("Only cash transactions are supported here")
        if not effect["deleted"]:
            self.validate_groups(proposal["groups"])
        if any(match["collision"] for match in self.matches(proposal)):
            raise ValidationError("This source identity already describes a different payment")
        if not proposal["kind"].endswith(".add"):
            local_id = self.local("transactions", effect["record"])
            if self.db.scalar("SELECT COUNT(*) FROM reserve_transaction_links WHERE transaction_id=?", (local_id,)):
                raise ValidationError("Linked reserve actions are not enabled in this experiment")
        with self.writing():
            if effect["deleted"]:
                self.c.transactions.void(self.local("transactions", effect["record"]))
            else:
                groups = effect["groups"]
                self.validate_groups(groups, complete=True)
                money, category, details = groups["money"], groups["category"], groups["details"]
                account = self.local("accounts", money["account"])
                other = self.local("accounts", money["other_account"])
                for account_id in (account, other):
                    if account_id is not None:
                        item = self.c.accounts.get(account_id)
                        if item.account_type.value not in {"BANK", "CASH"} or item.currency != self.c.base_currency:
                            raise ValidationError("This experimental profile supports base-currency bank and cash accounts")
                splits = category["splits"]
                selected = self.local("categories", splits[0]["category"] if splits else category["category"])
                if selected is not None and self.c.categories.get(selected).is_system:
                    raise ValidationError("System financial actions are not enabled in this experiment")
                args = dict(account_id=account, date=money["date"], amount=money["amount"],
                            category_id=selected, other_account_id=other,
                            counterparty=details["counterparty"], notes=details["notes"])
                if proposal["kind"].endswith(".add"):
                    txn = self.c.transactions.record_in_account(**args, description=details["description"])
                    self.bind("transactions", effect["record"], txn.id)
                else:
                    current = self.c.transactions.get(self.local("transactions", effect["record"]))
                    kind, _, _ = self.c.transactions._register_kind(money["amount"], selected, other)
                    if kind != current.type:
                        raise ValidationError("Changing a transaction's kind is not enabled in this experiment")
                    txn = self.c.transactions.update_in_account(current.id, **args)
                if splits:
                    self.c.transactions.update_expense_split(txn.id, [(self.local("categories", split["category"]), split["amount"]) for split in splits])
                txn = self.c.transactions.get(txn.id)
                if txn.description != details["description"]:
                    lines = [PostingLine.cash(line.account_id, line.asset_id, line.quantity, line.effect,
                        line.category_id, line.memo, line.fx_rate, line.owner_id) for line in txn.lines]
                    self.c.transactions.repost(txn.id, money["date"], lines, details["description"],
                                               details["counterparty"], details["notes"])
        return self._result()

    def _result(self):
        rows = self.captured
        if not rows:
            raise ValidationError("This action changed nothing")
        if len(rows) <= MAX_ROWS and len(canonical(rows)) <= 40 * 1024:
            return dict(schema=SCHEMA, rows=rows)
        chunks, current, size = [], [], 2
        for row in rows:
            encoded = len(canonical(row)) + 1
            if encoded > CHUNK_BYTES:
                raise ValidationError("One record of this action is too large for the journal")
            if current and size + encoded > CHUNK_BYTES:
                chunks.append(current)
                current, size = [], 2
            current.append(row)
            size += encoded
        chunks.append(current)
        if len(chunks) > MAX_CHUNKS:
            raise ValidationError("This action is too large for one journal entry; split it into smaller parts")
        hashes = []
        for chunk in chunks:
            data = canonical(chunk)
            hashes.append(hashlib.sha256(data).hexdigest())
            self.db.execute("INSERT OR IGNORE INTO journal_chunks VALUES(?,?)", (hashes[-1], data))
        return dict(schema=SCHEMA, chunks=hashes)

    def assemble(self, domain):
        """The rows of a chunked effect, once every chunk is here and verified."""
        if "chunks" not in domain:
            return domain
        missing = [item for item in domain["chunks"]
                   if not self.db.scalar("SELECT 1 FROM journal_chunks WHERE hash=?", (item,))]
        if missing:
            raise ChunksMissing(missing)
        rows = []
        for item in domain["chunks"]:
            data = bytes(self.db.scalar("SELECT data FROM journal_chunks WHERE hash=?", (item,)))
            if hashlib.sha256(data).hexdigest() != item:
                raise JournalError("Damaged effect chunk; verified snapshot required")
            rows.extend(json.loads(data))
        return dict(schema=SCHEMA, rows=rows)

    @staticmethod
    def _keep(store, proposal, value):
        from .codec import origin_id
        store[origin_id(proposal["origin"])] = value
        while len(store) > 32:
            store.pop(next(iter(store)))

    def refused(self, proposal, error):
        self._keep(self.errors, proposal, getattr(error, "message", str(error)))

    def row_token(self, slot):
        """A command's precondition: the record's row and every row it owns (a
        transaction's money is in its ledger lines, not its own row)."""
        own = self.db.scalar("SELECT hash FROM journal_fp WHERE uuid=?", (slot,))
        table, _, key = slot.partition(":")
        if own is None or table not in self.rows.owned:
            return own
        local_id = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (table, json.loads(key)))
        if local_id is None:
            return own
        return digest(dict(row=own, owned=self.rows.record_hashes(table, local_id)))

    def apply(self, domain):
        """Typed exact replay on replicas, with no normal save/rule/automation call."""
        domain = self.assemble(domain)
        with self.writing():
            self.rows.apply(domain, bounded=len(domain["rows"]) <= MAX_ROWS)
            self.rows.reset()  # The effect names every touched row, deletes included; triggers could not name those.
            # Read back what was written: the fingerprint must describe this copy, not the effect.
            for item in domain["rows"]:
                if item["values"] is not None and self.rows.read(item) != item["values"]:
                    raise JournalError("Ledger fingerprint mismatch; verified snapshot required")
            self.rows.remember(domain["rows"])
            if any(row["table"] == "settings" for row in domain["rows"]):
                from .areas.settings import refresh
                refresh(self.c)
            changed = set()
            for row in domain["rows"]:
                if row["table"] == "transactions" and row["values"] is not None:
                    changed.add(self.local("transactions", row["key"]))
                elif row["table"] == "ledger_entries" and row["values"] is not None:
                    changed.add(self.local("transactions", row["values"]["transaction_id"]))
            for txn_id in sorted(changed):
                validate_posting([PostingLine(account_id=line["account_id"], asset_id=line["asset_id"],
                    quantity=from_e6(line["quantity_e6"]), unit_price=from_e6(line["unit_price_e6"]),
                    amount=from_e6(line["amount_e6"]), fx_rate=from_e6(line["fx_rate_e6"]),
                    amount_base=from_e6(line["amount_base_e6"]), effect=Effect(line["effect"]),
                    category_id=line["category_id"], memo=line["memo"], is_cash=bool(line["is_cash"]), owner_id=line["owner_id"])
                    for line in self.db.all("SELECT l.*,a.is_cash FROM ledger_entries l JOIN financial_assets a ON a.id=l.asset_id "
                                            "WHERE l.transaction_id=? ORDER BY l.line_no", (txn_id,))])
