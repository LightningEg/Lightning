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
from uuid import UUID, uuid5

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine, validate_posting
from lightning.core.money import from_e6

from .codec import JournalError, canonical, digest, fields, number, uuid
from .store import JournalStore, SCHEMA

HEADER = "ref type date description counterparty status source notes created_at updated_at counterparty_id".split()
LINE = "line_no date account_id asset_id quantity_e6 unit_price_e6 amount_e6 fx_rate_e6 amount_base_e6 effect category_id memo cleared owner_id".split()
PARTY = "name normalized_name default_category_id active created_at updated_at".split()
REFS = {"account_id": "accounts", "asset_id": "financial_assets", "category_id": "categories",
        "owner_id": "counterparties", "counterparty_id": "counterparties", "default_category_id": "categories"}


def validate_domain(value):
    if type(value) is dict and type(value.get('schema')) is int and value['schema'] == 2:
        from .domain import validate_effect
        return validate_effect(value)
    fields(value, ("schema", "transactions", "counterparties"))
    if type(value["schema"]) is not int or value["schema"] != 1:
        raise JournalError("Unsupported transaction effect schema")
    if type(value["transactions"]) is not list or not 1 <= len(value["transactions"]) <= 4:
        raise JournalError("Invalid transaction effects")
    if type(value["counterparties"]) is not list or len(value["counterparties"]) > 8:
        raise JournalError("Invalid counterparty effects")
    seen = set()
    for transaction in value["transactions"]:
        fields(transaction, ("uuid", "header", "lines"))
        uuid(transaction["uuid"])
        if transaction["uuid"] in seen:
            raise JournalError("Duplicate transaction effect")
        seen.add(transaction["uuid"])
        fields(transaction["header"], HEADER)
        if any(type(transaction["header"][key]) is not str for key in HEADER if key not in REFS):
            raise JournalError("Transaction header fields must be text")
        if type(transaction["lines"]) is not list or not 1 <= len(transaction["lines"]) <= 32:
            raise JournalError("Invalid posting count")
        if transaction["header"]["type"] not in ("OPN", "IN", "OUT", "TRF"):
            raise JournalError("Unsupported transaction type")
        if transaction["header"]["status"] not in ("POSTED", "VOID"):
            raise JournalError("Invalid transaction status")
        for index, line in enumerate(transaction["lines"], 1):
            fields(line, LINE)
            if line["line_no"] != index:
                raise JournalError("Noncontiguous postings")
            for field in ("quantity_e6", "unit_price_e6", "amount_e6", "fx_rate_e6", "amount_base_e6", "cleared"):
                if type(line[field]) is not int:
                    raise JournalError("Posting values must be exact integers")
            if any(type(line[key]) is not str for key in ("date", "effect", "memo")):
                raise JournalError("Posting labels must be text")
            if line["cleared"] not in (0, 1):
                raise JournalError("Invalid cleared flag")
            for field in REFS.keys() & line.keys():
                if line[field] is not None:
                    uuid(line[field])
        if transaction["header"]["counterparty_id"] is not None:
            uuid(transaction["header"]["counterparty_id"])
    for party in value["counterparties"]:
        fields(party, ("uuid", "values"))
        uuid(party["uuid"])
        fields(party["values"], PARTY)
        if party["values"]["default_category_id"] is not None:
            uuid(party["values"]["default_category_id"])


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
    if role not in ("home", "replica"):
        raise JournalError("Invalid journal role")
    with db.transaction():
        for statement in SCHEMA:
            db.execute(statement)
        config = dict(version=2, profile=profile, generation=generation, device=device,
                      incarnation=incarnation, home_key=home_key, origin_key=origin_key, role=role)
        db.execute("INSERT INTO journal_meta VALUES(1,?,1)", (canonical(config).decode(),))
        db.execute("CREATE TABLE journal_ids(entity TEXT,uuid TEXT,local_id INTEGER,PRIMARY KEY(entity,uuid),UNIQUE(entity,local_id))")
    return attach(container)


