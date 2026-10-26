"""Public API of the transactions module: record, edit, void, find.

Every write goes through ``validate_posting`` (core/ledger.py) before it is saved.
Edits happen in place — the ref never changes — and the audit log keeps before/after.
Search reads transactions, accounts and categories directly, so nothing derived is stored.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json

from lightning.accounts.domain import Account, AccountType
from lightning.accounts.service import AccountService
from lightning.assets.service import AssetService
from lightning.categories.domain import Direction, Movement
from lightning.categories.service import CategoryService
from lightning.counterparties import CounterpartyService
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import LightningError, NotFoundError, ValidationError
from lightning.core.ledger import Effect, PostingLine, split_line_e6, validate_posting
from lightning.core.money import ONE, ZERO, check_places, fmt, from_e6, to_decimal, to_e6
from lightning.core.refs import DOC_LABELS, DocType, format_ref, ref_prefix
from lightning.database.audit import AuditLog
from lightning.database.connection import Database
from lightning.fx import MISSING_DAYS, rate_for

from . import conversion
from .domain import Transaction, TxnFilter, TxnSource, TxnStatus, TxnSummary
from .repository import TransactionRepository
from .tags import normalize as normal_tag, tags_in

EDITABLE_TYPES = {DocType.IN, DocType.OUT, DocType.TRF}


class TransactionService:
    def __init__(
        self,
        db: Database,
        accounts: AccountService,
        assets: AssetService,
        categories: CategoryService,
        audit: AuditLog,
        base_currency: str,
    ):
        self.db = db
        self.repo = TransactionRepository(db)
        self.accounts = accounts
        self.assets = assets
        self.categories = categories
        self.counterparties = CounterpartyService(db)
        self.audit = audit
        self.base_currency = base_currency

    def merge_preview(self, keep_id: int, drop_id: int):
        """Describe a duplicate merge; the confirmation fingerprint must be submitted to merge."""
        from .merge import MergeService
        return MergeService(self).preview(keep_id, drop_id)

    def merge(self, keep_id: int, drop_id: int, fingerprint: str):
        """Merge a selected duplicate pair after a fresh preview was confirmed."""
        from .merge import MergeService
        return MergeService(self).merge(keep_id, drop_id, fingerprint)

    # ======================================================================
    # Recording
    # ======================================================================
    def record_inflow(self, date: str, account_id: int, amount, category_id: int, description: str = "",
                      counterparty: str = "", notes: str = "", source: TxnSource = TxnSource.MANUAL,
                      allow_system_category: bool = False, owner_id: int | None = None) -> Transaction:
        """Money in: salary, interest, a gift. Money back in an expense category is a refund."""
        category = self.categories.get(category_id) if category_id is not None else None
        if category is not None and category.movement == Movement.OUTFLOW and not category.is_system:
            # The register and import already record it this way; the account form now does too.
            return self.record_refund(date, account_id, amount, category_id, description=description,
                                      counterparty=counterparty, notes=notes, source=source, owner_id=owner_id)
        day, lines = self._money_lines(Movement.INFLOW, date, account_id, amount, category_id, allow_system_category)
        lines = [replace(line, owner_id=owner_id) for line in lines]
        return self._create(DocType.IN, day, lines, description, counterparty, notes, source)

    def record_outflow(self, date: str, account_id: int, amount, category_id: int, description: str = "",
                       counterparty: str = "", notes: str = "", source: TxnSource = TxnSource.MANUAL,
                       allow_system_category: bool = False, owner_id: int | None = None) -> Transaction:
        """Money out: groceries, fees, tax. On a credit card this increases what you owe."""
        day, lines = self._money_lines(Movement.OUTFLOW, date, account_id, amount, category_id, allow_system_category)
        lines = [replace(line, owner_id=owner_id) for line in lines]
        return self._create(DocType.OUT, day, lines, description, counterparty, notes, source)

    def record_refund(self, date: str, account_id: int, amount, category_id: int, description: str = "",
                      counterparty: str = "", notes: str = "", source: TxnSource = TxnSource.MANUAL,
                      owner_id: int | None = None) -> Transaction:
        """Money returned for a purchase; record it against the original expense category."""
        account = self.accounts.require_usable(account_id)
        self._refuse_physical_asset(account)
        day = self._check_date(date)
        asset = self.assets.cash_asset(account.currency)
        value = self._positive_amount(amount, asset.quantity_decimals)
        category_obj = self.categories.get(category_id)
        category = self.categories.require(category_id, Movement.OUTFLOW, allow_system=category_obj.is_system)
        if category.movement != Movement.OUTFLOW:
            raise ValidationError("Choose an expense category for a refund.", "category")
        if category.code == "EXP.SYSTEM.CUSTODY":
            raise ValidationError("Money held for others cannot be recorded as an expense refund.", "category")
        line = PostingLine.cash(account.id, asset.id, value, Effect.OUTFLOW, category.id,
                                memo="Refund", fx_rate=self._fx(account, day), owner_id=owner_id)
        return self._create(DocType.IN, day, [line], description or "Refund", counterparty, notes, source)

    def record_transfer(self, date: str, from_account_id: int, to_account_id: int, amount,
                        description: str = "", notes: str = "",
                        source: TxnSource = TxnSource.MANUAL, owner_id: int | None = None,
                        allow_legacy_deposit_cash: bool = False) -> Transaction:
        """Money moving between your own accounts. Never income, expense or revaluation."""
        source_account = self.accounts.get(from_account_id)
        destination_account = self.accounts.get(to_account_id)
        if (destination_account.account_type == AccountType.DEPOSIT or
                (source_account.account_type == AccountType.DEPOSIT and not allow_legacy_deposit_cash)):
            raise ValidationError("CD portfolios cannot receive cash. Use the CD purchase action.")
        if allow_legacy_deposit_cash and source_account.account_type != AccountType.DEPOSIT:
            raise ValidationError("Legacy cash can only be moved out of a previous deposit account.")
        day, lines = self._transfer_lines(date, from_account_id, to_account_id, amount,
                                          allow_legacy_deposit_cash)
        lines = [replace(line, owner_id=owner_id) for line in lines]
        return self._create(DocType.TRF, day, lines, description, "", notes, source)

    def change_cash_ownership(self, date: str, account_id: int, amount, from_owner_id: int | None,
                              to_owner_id: int | None, notes: str = "", txn_id: int | None = None) -> Transaction:
        """Reassign cash ownership inside one account without changing its gross balance."""
        return self._ownership_posting(date, account_id, amount, from_owner_id, to_owner_id,
                                       notes=notes, txn_id=txn_id)

    def record_expense_paid_by_person(self, date: str, account_id: int, amount, owner_id: int,
                                      category_id: int, notes: str = "",
                                      txn_id: int | None = None) -> Transaction:
        """Record an expense paid externally and credit the same value to that person's custody."""
        person = self._active_owner(owner_id)
        account = self.accounts.require_usable(account_id)
        if account.account_type not in {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE}:
            raise ValidationError("Choose a cash, bank, or brokerage account.", "account_id")
        day = self._check_date(date)
        cash = self.assets.cash_asset(account.currency)
        value = self._positive_amount(amount, cash.quantity_decimals)
        category = self.categories.require(category_id, Movement.OUTFLOW)
        if category.code == "EXP.SYSTEM.CUSTODY":
            raise ValidationError("Choose the expense category Dad paid for.", "category")
        custody = self.categories.get_by_code("EXP.SYSTEM.CUSTODY")
        lines = [
            PostingLine.cash(account.id, cash.id, -value, Effect.OUTFLOW, category.id,
                             memo="Paid externally", fx_rate=self._fx(account, day)),
            PostingLine.cash(account.id, cash.id, value, Effect.INFLOW, custody.id,
                             memo=f"Held for {person['name']}", fx_rate=self._fx(account, day), owner_id=person["id"]),
        ]
        return self._save_ownership_document(day, account, lines, value,
                                             f"Ownership: expense paid by {person['name']}",
                                             person["name"], notes, txn_id)

    def _ownership_posting(self, date, account_id, amount, from_owner_id, to_owner_id,
                           notes="", txn_id=None):
        if from_owner_id == to_owner_id:
            raise ValidationError("Choose two different owners.", "to_owner_id")
        if from_owner_id is not None and to_owner_id is not None:
            raise ValidationError("A change must move between your money and one other person.", "to_owner_id")
        from_owner = self._active_owner(from_owner_id) if from_owner_id is not None else None
        to_owner = self._active_owner(to_owner_id) if to_owner_id is not None else None
        account = self.accounts.require_usable(account_id)
        if account.account_type not in {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE}:
            raise ValidationError("Choose a cash, bank, or brokerage account.", "account_id")
        day = self._check_date(date)
        cash = self.assets.cash_asset(account.currency)
        value = self._positive_amount(amount, cash.quantity_decimals)
        lines = [
            PostingLine.cash(account.id, cash.id, -value, Effect.INTERNAL, fx_rate=self._fx(account, day),
                             memo=f"Ownership from {from_owner['name'] if from_owner else 'you'}",
                             owner_id=from_owner["id"] if from_owner else None),
            PostingLine.cash(account.id, cash.id, value, Effect.INTERNAL, fx_rate=self._fx(account, day),
                             memo=f"Ownership to {to_owner['name'] if to_owner else 'you'}",
                             owner_id=to_owner["id"] if to_owner else None),
        ]
        description = (f"Ownership: {from_owner['name'] if from_owner else 'You'} → "
                       f"{to_owner['name'] if to_owner else 'You'}")
        return self._save_ownership_document(day, account, lines, value, description, "", notes, txn_id)

    def _save_ownership_document(self, day, account, lines, amount, description, counterparty,
                                 notes, txn_id=None):
        validate_posting(lines)
        for line in lines:
            self.accounts.require_usable(line.account_id)
        if txn_id is None:
            return self._create(DocType.ADJ, day, lines, description, counterparty, notes,
                                TxnSource.MANUAL, validate_all_cash=True)
        current = self.get(txn_id)
        if current.type != DocType.ADJ or not current.description.startswith("Ownership:") or current.is_void:
            raise ValidationError("This is not an active ownership entry.")
        return self._update(current, day, lines, description, counterparty, notes, validate_all_cash=True)

    def _active_owner(self, owner_id):
        if owner_id is None:
            return None
        person = self.db.one("SELECT id,name,active FROM counterparties WHERE id=?", (owner_id,))
        if not person or not person["active"]:
            raise ValidationError("Choose an active saved person.", "owner_id")
        return dict(person)

    def record_in_account(self, account_id: int, date: str, amount: object, category_id: int | None = None,
                          other_account_id: int | None = None, counterparty: str = "", notes: str = "",
                          description: str = "", owner_id: int | None = None) -> Transaction:
        """One register row -> the right transaction.

        ``amount`` is signed from this account's point of view: positive = money in, negative = money out.
        Give a category (money in / money out) — or another of your accounts, which makes it a transfer.
        Counterparty is the person or business; choosing an owned account makes a transfer.
        """
        if self.accounts.get(account_id).account_type.value == "DEPOSIT":
            raise ValidationError("CD portfolios cannot hold cash. Use the CD purchase or redemption action.")
        kind, value, category_id = self._register_kind(amount, category_id, other_account_id)
        if kind == DocType.TRF:
            src, dst = (account_id, other_account_id) if value < 0 else (other_account_id, account_id)
            return self.record_transfer(date, src, dst, abs(value), description=description, notes=notes,
                                        owner_id=owner_id)
        if kind == DocType.OUT:
            return self.record_outflow(date, account_id, -value, category_id, description=description,
                                       counterparty=counterparty, notes=notes, owner_id=owner_id)
        if self.categories.get(category_id).movement == Movement.OUTFLOW:
            return self.record_refund(date, account_id, value, category_id, description=description,
                                      counterparty=counterparty, notes=notes, owner_id=owner_id)
        return self.record_inflow(date, account_id, value, category_id, description=description,
                                  counterparty=counterparty, notes=notes, owner_id=owner_id)

    def update_in_account(self, txn_id: int, account_id: int, date: str, amount: object,
                          category_id: int | None = None, other_account_id: int | None = None,
                          counterparty: str = "", notes: str = "", owner_id: int | None = None) -> Transaction:
        """Edit a register row in place, seen from ``account_id`` (the register it was edited in).

        If the kind changes (e.g. a transfer becomes money out) the old one is voided and a new one recorded,
        because a ref's prefix (TRF/OUT/IN) must always tell the truth.
        """
        current = self.get(txn_id)
        if current.is_void:
            raise ValidationError("Restore this transaction before editing it.")
        if current.type == DocType.OPN:
            raise ValidationError("Change an opening balance from the account's edit page.")
        if current.type not in EDITABLE_TYPES:
            raise ValidationError(f"{current.type_label} transactions are edited from Investments.")
        cash_lines = [line for line in current.lines if self.assets.get_asset(line.asset_id).is_cash]
        if current.type == DocType.OUT and len(cash_lines) > 1 and category_id is None:
            total = sum((line.quantity for line in cash_lines), ZERO)
            if account_id != cash_lines[0].account_id or to_decimal(amount, "amount") != total:
                raise ValidationError("Change split amounts on the transaction details page; this edit only changes its notes or date.")
            return self.update_metadata(current.id, date, counterparty, notes)
        kind, value, category_id = self._register_kind(amount, category_id, other_account_id)
        if kind != current.type and category_id is not None:
            category = self.categories.get(category_id)
            movement = Movement.INFLOW if kind == DocType.IN else Movement.OUTFLOW
            if category.is_system and category.movement != movement:
                raise ValidationError("This system category cannot be changed to the opposite money direction. Choose a regular category.", "category")
        with self.db.transaction():
            if kind != current.type:
                self.void(current.id, f"Replaced when edited ({current.type_label} → {DOC_LABELS[kind]})")
                return self.record_in_account(account_id, date, value, category_id, other_account_id,
                                              counterparty, notes, current.description, owner_id)
            if kind == DocType.TRF:
                src, dst = (account_id, other_account_id) if value < 0 else (other_account_id, account_id)
                return self.update_transfer(current.id, date, src, dst, abs(value), current.description, notes,
                                            owner_id=owner_id)
            if kind == DocType.IN and self.categories.get(category_id).movement == Movement.OUTFLOW:
                return self.update_refund(current.id, date, account_id, abs(value), category_id,
                                          current.description, counterparty, notes, owner_id=owner_id)
            return self.update_money(current.id, date, account_id, abs(value), category_id,
                                     current.description, counterparty, notes, owner_id=owner_id)

    def set_transaction_owner(self, txn_id: int, owner_id: int | None) -> Transaction:
        """Assign the transaction's selected owner to each of its ledger lines."""
        txn = self.get(txn_id)
        proposed = [replace(line, owner_id=owner_id) for line in txn.lines]
        with self.db.transaction():
            self._refuse_linked_loan_edit(txn, txn.date, proposed)
            self._validate_owner_balances(proposed, txn.date, exclude_txn_id=txn_id,
                                         force_brokerage_cash=txn.type == DocType.BUY,
                                         extra_keys=self._affected_owner_keys(txn.lines + proposed,
                                             force_brokerage_cash=txn.type == DocType.BUY))
            self.db.execute("UPDATE ledger_entries SET owner_id=? WHERE transaction_id=?", (owner_id, txn_id))
            updated = self.get(txn_id)
            self.audit.record("transaction", txn_id, "edit", f"Changed owner on {txn.ref}",
                              before=self._snapshot(txn), after=self._snapshot(updated))
        return self.get(txn_id)

    def mark_line_owner(self, txn_id: int, account_id: int, asset_id: int, quantity_e6: int,
                        owner_id: int) -> bool:
        """Mark ``quantity_e6`` (signed micro-units) of the transaction's first unowned line on this account and asset,
        with the same sign, as held for ``owner_id``. A part splits the line in two (2G3); returns False when no
        such line is left. Validated and audited like any other edit."""
        current = self.get(txn_id)
        if current.is_void:
            raise ValidationError("Restore this transaction before editing it.")
        index = next((i for i, line in enumerate(current.lines)
                      if line.account_id == account_id and line.asset_id == asset_id and line.owner_id is None
                      and to_e6(line.quantity) * quantity_e6 > 0), None)
        if index is None:
            return False
        cleared = {row["id"]: row["cleared"] for row in self.db.all(
            "SELECT id,cleared FROM ledger_entries WHERE transaction_id=?", (txn_id,))}
        lines = [PostingLine(account_id=ln.account_id, asset_id=ln.asset_id, quantity=ln.quantity, effect=ln.effect,
                             unit_price=ln.unit_price, fx_rate=ln.fx_rate, category_id=ln.category_id, memo=ln.memo,
                             amount=ln.amount, amount_base=ln.amount_base, owner_id=ln.owner_id,
                             is_cash=self.assets.get_asset(ln.asset_id).is_cash) for ln in current.lines]
        flags = [cleared.get(ln.id, 0) for ln in current.lines]
        line, stored = lines[index], current.lines[index]
        total = abs(to_e6(line.quantity))
        take = min(abs(quantity_e6), total)
        if take == total:
            lines[index] = replace(line, owner_id=owner_id)
        else:
            # Both parts keep whole cents and their own base amount (core/ledger.split_line_e6, 2G).
            owned_amount, owned_base, rest_amount, rest_base = split_line_e6(
                to_e6(line.amount), to_e6(line.fx_rate), take, total)
            if line.effect == Effect.INTERNAL and owned_base + rest_base != to_e6(line.amount_base):
                raise ValidationError("At this exchange rate that part leaves the transfer a cent out in "
                                      "your currency; mark a slightly different amount.", "amount")
            sign = -1 if line.quantity < ZERO else 1
            lines[index] = replace(line, quantity=from_e6(sign * (total - take)), amount=from_e6(rest_amount),
                                   amount_base=from_e6(rest_base))
            lines.append(replace(line, quantity=from_e6(sign * take), amount=from_e6(owned_amount),
                                 amount_base=from_e6(owned_base), owner_id=owner_id))
            flags.append(flags[index])
        validate_posting(lines)
        day = parse_date(current.date)
        self._refuse_linked_loan_edit(current, current.date, lines)
        # Both owners of the account and asset are checked: the person's part and what is left as yours.
        self._validate_owner_balances(lines, day, exclude_txn_id=txn_id,
                                      force_brokerage_cash=current.type == DocType.BUY,
                                      extra_keys={(account_id, asset_id, owner_id), (account_id, asset_id, None)})
        with self.db.transaction():
            self._refuse_linked_loan_edit(current, current.date, lines)
            self.repo.replace_lines(txn_id, current.date, lines)
            for line_no, flag in enumerate(flags, start=1):
                if flag:
                    self.db.execute("UPDATE ledger_entries SET cleared=? WHERE transaction_id=? AND line_no=?",
                                    (flag, txn_id, line_no))
            self.audit.record("transaction", txn_id, "edit", f"Changed owner on {current.ref}",
                              before=self._snapshot(current), after=self._snapshot(self.get(txn_id)))
        return True

    def update_refund(self, txn_id: int, date: str, account_id: int, amount, category_id: int,
                      description: str = "", counterparty: str = "", notes: str = "",
                      owner_id: int | None = None) -> Transaction:
        current = self._editable(txn_id, {DocType.IN})
        account = self.accounts.require_usable(account_id)
        self._refuse_physical_asset(account)
        day = self._check_date(date)
        asset = self.assets.cash_asset(account.currency)
        value = self._positive_amount(amount, asset.quantity_decimals)
        category_obj = self.categories.get(category_id)
        category = self.categories.require(category_id, Movement.OUTFLOW, allow_system=category_obj.is_system)
        if category.movement != Movement.OUTFLOW:
            raise ValidationError("Choose an expense category for a refund.", "category")
        if category.code == "EXP.SYSTEM.CUSTODY":
            raise ValidationError("Money held for others cannot be recorded as an expense refund.", "category")
        line = PostingLine.cash(account.id, asset.id, value, Effect.OUTFLOW, category.id,
                                memo="Refund", fx_rate=self._fx(account, day), owner_id=owner_id)
        return self._update(current, day, [line], description or "Refund", counterparty, notes)

    def _register_kind(self, amount: object, category_id: int | None, other_account_id: int | None):
        value = to_decimal(amount, "amount")
        if value == ZERO:
            raise ValidationError("Enter an amount: negative for money out (-450), positive for money in.", "amount")
        if other_account_id is not None:
            return DocType.TRF, value, None
        if category_id is None:
            raise ValidationError("Choose a category — or pick one of your accounts as the counterparty for a transfer.",
                                  "category")
        category = self.categories.get(category_id)
        return (DocType.OUT if value < 0 else DocType.IN), value, category.id

    def _tagged_notes(self) -> list:
        return self.repo.db.all("SELECT id, notes FROM transactions WHERE status='POSTED' AND instr(notes, '#') > 0")

    def tag_transaction_ids(self, tag: str) -> set[int]:
        """Posted transactions whose notes carry the tag (#eid matches #Eid, never #eid2026)."""
        tag = normal_tag(tag)
        return {int(row["id"]) for row in self._tagged_notes() if tag and tag in tags_in(row["notes"])}

    def tags(self) -> list[tuple[str, int]]:
        """Every tag in use, with how many posted transactions carry it, most used first."""
        counts: dict[str, int] = {}
        for row in self._tagged_notes():
            for tag in tags_in(row["notes"]):
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    def search_ids(self, text: str) -> set[int]:
        """Transaction ids matching a search (posted ones)."""
        ids = set(self.repo.ids(TxnFilter(search=text, limit=100000)))
        resolved = self.counterparties.resolve(text)
        if resolved:
            rows = self.repo.db.all(
                "SELECT id FROM transactions WHERE status!='VOID' AND counterparty_id=?",
                (resolved["id"],),
            )
            ids.update(int(row["id"]) for row in rows)
        # Include likely counterparty spellings so a near miss such as "Talbt"
        # still finds transactions, while exposing a human-confirmed suggestion.
        for name, _score in self.counterparties.suggestions(text, limit=5):
            rows = self.repo.db.all(
                "SELECT id FROM transactions WHERE status!='VOID' AND "
                "(counterparty_id=(SELECT id FROM counterparties WHERE name=?) OR counterparty LIKE ?)",
                (name, f"%{name}%"),
            )
            ids.update(int(row["id"]) for row in rows)
        return ids

    # A counterparty's usual category is a habit, not one odd filing (as in Actual Budget): the same
    # category in at least 3 of its last 5 transactions, or in every one while it has 2 to 4. Only the
    # 180 days before its newest transaction count, so an old habit fades.
    USUAL_WINDOW = 5
    USUAL_MIN = 3
    USUAL_DAYS = 180

    def usual_categories(self) -> dict[str, dict]:
        """The category each counterparty is usually filed under, when it has one: picked in at least
        3 of its last 5 transactions in the 180 days before its newest, or in all of them while it has
        2 to 4. {name: {category_id, count, total}}."""
        tally: dict[str, dict[int, list]] = {}
        totals: dict[str, set] = {}
        newest: dict = {}
        for row in self.repo.recent_categories(self.USUAL_WINDOW):
            name = row["counterparty"]
            day = parse_date(row["date"])
            newest.setdefault(name, day)  # rows come newest first
            if (newest[name] - day).days > self.USUAL_DAYS:
                continue
            seen = tally.setdefault(name, {})
            totals.setdefault(name, set()).add(row["id"])
            entry = seen.setdefault(row["category_id"], [0, (row["date"], row["id"])])
            entry[0] += 1
            entry[1] = max(entry[1], (row["date"], row["id"]))
        usual = {}
        for name, seen in tally.items():
            category_id, (count, _) = max(seen.items(), key=lambda kv: (kv[1][0], kv[1][1]))
            total = len(totals[name])
            if count >= self.USUAL_MIN or (2 <= total < self.USUAL_WINDOW and count == total):
                usual[name] = {"category_id": category_id, "count": count, "total": total}
        return usual

    def post(self, doc_type: DocType, date: str, lines: list[PostingLine], description: str = "",
             counterparty: str = "", notes: str = "", source: TxnSource = TxnSource.MANUAL) -> Transaction:
        """Record any document from lines built by another module (investments). Same rules as everything else:
        accounts usable, date not in the future, lines valid, holdings never below zero.
        """
        for account_id in {ln.account_id for ln in lines}:
            self.accounts.require_usable(account_id)
        self._validate_deposit_lines(lines, doc_type, source)
        day = self._check_date(date)
        validate_posting(lines)  # _create checks owner balances
        return self._create(doc_type, day, lines, description, counterparty, notes, source)

    def repost(self, txn_id: int, date: str, lines: list[PostingLine], description: str = "",
               counterparty: str = "", notes: str = "") -> Transaction:
        """Replace the lines of a document built by another module; the ref never changes."""
        current = self.get(txn_id)
        if current.is_void:
            raise ValidationError("Restore this transaction before editing it.")
        for account_id in {ln.account_id for ln in lines}:
            self.accounts.require_usable(account_id)
        self._validate_deposit_lines(lines, current.type, current.source)
        day = self._check_date(date)
        validate_posting(lines)  # _update checks owner balances, excluding this transaction
        return self._update(current, day, lines, description, counterparty, notes)

    def _affected_owner_keys(self, lines, *, force_brokerage_cash=False, validate_all_cash=False):
        """Include removed owners and the owned side of an ownership change (2H)."""
        cash_scopes = {(line.account_id, line.asset_id) for line in lines
                       if line.owner_id is not None or validate_all_cash or
                       (force_brokerage_cash and self.accounts.get(line.account_id).account_type == AccountType.BROKERAGE)}
        return {(line.account_id, line.asset_id, line.owner_id) for line in lines
                if not self.assets.get_asset(line.asset_id).is_cash or
                (line.account_id, line.asset_id) in cash_scopes}

    def _validate_owner_balances(self, lines, day, exclude_txn_id=None, force_brokerage_cash=False,
                                 validate_all_cash=False, extra_keys=(), ignore_before_day=False,
                                 validate_from=None):
        """An owner's dated account/asset position may never become negative."""
        keys = set(extra_keys)
        for line in lines:
            asset = self.assets.get_asset(line.asset_id)
            account = self.accounts.get(line.account_id)
            if line.owner_id is not None:
                owner = self.db.one("SELECT id FROM counterparties WHERE id=? AND active=1", (line.owner_id,))
                if not owner:
                    raise ValidationError("Choose an active saved owner.", "owner_id")
            if ((line.owner_id is not None and line.quantity != ZERO) or not asset.is_cash or
                    (validate_all_cash and asset.is_cash and line.quantity != ZERO) or
                    (force_brokerage_cash and line.effect == Effect.INTERNAL and
                     account.account_type == AccountType.BROKERAGE)):
                keys.add((line.account_id, line.asset_id, line.owner_id))
        for account_id, asset_id, owner_id in keys:
            params = [account_id, asset_id, owner_id]
            sql = ("SELECT le.date, SUM(le.quantity_e6) q FROM ledger_entries le "
                   "JOIN transactions t ON t.id=le.transaction_id "
                   "WHERE t.status='POSTED' AND le.account_id=? AND le.asset_id=? AND le.owner_id IS ?")
            if exclude_txn_id is not None:
                sql += " AND t.id<>?"
                params.append(exclude_txn_id)
            sql += " GROUP BY le.date ORDER BY le.date"
            proposed = sum(int(line.quantity * 1_000_000) for line in lines
                           if (line.account_id, line.asset_id, line.owner_id) == (account_id, asset_id, owner_id))
            by_day = {}
            for row in self.db.all(sql, tuple(params)):
                by_day[row["date"]] = int(row["q"])
            by_day[str(day)] = by_day.get(str(day), 0) + proposed
            running = 0
            for on, quantity in sorted(by_day.items()):
                before_day = running
                running += quantity
                if running < 0 and (not ignore_before_day or on >= str(validate_from or day)):
                    asset = self.assets.get_asset(asset_id)
                    if not asset.is_cash:
                        raise ValidationError(
                            f"{self.accounts.get(account_id).label} would hold less than zero {asset.name} on {on}.",
                            "quantity")
                    owner_label = "the user's" if owner_id is None else "the selected owner's"
                    after = Decimal(running).scaleb(-6)
                    before = Decimal(before_day).scaleb(-6)
                    account = self.accounts.get(account_id)
                    context = (f"This purchase is dated {day}; check whether later payments still fit."
                               if on > str(day) else
                               "Only cash available on the purchase date can fund it.")
                    raise ValidationError(
                        f"This would leave {owner_label} balance at {fmt(after, 2, True)} {account.currency} "
                        f"in {account.label} on {on}; the balance before that date's transactions was "
                        f"{fmt(before, 2)} {account.currency}. {context}",
                        "owner")

    def _refuse_cash_below_zero(self, lines, day, current: Transaction | None = None, *, removed=(), added=()) -> None:
        """Compare every affected cash history before/after the whole action (2G/2H).

        Snapshots of removed postings make this work before or after SQL changes,
        including multi-delete and restoring a void document. Imported/system
        posting history may contain deficits; unchanged or improved days remain editable.
        """
        previous = [txn for txn in (([current] if current else []) + list(removed)) if not txn.is_void]
        following = [(str(day), lines)] + [(txn.date, txn.lines) for txn in added if not txn.is_void]
        old_lines = [line for txn in previous for line in txn.lines]
        new_lines = [line for _, posting in following for line in posting]
        keys = {(line.account_id, line.asset_id) for line in new_lines + old_lines
                if line.quantity != ZERO and self.assets.get_asset(line.asset_id).is_cash}
        excluded = {txn.id for txn in previous} | {txn.id for txn in added}
        if current:
            excluded.add(current.id)
        first = min([str(day)] + [txn.date for txn in previous] + [on for on, _ in following])
        for account_id, asset_id in keys:
            account = self.accounts.get(account_id)
            if account.account_type not in {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE}:
                continue
            start = max(first, account.opening_date)
            # Aggregate the opening balance once, then walk affected days on the account index.
            exclusion = " AND le.transaction_id NOT IN (" + ",".join("?" for _ in excluded) + ")" if excluded else ""
            opening = self.db.scalar(
                "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le "
                "JOIN transactions t ON t.id=le.transaction_id "
                "WHERE t.status='POSTED' AND le.account_id=? AND le.date<? AND +le.asset_id=?" + exclusion,
                (account_id, start, asset_id, *excluded))
            base = {"": int(opening)}
            for row in self.db.all(
                "SELECT le.date, SUM(le.quantity_e6) q FROM ledger_entries le "
                "JOIN transactions t ON t.id=le.transaction_id "
                "WHERE t.status='POSTED' AND le.account_id=? AND le.date>=? AND +le.asset_id=?" + exclusion +
                " GROUP BY le.date",
                (account_id, start, asset_id, *excluded)):
                base[row["date"]] = int(row["q"])
            before, after = dict(base), dict(base)
            for txn in previous:
                for line in txn.lines:
                    if (line.account_id, line.asset_id) == (account_id, asset_id):
                        before[txn.date] = before.get(txn.date, 0) + int(line.quantity * 1_000_000)
            for on, posting in following:
                for line in posting:
                    if (line.account_id, line.asset_id) == (account_id, asset_id):
                        after[on] = after.get(on, 0) + int(line.quantity * 1_000_000)
            old_balance = new_balance = 0
            for on in sorted(set(before) | set(after) | {start}):
                old_balance += before.get(on, 0)
                new_balance += after.get(on, 0)
                if on >= start and new_balance < min(0, old_balance):
                    raise ValidationError(
                        f"This would leave {account.label} at {fmt(Decimal(new_balance).scaleb(-6), 2, True)} "
                        f"{account.currency} on {on}. Move money in first, or record the smaller amount.", "amount")

    def _validate_deposit_lines(self, lines, doc_type: DocType, source: TxnSource) -> None:
        """CD portfolios hold certificate assets only; cash stays in bank and wallet accounts."""
        for line in lines:
            account = self.accounts.get(line.account_id)
            asset = self.assets.get_asset(line.asset_id)
            is_certificate = self.assets.get_class(asset.asset_class_id).code == "DEPOSIT.CD"
            if account.account_type == AccountType.DEPOSIT:
                if asset.is_cash:
                    raise ValidationError("A CD portfolio cannot hold cash. Use the CD purchase or redemption action.")
                if (doc_type == DocType.VAL and source == TxnSource.SYSTEM and
                        line.effect == Effect.REVALUATION and line.quantity == ZERO and not line.is_cash and
                        is_certificate):
                    continue
                if not is_certificate or doc_type not in {DocType.BUY, DocType.SEL}:
                    raise ValidationError("Only CD certificates can be traded in a CD portfolio.", "asset")
            elif is_certificate:
                raise ValidationError("Certificates must be held in a bank-specific CD portfolio.", "account")

    def set_opening_balance(self, account_id: int, amount: Decimal, date: str,
                            owner_id: int | None = None) -> Transaction | None:
        """Create, change or remove an account's opening balance (signed: liabilities are negative).

        Called by the workflow layer when an account is opened or edited.
        """
        account = self.accounts.get(account_id)
        day = parse_date(date, "opening_date")
        asset = self.assets.cash_asset(account.currency)
        amount = check_places(to_decimal(amount, "opening_balance"), asset.quantity_decimals, "opening_balance")
        existing_id = self.repo.opening_txn_id(account_id)  # the cash opening balance
        with self.db.transaction():
            if amount == ZERO:
                if existing_id:
                    self.void(existing_id, "Opening balance set to zero")
                return None
            lines = [PostingLine.cash(account.id, asset.id, amount, Effect.OPENING,
                                      fx_rate=self._fx(account, day), memo="Opening balance", owner_id=owner_id)]
            validate_posting(lines)  # _create/_update check owner balances, excluding the opening being replaced
            if existing_id:
                current = self.get(existing_id)
                return self._update(current, day, lines, current.description, "", current.notes)
            return self._create(DocType.OPN, day, lines, f"Opening balance — {account.name}", "", "",
                                TxnSource.SYSTEM)

    def opening_txn_id(self, account_id: int, asset_id: int | None = None, exclude_id: int | None = None) -> int | None:
        """The live opening transaction for an account's cash (asset_id None) or for one of its holdings."""
        return self.repo.opening_txn_id(account_id, asset_id, exclude_id)

    def opening_balance(self, account_id: int) -> Decimal:
        """The account's opening cash balance."""
        txn_id = self.repo.opening_txn_id(account_id)
        if not txn_id:
            return ZERO
        return sum((ln.quantity for ln in self.get(txn_id).lines if ln.account_id == account_id
                    and self.assets.get_asset(ln.asset_id).is_cash), ZERO)

    # ======================================================================
    # Editing, voiding
    # ======================================================================
    def update_money(self, txn_id: int, date: str, account_id: int, amount, category_id: int,
                     description: str = "", counterparty: str = "", notes: str = "",
                     owner_id: int | None = None) -> Transaction:
        current = self._editable(txn_id, {DocType.IN, DocType.OUT})
        movement = Movement.INFLOW if current.type == DocType.IN else Movement.OUTFLOW
        category = self.categories.get(category_id)
        unchanged_category = any(line.category_id == category_id for line in current.lines)
        day, lines = self._money_lines(movement, date, account_id, amount, category_id,
                                       allow_system_category=category.is_system,
                                       allow_inactive_category=unchanged_category)
        lines = [replace(line, owner_id=owner_id) for line in lines]
        return self._update(current, day, lines, description, counterparty, notes)

    def update_metadata(self, txn_id: int, date: str, counterparty: str = "", notes: str = "") -> Transaction:
        """Edit transaction details without rebuilding or changing its ledger lines."""
        current = self._editable(txn_id, EDITABLE_TYPES)
        day = self._check_date(date)
        return self._update(current, day, list(current.lines), current.description, counterparty, notes)

    def set_category(self, txn_ids: list[int], category_id: int) -> tuple[list[int], list[int]]:
        """Give several money-in or money-out rows one category (the selection bar's control)."""
        return self.bulk_update(txn_ids, {"category_id": category_id})

    def bulk_update(self, txn_ids: list[int], changes: dict) -> tuple[list[int], list[int]]:
        """Edit many money-in or money-out rows at once, one DB transaction. ``changes`` holds only what the
        user changed: ``date``, ``counterparty``, ``notes``, ``category_id``, ``owner_id`` (Held for; only for
        money held for others). Amounts are never bulk-edited. Each row goes through the single-row edit
        path (``_update``). Rows that cannot take the change (transfers, investment and opening rows, split
        expenses, voided rows, a category for the other direction) are skipped whole. Returns (changed, skipped)."""
        category = self.categories.get(changes["category_id"]) if changes.get("category_id") else None
        # Money held for others needs an owner per row, so it is never set in bulk.
        if category and (category.is_system or category.code == "EXP.SYSTEM.CUSTODY"):
            raise ValidationError("Choose a spending or income category.", "category")
        day = self._check_date(changes["date"]) if "date" in changes else None
        changed, skipped = [], []
        with self.db.transaction():
            for txn_id in dict.fromkeys(txn_ids):
                current = self.get(txn_id)
                lines_with_category = [line for line in current.lines if line.category_id]
                wanted = Direction.IN if current.type == DocType.IN else Direction.OUT
                if (current.is_void or current.type not in {DocType.IN, DocType.OUT} or len(lines_with_category) != 1
                        or (category and category.direction not in (wanted, Direction.BOTH))):
                    skipped.append(txn_id)
                    continue
                lines = list(current.lines)
                if category:
                    lines = [replace(line, category_id=category.id) if line.category_id else line for line in lines]
                if "owner_id" in changes:
                    row_category = self.categories.get(lines_with_category[0].category_id if not category else category.id)
                    if row_category.code != "EXP.SYSTEM.CUSTODY":
                        skipped.append(txn_id)
                        continue
                    lines = [replace(line, owner_id=changes["owner_id"]) for line in lines]
                try:
                    self._update(current, day or parse_date(current.date), lines, current.description,
                                 changes["counterparty"] if "counterparty" in changes else current.counterparty,
                                 changes["notes"] if "notes" in changes else current.notes)
                except LightningError as exc:
                    raise ValidationError(f"{current.ref}: {exc.message}", exc.field) from exc
                changed.append(txn_id)
        return changed, skipped

    def update_expense_split(self, txn_id: int, allocations: list[tuple[int, object]]) -> Transaction:
        """Replace an expense's category allocation while preserving its total cash movement."""
        current = self._editable(txn_id, {DocType.OUT})
        cash_lines = [line for line in current.lines if self.assets.get_asset(line.asset_id).is_cash]
        if len(cash_lines) != len(current.lines) or not cash_lines:
            raise ValidationError("Only ordinary cash expenses can be split.")
        account_ids = {line.account_id for line in cash_lines}
        if len(account_ids) != 1:
            raise ValidationError("This expense cannot be split across accounts.")
        total = -sum((line.quantity for line in cash_lines), ZERO)
        if any(self.categories.get(line.category_id).code == "EXP.SYSTEM.CUSTODY"
               for line in cash_lines if line.category_id):
            raise ValidationError("Money held for others cannot be split as a personal expense.")
        account_id = next(iter(account_ids))
        account = self.accounts.require_usable(account_id)
        asset = self.assets.cash_asset(account.currency)
        parsed: list[tuple[int, Decimal]] = []
        for category_id, raw_amount in allocations:
            amount = check_places(to_decimal(raw_amount, "split_amount"), asset.quantity_decimals, "split_amount")
            if amount <= ZERO:
                raise ValidationError("Each split amount must be greater than zero.", "split_amount")
            category = self.categories.require(category_id, Movement.OUTFLOW)
            if category.movement != Movement.OUTFLOW:
                raise ValidationError("Choose an expense category for each split row.", "split_category_id")
            if category.code == "EXP.SYSTEM.CUSTODY":
                raise ValidationError("Money held for others cannot be split as a personal expense.")
            parsed.append((category.id, amount))
        if not parsed:
            raise ValidationError("Add at least one category and amount.")
        if sum((amount for _, amount in parsed), ZERO) != total:
            raise ValidationError(f"Split amounts must add up to the transaction total ({fmt(total)}).", "split_amount")
        fx_rate = self._fx(account, parse_date(current.date))
        lines = [PostingLine.cash(account_id, asset.id, -amount, Effect.OUTFLOW, category_id,
                                 fx_rate=fx_rate) for category_id, amount in parsed]
        return self._update(current, parse_date(current.date), lines, current.description, current.counterparty,
                            current.notes)

    def update_transfer(self, txn_id: int, date: str, from_account_id: int, to_account_id: int, amount,
                        description: str = "", notes: str = "", owner_id: int | None = None) -> Transaction:
        current = self._editable(txn_id, {DocType.TRF})
        day, lines = self._transfer_lines(date, from_account_id, to_account_id, amount)
        lines = [replace(line, owner_id=owner_id) for line in lines]
        return self._update(current, day, lines, description, "", notes)

    def record_conversion(self, date: str, from_account_id: int, to_account_id: int, sent, received, fee=None,
                          description: str = "", notes: str = "",
                          source: TxnSource = TxnSource.MANUAL) -> Transaction:
        """Your own money changing currency: `sent` leaves one account, `received` arrives in another, and an
        optional `fee` (in the sending currency) is an expense. The executed rate is kept as a dated rate."""
        day, lines = self._conversion_lines(date, from_account_id, to_account_id, sent, received, fee)
        with self.db.transaction():
            created = self.post(DocType.CNV, day, lines, description, "", notes, source)
            conversion.refresh_trade_rates(self, [created])
        return created

    def update_conversion(self, txn_id: int, date: str, from_account_id: int, to_account_id: int, sent, received,
                          fee=None, description: str = "", notes: str = "") -> Transaction:
        current = self._editable(txn_id, {DocType.CNV})
        day, lines = self._conversion_lines(date, from_account_id, to_account_id, sent, received, fee)
        with self.db.transaction():
            previous = self.get(txn_id)
            updated = self.repost(txn_id, day, lines, description, "", notes)
            conversion.refresh_trade_rates(self, [previous, updated])
        return updated

    def conversion_of(self, t: Transaction):
        """A conversion read back: amounts, currencies, fee, executed rate (None for any other document)."""
        return conversion.describe(self, t) if t.type == DocType.CNV else None

    def conversion_spread(self, t: Transaction):
        """What the bank kept beyond the market rate, in the profile currency (None: no market rate that day)."""
        described = self.conversion_of(t)
        return conversion.spread_cost(self, described, t.date) if described else None

    def conversion_quote(self, date: str, from_account_id: int, to_account_id: int, sent, received):
        """For the Convert form: the executed rate and its distance from the day's market rate."""
        return conversion.quote(self, fmt_date(parse_date(date)), self.accounts.get(from_account_id),
                                self.accounts.get(to_account_id), sent, received)

    def _conversion_lines(self, date: str, from_id: int, to_id: int, sent, received, fee):
        src = self.accounts.require_usable(from_id, "from_account")
        dst = self.accounts.require_usable(to_id, "to_account")
        day = self._check_date(date)
        lines = conversion.build(self, fmt_date(day), src, dst, sent, received, fee)
        validate_posting(lines)
        return day, lines

    def void(self, txn_id: int, reason: str = "") -> Transaction:
        """Cancel a transaction. It stays visible (greyed out) and can be restored."""
        t = self.get(txn_id)
        if t.type == DocType.VAL and t.source == TxnSource.SYSTEM:
            self.delete_many([txn_id])
            return self.get(txn_id)
        if t.is_void:
            return t
        with self.db.transaction():
            self.repo.set_status(t.id, TxnStatus.VOID)
            custody_keys = self._affected_owner_keys(t.lines, force_brokerage_cash=t.type == DocType.BUY,
                                                      validate_all_cash=self._is_ownership_transaction(t))
            if custody_keys:
                self._validate_owner_balances([], t.date, validate_all_cash=True, extra_keys=custody_keys,
                                              ignore_before_day=True)
            self._refuse_cash_below_zero([], t.date, removed=[t])
            self._check_holdings(t.lines)
            self.audit.record("transaction", t.id, "void", reason or f"Voided {t.ref}")
            if t.type == DocType.CNV:
                conversion.refresh_trade_rates(self, [t])
        return self.get(txn_id)

    def delete_many(self, txn_ids: list[int]) -> int:
        """Hide selected transactions from normal views while retaining audit and restore history."""
        ids = list(dict.fromkeys(int(value) for value in txn_ids))
        transactions = [self.get(txn_id) for txn_id in ids]
        if any(txn.type == DocType.OPN and not txn.is_void for txn in transactions):
            raise ValidationError("Change an opening balance from the account edit page.")
        pending = [txn for txn in transactions if not txn.is_void]
        if not pending:
            return 0
        lines = [line for txn in pending for line in txn.lines]
        with self.db.transaction():
            for txn in pending:
                if txn.type == DocType.VAL and txn.source == TxnSource.SYSTEM:
                    post = self.db.one("SELECT period_id,account_id FROM reevaluation_account_posts WHERE transaction_id=?",
                                       (txn.id,))
                    if post:
                        self.db.execute("INSERT OR IGNORE INTO reevaluation_suppressed_accounts(period_id,account_id,created_at) "
                                        "VALUES(?,?,datetime('now'))", (post["period_id"], post["account_id"]))
                        self.db.execute("UPDATE reevaluation_periods SET source_hash='' WHERE date>"
                                        "(SELECT date FROM reevaluation_periods WHERE id=?)", (post["period_id"],))
                self.repo.set_status(txn.id, TxnStatus.VOID)
                self.audit.record("transaction", txn.id, "void", f"Deleted by user: {txn.ref}")
            custody_keys = {key for txn in pending
                            for key in self._affected_owner_keys(txn.lines, force_brokerage_cash=txn.type == DocType.BUY,
                                                                 validate_all_cash=self._is_ownership_transaction(txn))}
            if custody_keys:
                self._validate_owner_balances([], min(txn.date for txn in pending),
                                              validate_all_cash=True, extra_keys=custody_keys,
                                              ignore_before_day=True)
            self._refuse_cash_below_zero([], min(txn.date for txn in pending), removed=pending)
            self._check_holdings(lines)
            if any(txn.type == DocType.CNV for txn in pending):
                conversion.refresh_trade_rates(self, pending)
        return len(pending)

    def restore(self, txn_id: int) -> Transaction:
        t = self.get(txn_id)
        if not t.is_void:
            return t
        if t.type == DocType.OPN:
            for line in t.lines:
                asset = self.assets.get_asset(line.asset_id)
                if self.repo.opening_txn_id(line.account_id, None if asset.is_cash else asset.id, exclude_id=t.id):
                    raise ValidationError("This account already has another opening balance for that.")
        with self.db.transaction():
            if t.type == DocType.VAL and t.source == TxnSource.SYSTEM:
                post = self.db.one("SELECT period_id,account_id FROM reevaluation_account_posts WHERE transaction_id=?",
                                   (t.id,))
                if not post:
                    # The engine voided it when it recalculated the checkpoint;
                    # the replacement is already posted.
                    raise ValidationError("This revaluation was replaced by a newer calculation, so it can't be restored.")
                if post:
                    self.db.execute("DELETE FROM reevaluation_suppressed_accounts WHERE period_id=? AND account_id=?",
                                    (post["period_id"], post["account_id"]))
                    self.db.execute("UPDATE reevaluation_periods SET source_hash='' WHERE date>="
                                    "(SELECT date FROM reevaluation_periods WHERE id=?)", (post["period_id"],))
            # re-validate against today's rules (accounts may have been deactivated)
            for line in t.lines:
                self.accounts.require_usable(line.account_id)
            self._check_date(t.date)
            if self._is_ownership_transaction(t):
                self._validate_owner_balances(t.lines, t.date, exclude_txn_id=t.id, validate_all_cash=True,
                                              ignore_before_day=True)
            else:
                self._validate_owner_balances(t.lines, t.date, exclude_txn_id=t.id, ignore_before_day=True,
                                             force_brokerage_cash=t.type == DocType.BUY)
            self._refuse_cash_below_zero(t.lines, t.date, t)
            self.repo.set_status(t.id, TxnStatus.POSTED)
            self._check_holdings(t.lines)
            self.check_reserve_links([t.id])
            self.audit.record("transaction", t.id, "restore", f"Restored {t.ref}")
            if t.type == DocType.CNV:
                conversion.refresh_trade_rates(self, [t])
        return self.get(txn_id)

    # ======================================================================
    # Reading
    # ======================================================================
    def replaced_revaluation_ids(self) -> set[int]:
        """System revaluations voided because the engine recalculated their checkpoint."""
        return {int(row["id"]) for row in self.db.all(
            "SELECT t.id FROM transactions t WHERE t.type='VAL' AND t.source='SYSTEM' AND t.status='VOID' "
            "AND NOT EXISTS (SELECT 1 FROM reevaluation_account_posts p WHERE p.transaction_id=t.id)")}

    # -- one save per submitted form (2J) ------------------------------------------------------------------
    @staticmethod
    def _submission(token, payload: dict) -> tuple[str, str] | None:
        token = str(token or "")
        if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
            return None  # Callers without a token keep the old contract.
        body = json.dumps({key: str(value) for key, value in payload.items()}, sort_keys=True, ensure_ascii=False)
        return token, hashlib.sha256(body.encode()).hexdigest()

    def submitted(self, token, payload: dict) -> Transaction | None:
        """The transaction an earlier delivery of this same form created, if any. Call inside the write transaction."""
        found = self._submission(token, payload)
        if found is None:
            return None
        row = self.db.one("SELECT entity_id, after_json FROM audit_log WHERE entity='form' AND summary=?", (found[0],))
        if row is None:
            return None
        txn = self.repo.get(int(row["entity_id"]))
        if txn is None or txn.is_void or json.loads(row["after_json"]) != found[1]:
            ref = f" as {txn.ref}" if txn is not None else ""
            raise ValidationError(f"This form was already saved{ref}. Open a new one to add another.")
        return txn

    def remember_submission(self, token, payload: dict, txn_id: int) -> None:
        """Saved in the audit log, in the same write as the transaction; the log is outside Undo and the journal."""
        found = self._submission(token, payload)
        if found is not None:
            self.audit.record("form", txn_id, "SUBMITTED", found[0], after=found[1])

    def get(self, txn_id: int) -> Transaction:
        found = self.repo.get(txn_id) if 0 < txn_id <= 9_223_372_036_854_775_807 else None  # SQLite's largest id (2E6)
        if not found:
            raise NotFoundError("Transaction not found.")
        return found

    def revision(self, txn_id: int) -> str:
        """Opaque form version, covering the header and every posting line."""
        payload = json.dumps(self._snapshot(self.get(txn_id)), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def require_revision(self, txn_id: int, expected: str | None) -> None:
        """Call inside the write transaction. None retains legacy client behavior."""
        if expected is not None and expected != self.revision(txn_id):
            raise ValidationError(
                "This transaction changed since you opened it. Reopen it before saving.", "revision")

    def get_by_ref(self, ref: str) -> Transaction:
        found = self.repo.get_by_ref((ref or "").strip().upper())
        if not found:
            raise NotFoundError(f"Transaction {ref} not found.")
        return found

    def find(self, f: TxnFilter) -> tuple[list[TxnSummary], int]:
        txns, total = self.repo.list(f)
        return [self.summarize(t) for t in txns], total

    def count_for_account(self, account_id: int) -> int:
        return self.repo.count_for_account(account_id)

    def earliest_activity(self, account_id: int) -> str | None:
        """Date of the account's first posted transaction other than its opening balance."""
        return self.repo.earliest_activity(account_id)

    def history(self, txn_id: int) -> list[dict]:
        return self.audit.history("transaction", txn_id)

    def summarize(self, t: Transaction) -> TxnSummary:
        account_id = to_account_id = category_id = None
        amount = ZERO
        if t.type == DocType.TRF:
            out_line = next((ln for ln in t.lines if ln.quantity < 0), None)
            in_line = next((ln for ln in t.lines if ln.quantity > 0), None)
            account_id = out_line.account_id if out_line else None
            to_account_id = in_line.account_id if in_line else None
            amount = in_line.quantity if in_line else ZERO
        type_label = t.type_label
        to_amount, to_currency, rate = ZERO, "", None
        if t.type == DocType.CNV and (described := conversion.describe(self, t)):
            account_id, to_account_id = described.src_account_id, described.dst_account_id
            amount, to_amount, to_currency, rate = described.sent, described.received, described.received_currency, described.rate
        elif t.type == DocType.ADJ and self._is_ownership_transaction(t):
            cash = [ln for ln in t.lines if self.assets.get_asset(ln.asset_id).is_cash]
            outflow = next((ln for ln in cash if ln.effect == Effect.OUTFLOW), None)
            if outflow:
                type_label = "Expense paid for you"
                first = outflow
                account_id, category_id = first.account_id, first.category_id
                amount = outflow.quantity
            else:
                type_label = "Ownership change"
                first = cash[0] if cash else (t.lines[0] if t.lines else None)
                if first:
                    account_id, category_id = first.account_id, first.category_id
                    own_line = next((line for line in cash if line.owner_id is None), None)
                    amount = own_line.quantity if own_line else max((abs(line.quantity) for line in cash), default=ZERO)
        elif t.lines:
            cash = [ln for ln in t.lines if self.assets.get_asset(ln.asset_id).is_cash]
            first = (cash or t.lines)[0]
            account_id, category_id = first.account_id, first.category_id
            if t.type == DocType.VAL and t.source == TxnSource.SYSTEM:
                amount = first.amount
            else:
                amount = sum((ln.quantity for ln in cash), ZERO)  # 0 for a holding-only document
        currency = self.accounts.get(account_id).currency if account_id else self.base_currency
        return TxnSummary(
            id=t.id,
            ref=t.ref,
            date=t.date,
            type=t.type,
            type_label=type_label,
            status=t.status,
            description=t.description,
            counterparty=t.counterparty,
            notes=t.notes,
            amount=amount,
            currency=currency,
            account_label=self.accounts.get(account_id).label if account_id else "",
            to_account_label=self.accounts.get(to_account_id).label if to_account_id else "",
            category_label=self.categories.display_name(category_id) if category_id else "",
            category_code=self.categories.get(category_id).code if category_id else "",
            account_id=account_id,
            to_account_id=to_account_id,
            category_id=category_id,
            to_amount=to_amount,
            to_currency=to_currency,
            rate=rate,
        )

    @staticmethod
    def _is_ownership_transaction(txn: Transaction) -> bool:
        return txn.type == DocType.ADJ and txn.description.startswith("Ownership:")

    def _ownership_cash_keys(self, lines):
        keys = set()
        for line in lines:
            asset = self.assets.get_asset(line.asset_id)
            if asset.is_cash:
                keys.add((line.account_id, line.asset_id, line.owner_id))
        return keys

    def _tagged_cash_keys(self, lines):
        return {(line.account_id, line.asset_id, line.owner_id) for line in lines
                if line.owner_id is not None and self.assets.get_asset(line.asset_id).is_cash}

    # ======================================================================
    # Internals
    # ======================================================================
    def _money_lines(self, movement: Movement, date: str, account_id: int, amount, category_id: int,
                     allow_system_category: bool = False, allow_inactive_category: bool = False):
        account = self.accounts.require_usable(account_id)
        if account.account_type == AccountType.DEPOSIT:
            raise ValidationError("A CD portfolio cannot hold cash.")
        self._refuse_physical_asset(account)
        day = self._check_date(date)
        asset = self.assets.cash_asset(account.currency)
        value = self._positive_amount(amount, asset.quantity_decimals)
        category = self.categories.require(category_id, movement, allow_system=allow_system_category,
                                           allow_inactive=allow_inactive_category)
        signed = value if movement == Movement.INFLOW else -value
        effect = Effect.INFLOW if movement == Movement.INFLOW else Effect.OUTFLOW
        lines = [PostingLine.cash(account.id, asset.id, signed, effect, category.id,
                                  fx_rate=self._fx(account, day))]
        validate_posting(lines)
        return day, lines

    @staticmethod
    def _refuse_physical_asset(account: Account) -> None:
        if account.account_type == AccountType.PHYSICAL_ASSET:
            raise ValidationError("A physical asset account holds things, not cash. Use a bank or cash account for the money.",
                                  "account")

    def _transfer_lines(self, date: str, from_id: int, to_id: int, amount,
                        allow_legacy_deposit_cash: bool = False):
        src = self.accounts.require_usable(from_id, "from_account")
        dst = self.accounts.require_usable(to_id, "to_account")
        if src.id == dst.id:
            raise ValidationError("Choose two different accounts.", "to_account")
        # A gam'eya circle receives instalments and pays out your turn as transfers (lightning/deposits/gameya.py).
        source_accounts = {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE, AccountType.GAMEYA}
        if allow_legacy_deposit_cash:
            source_accounts.add(AccountType.DEPOSIT)
        destination_accounts = {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE, AccountType.GAMEYA}
        if src.account_type not in source_accounts or dst.account_type not in destination_accounts:
            raise ValidationError("Transfers can move cash from wallets, banks, or legacy deposit balances into liquid accounts.", "to_account")
        if src.currency != dst.currency:
            raise ValidationError("Both accounts must use the same currency; to change currency, use Convert.", "to_account")
        day = self._check_date(date)
        asset = self.assets.cash_asset(src.currency)
        value = self._positive_amount(amount, asset.quantity_decimals)
        lines = [
            PostingLine.cash(src.id, asset.id, -value, Effect.INTERNAL, fx_rate=self._fx(src, day), memo="Transfer out"),
            PostingLine.cash(dst.id, asset.id, value, Effect.INTERNAL, fx_rate=self._fx(dst, day), memo="Transfer in"),
        ]
        validate_posting(lines)
        return day, lines

    def _create(self, doc_type: DocType, day, lines: list[PostingLine], description: str, counterparty: str,
                notes: str, source: TxnSource, validate_all_cash: bool = False) -> Transaction:
        with self.db.transaction():
            self._check_line_identity(lines)
            self._validate_owner_balances(lines, day, force_brokerage_cash=doc_type == DocType.BUY,
                                          validate_all_cash=validate_all_cash,
                                          ignore_before_day=validate_all_cash)
            if source == TxnSource.MANUAL or doc_type == DocType.OPN:
                self._refuse_cash_below_zero(lines, day)
            ref = format_ref(doc_type, day, self.repo.next_seq(ref_prefix(doc_type, day)))
            header = Transaction(
                id=0, ref=ref, type=doc_type, date=fmt_date(day),
                description=(description or "").strip(), counterparty=(counterparty or "").strip(),
                status=TxnStatus.POSTED, source=source, notes=(notes or "").strip(),
                created_at="", updated_at="",
            )
            canonical = self._canonical_counterparty(doc_type, header.counterparty)
            if canonical:
                header.counterparty = canonical["name"]
            txn_id = self.repo.insert(header, lines, canonical["id"] if canonical else None)
            self._check_holdings(lines)
        return self.get(txn_id)

    @staticmethod
    def _same_posting(current: Transaction, day, lines) -> bool:
        fields = ("account_id", "asset_id", "quantity", "unit_price", "fx_rate", "amount", "amount_base",
                  "effect", "category_id", "memo", "owner_id")
        def values(line):
            return tuple(getattr(line, name) for name in fields)
        return (current.date == str(day) and
                [values(line) for line in current.lines] == [values(line) for line in lines])

    def _refuse_linked_loan_edit(self, current, day, lines):
        """A confirmed repayment's principal/fee allocation cannot be guessed after a ledger edit."""
        if self._same_posting(current, day, lines):
            return
        if self.db.scalar("SELECT 1 FROM loan_extra_payments WHERE transaction_id=?", (current.id,)):
            raise ValidationError("Void this loan repayment and record a corrected payment from Loans.")
        if self.db.scalar("SELECT 1 FROM planned_payments p JOIN planned_items i ON i.id=p.planned_item_id "
                          "WHERE p.transaction_id=? AND i.kind='LOAN'", (current.id,)):
            raise ValidationError("Reopen this loan payment before changing its amount, date, account or category.")

    def _validate_linked_loan_amount(self, txn):
        """Undo may restore both the ledger and its settlement, but may not drift an existing link."""
        expected = self.db.all(
            "SELECT p.amount_e6 FROM planned_payments p JOIN planned_items i ON i.id=p.planned_item_id "
            "WHERE p.transaction_id=? AND i.kind='LOAN' AND p.status='PAID' "
            "UNION ALL SELECT principal_e6+fee_e6 AS amount_e6 FROM loan_extra_payments WHERE transaction_id=?",
            (txn.id, txn.id))
        if not expected:
            return
        actual = sum((abs(line.quantity) for line in txn.lines if line.owner_id is None and
                      line.effect == Effect.OUTFLOW and self.assets.get_asset(line.asset_id).is_cash), ZERO)
        if any(from_e6(row["amount_e6"]) != actual for row in expected):
            raise ValidationError("Reopen this loan payment before changing its amount, date, account or category.")

    def _update(self, current: Transaction, day, lines: list[PostingLine], description: str, counterparty: str,
                notes: str, validate_all_cash: bool = False) -> Transaction:
        with self.db.transaction():
            self._check_line_identity(lines)
            self._refuse_linked_loan_edit(current, day, lines)
            self._validate_owner_balances(lines, day, exclude_txn_id=current.id,
                                         force_brokerage_cash=current.type == DocType.BUY,
                                         validate_all_cash=validate_all_cash,
                                         ignore_before_day=validate_all_cash,
                                         validate_from=min(str(day), current.date),
                                         extra_keys=self._affected_owner_keys(current.lines + list(lines),
                                             force_brokerage_cash=current.type == DocType.BUY,
                                             validate_all_cash=validate_all_cash))
            self._refuse_cash_below_zero(lines, day, current)
            updated = replace(
                current, date=fmt_date(day), description=(description or "").strip(),
                counterparty=(counterparty or "").strip(), notes=(notes or "").strip(),
            )
            canonical = self._canonical_counterparty(current.type, updated.counterparty)
            if canonical:
                updated.counterparty = canonical["name"]
            self.repo.update_header(updated, canonical["id"] if canonical else None)
            # Metadata-only saves keep the actual rows and confirmed reserve links (2W).
            # Financial edits still invalidate reserve use through the database trigger.
            if not self._same_posting(current, day, lines):
                old_cleared = self.db.all(
                    "SELECT account_id,asset_id,quantity_e6,effect,category_id,memo,cleared "
                    "FROM ledger_entries WHERE transaction_id=? ORDER BY line_no", (current.id,))
                self.repo.replace_lines(current.id, updated.date, lines)
                if updated.date == current.date and len(old_cleared) == len(lines):
                    new_rows = self.db.all(
                        "SELECT id,account_id,asset_id,quantity_e6,effect,category_id,memo "
                        "FROM ledger_entries WHERE transaction_id=? ORDER BY line_no", (current.id,))
                    for old, new in zip(old_cleared, new_rows):
                        same_posting = all(old[key] == new[key] for key in
                                           ("account_id", "asset_id", "quantity_e6", "effect", "category_id", "memo"))
                        if same_posting and old["cleared"]:
                            self.db.execute("UPDATE ledger_entries SET cleared=1 WHERE id=?", (new["id"],))
            self._check_holdings(list(current.lines) + list(lines))
            after = self.get(current.id)
            self.audit.record("transaction", current.id, "edit", f"Edited {current.ref}",
                              before=self._snapshot(current), after=self._snapshot(after))
        return after

    # Investment documents keep the name typed on them; every other one names a saved counterparty.
    _INVESTMENT_NAMED = {DocType.BUY, DocType.SEL, DocType.DIV, DocType.OPN}

    def _canonical_counterparty(self, doc_type: DocType, name: str):
        """The saved counterparty a new or edited document names, created when the name is new (None if none)."""
        if doc_type in self._INVESTMENT_NAMED or not name:
            return None
        canonical = self.counterparties.resolve(name)
        if not canonical:
            if self.counterparties.suggestions(name):
                raise ValidationError("This Counterparty resembles a saved one. Confirm reuse or explicitly create it.",
                                      "counterparty")
            canonical = self.counterparties.get(self.counterparties.create(name))
        return canonical

    def _editable(self, txn_id: int, allowed: set[DocType]) -> Transaction:
        t = self.get(txn_id)
        if t.is_void:
            raise ValidationError("Restore this transaction before editing it.")
        if t.type not in allowed:
            if t.type == DocType.OPN:
                raise ValidationError("Change an opening balance from the account's edit page.")
            raise ValidationError(f"{t.type_label} transactions cannot be edited here.")
        return t

    def check_reserve_links(self, txn_ids) -> None:
        """A reserve never pays out more than was assigned to it, also after a restore or an undo brings back an
        expense that was linked to it while another one took its place (audit 2026-10-26)."""
        marks = ",".join("?" * len(txn_ids))
        over = self.db.one(
            f"SELECT r.name FROM cash_reserves r WHERE r.id IN (SELECT reserve_id FROM reserve_transaction_links "
            f"WHERE transaction_id IN ({marks})) AND r.allocated_e6 < (SELECT COALESCE(SUM(l.amount_e6),0) "
            f"FROM reserve_transaction_links l JOIN transactions t ON t.id=l.transaction_id "
            f"WHERE l.reserve_id=r.id AND t.status='POSTED') LIMIT 1", tuple(txn_ids)) if txn_ids else None
        if over is not None:
            raise ValidationError(f"This would spend more from the reserve {over['name']} than is assigned to it. "
                                  "Assign more cash to it, or unlink a payment, first.")

    def _check_line_identity(self, lines) -> None:
        """Every writer, built-in or not, must agree with master data (2I): a line is cash exactly when its asset
        is, cash sits only in an account of its own currency, and profile-currency cash moves at a rate of 1."""
        for i, line in enumerate(lines, start=1):
            if not isinstance(line, PostingLine):
                continue  # Stored lines kept as they are by a metadata-only save.
            asset = self.assets.get_asset(line.asset_id)
            if line.effect != Effect.REVALUATION and line.is_cash != asset.is_cash:
                raise ValidationError(f"Line {i}: {asset.name} is {'' if asset.is_cash else 'not '}cash.")
            if not asset.is_cash:
                continue
            account = self.accounts.get(line.account_id)
            if asset.currency != account.currency:
                raise ValidationError(
                    f"Line {i}: {account.label} holds {account.currency}, not {asset.currency} cash.", "currency")
            if asset.currency == self.base_currency and line.fx_rate != ONE:
                raise ValidationError(f"Line {i}: {asset.currency} cash moves at a rate of 1.", "fx_rate")

    def _check_holdings(self, lines) -> None:
        """No holding may ever go below zero units (you cannot sell or remove what you did not have)."""
        for account_id, asset_id in {(ln.account_id, ln.asset_id) for ln in lines}:
            asset = self.assets.get_asset(asset_id)
            if asset.is_cash:
                continue
            lowest, on = self.repo.lowest_running_quantity(account_id, asset_id)
            if lowest < 0:
                account = self.accounts.get(account_id)
                raise ValidationError(
                    f"{account.label} would hold less than zero {asset.name} on {on}. "
                    "Check the quantities and dates of buys and sells.", "quantity")
        self._check_circles({ln.account_id for ln in lines})

    def _check_circles(self, account_ids) -> None:
        """A gam'eya takes at most one instalment per member and pays you once, however the transfer was entered
        or brought back (restore, undo, the register; audit 2026-10-26). Counted as the circle's own screen counts."""
        for account_id in account_ids:
            terms = self.db.one("SELECT members FROM gameya_terms WHERE account_id=?", (account_id,))
            if terms is None:
                continue
            counts = self.db.one(
                "SELECT COALESCE(SUM(le.quantity_e6>0),0) AS paid, COALESCE(SUM(le.quantity_e6<0),0) AS payouts "
                "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED' "
                "AND t.type='TRF' JOIN financial_assets fa ON fa.id=le.asset_id AND fa.is_cash=1 "
                "WHERE le.account_id=? AND le.owner_id IS NULL AND le.effect='INTERNAL'", (account_id,))
            label = self.accounts.get(account_id).label
            if counts["paid"] > terms["members"]:
                raise ValidationError(f"{label} has {terms['members']} members: all its instalments are recorded.")
            if counts["payouts"] > 1:
                raise ValidationError(f"{label} has already paid you its pot.")

    def _check_date(self, date: str):
        day = parse_date(date)
        if day > today():
            raise ValidationError(
                f"{fmt_date(day)} is in the future. Record transactions on or after the day they happen.", "date")
        return day

    @staticmethod
    def _amount_or_zero(amount, places: int) -> Decimal:
        value = check_places(to_decimal(amount, "fee"), places)
        if value < ZERO:
            raise ValidationError("A fee cannot be negative.", "fee")
        return value

    @staticmethod
    def _positive_amount(amount, places: int) -> Decimal:
        value = check_places(to_decimal(amount), places)
        if value <= ZERO:
            raise ValidationError("Enter an amount greater than zero.", "amount")
        return value

    def _fx(self, account: Account, day) -> Decimal:
        return self._rate(account.currency, day)

    def _rate(self, currency: str, day) -> Decimal:
        """The profile-currency value of one unit of `currency`: the one lookup in lightning/fx.py."""
        if currency == self.base_currency:
            return ONE
        found = rate_for(self.db, currency, self.base_currency, fmt_date(parse_date(day)))
        if not found:
            raise ValidationError(
                f"No {currency}/{self.base_currency} exchange rate within {MISSING_DAYS} days before "
                f"{fmt_date(parse_date(day))}. Add a dated rate before recording this amount.",
                "currency",
            )
        return found.rate

    @staticmethod
    def _snapshot(t: Transaction) -> dict:
        return asdict(t)