def attach(container):
    store = JournalStore(container.db)
    store.db.conn.execute("PRAGMA synchronous=FULL")
    if store.db.has_table('journal_domain_contract'):
        from .full import FullAdapter
        store.adapter = FullAdapter(container, store)
    else:
        store.adapter = CashAdapter(container, store)
    return store


def inspect_adapter(db, config):
    """Inspect a checkpoint without installing guards or changing its contents."""
    from types import SimpleNamespace
    cls = CashAdapter
    if db.has_table('journal_domain_contract'):
        from .full import FullAdapter
        from .domain import DomainGraph
        if db.scalar('SELECT schema FROM journal_domain_contract WHERE id=1') != 2:
            raise JournalError('Unsupported financial domain contract')
        cls = FullAdapter
    adapter = cls.__new__(cls)
    adapter.db, adapter.store = db, SimpleNamespace(config=config, resolve=lambda value: value)
    if cls is not CashAdapter:
        adapter.graph = DomainGraph(db, config['profile'])
    return adapter


class CashAdapter:
    def __init__(self, container, store):
        self.c, self.store, self.db = container, store, container.db
        self.namespace = UUID(store.config["profile"])
        self.allowed = False
        self.denied = None
        self.c.db.undo = None  # Journal undo is a new proposal; legacy row restoration is disabled.
        for row in self.db.all("SELECT name FROM sqlite_temp_master WHERE type='trigger' AND name LIKE 'undo_%'"):
            self.db.execute('DROP TRIGGER "' + row[0].replace('"', '""') + '"')
        with self.db.transaction():
            for entity in ("accounts", "financial_assets", "categories", "counterparties", "transactions"):
                for row in self.db.all(f"SELECT * FROM {entity}"):
                    self.uid(entity, row["id"])
        self.db.conn.set_authorizer(self._authorize)

    def _authorize(self, action, table, column, database, trigger):
        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            if table.startswith("journal_"):
                return sqlite3.SQLITE_OK
            if self.allowed and (table in {"transactions", "ledger_entries", "counterparties", "audit_log", "reserve_transaction_links"} or table.startswith("transactions_fts")):
                return sqlite3.SQLITE_OK
            self.denied = table
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    @contextmanager
    def writing(self):
        self.denied = None
        self.allowed = True
        self.db.conn.set_authorizer(self._authorize)
        try:
            yield
        except self.db.driver.DatabaseError as error:
            if self.denied:
                raise ValidationError("This action writes an area not covered by the experimental journal") from error
            raise
        finally:
            self.allowed = False
            # Resetting the authorizer invalidates prepared statements, so a cached
            # statement authorized inside confirmation cannot bypass the guard later.
            self.db.conn.set_authorizer(self._authorize)

    def uid(self, entity, local_id):
        if local_id is None:
            return None
        known = self.db.scalar("SELECT uuid FROM journal_ids WHERE entity=? AND local_id=?", (entity, local_id))
        if known:
            return known
        row = self.db.one(f"SELECT * FROM {entity} WHERE id=?", (local_id,))
        if row is None:
            raise ValidationError("A referenced record is missing")
        natural = row["ref"] if entity == "transactions" else row["normalized_name"] if entity == "counterparties" else row["code"]
        value = str(uuid5(self.namespace, f"{entity}:{natural}"))
        self.bind(entity, value, local_id)
        return value

    def bind(self, entity, value, local_id):
        self.db.execute("INSERT INTO journal_ids VALUES(?,?,?)", (entity, value, local_id))

    def local(self, entity, value):
        if value is None:
            return None
        uuid(value)
        if entity == "transactions":
            value = self.store.resolve(value)
        result = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (entity, value))
        if result is None:
            raise ValidationError("A referenced record is not in the confirmed copy")
        return result

    def _encode(self, row, columns):
        return {key: self.uid(REFS[key], row[key]) if key in REFS else row[key] for key in columns}

    def transaction(self, txn_id):
        row = self.db.one("SELECT * FROM transactions WHERE id=?", (txn_id,))
        return dict(uuid=self.uid("transactions", txn_id), header=self._encode(row, HEADER),
                    lines=[self._encode(line, LINE) for line in self.db.all(
                        "SELECT * FROM ledger_entries WHERE transaction_id=? ORDER BY line_no", (txn_id,))])

    def fingerprint(self):
        state = hashlib.sha256(b"lightning-cash-journal-v1\n")
        transactions = [self.transaction(row[0]) for row in self.db.all("SELECT id FROM transactions")]
        for transaction in sorted(transactions, key=lambda item: item["uuid"]):
            # Wall-clock metadata is retained in exact effects, but not in the ledger fingerprint.
            transaction["header"].pop("created_at")
            transaction["header"].pop("updated_at")
            state.update(canonical(transaction) + b"\n")
        return state.hexdigest()

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
        for row in self.db.all("SELECT record_id FROM journal_records WHERE deleted=0"):
            existing = self.store.record(row[0])
            same_source = bool(groups.get("source") and groups["source"] == existing["groups"].get("source"))
            old_money, new_money = existing["groups"].get("money", {}), groups.get("money", {})
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
        before = {row[0]: self.transaction(row[0]) for row in self.db.all("SELECT id FROM transactions")}
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
            changed = [self.transaction(row[0]) for row in self.db.all("SELECT id FROM transactions")
                       if row[0] not in before or self.transaction(row[0]) != before[row[0]]]
            parties = [{"uuid": self.uid("counterparties", row["id"]), "values": self._encode(row, PARTY)}
                       for row in self.db.all("SELECT * FROM counterparties")
                       if self.uid("counterparties", row["id"]) in {t["header"]["counterparty_id"] for t in changed}]
        result = dict(schema=1, transactions=changed, counterparties=parties)
        try:
            validate_domain(result)
        except JournalError as error:
            raise ValidationError("This action exceeds the experimental transaction coverage") from error
        return result

    def apply(self, domain):
        """Typed exact replay on replicas, with no normal save/rule/automation call."""
        validate_domain(domain)
        with self.writing():
            for party in domain["counterparties"]:
                self._upsert("counterparties", party["uuid"], party["values"], PARTY)
            for transaction in domain["transactions"]:
                txn_id = self._upsert("transactions", transaction["uuid"], transaction["header"], HEADER)
                self.db.execute("DELETE FROM ledger_entries WHERE transaction_id=?", (txn_id,))
                postings = []
                for line in transaction["lines"]:
                    values = {key: self.local(REFS[key], value) if key in REFS else value for key, value in line.items()}
                    postings.append(PostingLine(account_id=values["account_id"], asset_id=values["asset_id"],
                        quantity=from_e6(values["quantity_e6"]), unit_price=from_e6(values["unit_price_e6"]),
                        amount=from_e6(values["amount_e6"]), fx_rate=from_e6(values["fx_rate_e6"]),
                        amount_base=from_e6(values["amount_base_e6"]), effect=Effect(values["effect"]),
                        category_id=values["category_id"], memo=values["memo"], is_cash=True, owner_id=values["owner_id"]))
                    self.db.execute(f"INSERT INTO ledger_entries(transaction_id,{','.join(LINE)}) VALUES({','.join('?' for _ in range(len(LINE)+1))})",
                                    (txn_id, *(values[column] for column in LINE)))
                validate_posting(postings)

    def _upsert(self, entity, value, row, columns):
        values = {key: self.local(REFS[key], item) if key in REFS else item for key, item in row.items()}
        local_id = self.db.scalar("SELECT local_id FROM journal_ids WHERE entity=? AND uuid=?", (entity, value))
        if local_id is None:
            cursor = self.db.execute(f"INSERT INTO {entity}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                                     tuple(values[column] for column in columns))
            local_id = cursor.lastrowid
            self.bind(entity, value, local_id)
        else:
            self.db.execute(f"UPDATE {entity} SET {','.join(column+'=?' for column in columns)} WHERE id=?",
                            (*[values[column] for column in columns], local_id))
        return local_id
