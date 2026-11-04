"""Post or link one reviewed bank-import row inside its caller's transaction."""
from __future__ import annotations

from decimal import Decimal

from lightning.bank_import_rows import _amount, _date, _decimal_amount
from lightning.categories.domain import Movement
from lightning.core.errors import ValidationError
from lightning.transactions.domain import TxnSource


class ImportPoster:
    def __init__(self, db, accounts, categories, counterparties, transactions, money_from_others, reserves, rules):
        self.db, self.accounts, self.categories = db, accounts, categories
        self.counterparties, self.transactions = counterparties, transactions
        self.money_from_others, self.reserves, self.rules = money_from_others, reserves, rules

    def _create_once(self, name: str, alias: str | None = None, kind: str | None = None) -> int:
        """A counterparty typed as new on several rows is created once per batch; a name that already exists is used."""
        name = " ".join(str(name).split())
        key = name.casefold()
        created = getattr(self, "_created_in_batch", {})
        pending = getattr(self, "_pending_created", {})
        if key in created:
            return created[key]
        if key in pending:
            return pending[key]
        if kind == "PERSON":
            return self.counterparties.ensure_person(name)
        existing = self.counterparties.resolve(name)
        if existing:
            return existing["id"]
        use_alias = alias if alias and not self.counterparties.resolve(alias) else None
        new_id = self.counterparties.create(name, alias=use_alias)
        pending[key] = new_id
        self._pending_created = pending
        return new_id

    def _transfer_fee(self, row, decision, amount: Decimal) -> Decimal:
        """The part of a money-out transfer row that is the bank's fee (0 when none is entered). The row's amount
        is the whole debit; the fee is inside it, so the transfer carries amount minus fee."""
        text = str(decision.get("fee") or "").strip()
        if not text:
            return Decimal(0)
        if amount >= 0:
            raise ValidationError(f"CSV row {row['_line']}: a fee can only be split from money going out.", "fee")
        try:
            fee = _decimal_amount(text)
        except ValueError as exc:
            raise ValidationError(f"CSV row {row['_line']}: fee: {exc}", "fee") from None
        if fee == 0:
            return Decimal(0)
        if fee < 0 or fee >= abs(amount):
            raise ValidationError(f"CSV row {row['_line']}: the fee must be more than zero and less than the "
                                  "amount, so something is left to transfer.", "fee")
        return fee

    def _fee_category(self, decision) -> int:
        """The fee's category: the one picked beside the row's fee, else Fees & Charges."""
        chosen = str(decision.get("fee_category_id") or "").strip()
        if chosen:
            category = self.categories.get(int(chosen))
            self.categories.require(category.id, Movement.OUTFLOW)
            return category.id
        return self.categories.repo.get_by_code("EXP.PERSONAL.FEES").id

    def _held_for(self, row, decision, category, canonical, cp_text, similar, is_transfer):
        """Whose money this row moves: (owner name or None for your own money, id of a counterparty made for it).
        Held for works on any row, the way the register's does: an inflow is money you hold for them, an outflow is
        paid out of their money, a transfer moves their custody with it. The custody category with no Held for
        keeps its old fallbacks (the counterparty on the row owns it)."""
        selfish = {"self", "me", "my money", "my own money"}
        choice = str(decision.get("owner_choice", ""))
        typed = str(decision.get("whom", "")).strip()
        line = row["_line"]
        if choice == "self" or (not choice and typed.casefold() in selfish):
            return None, None
        if choice.startswith("existing:"):
            party = self.counterparties.get(int(choice.split(":", 1)[1]))
            if not party or not party["active"]:
                raise ValidationError(f"CSV row {line}: choose an active owner.", "whom")
            self.counterparties.ensure_person(party["name"])
            return party["name"], None
        if choice.startswith("new:") and choice[4:].strip():
            new_id = self._create_once(choice[4:], kind="PERSON")
            return self.counterparties.get(new_id)["name"], new_id
        if typed:
            party = self.counterparties.get(self.counterparties.ensure_person(typed))
            if not party["active"]:
                raise ValidationError(f"CSV row {line}: choose a saved active Counterparty in Whom.", "whom")
            return party["name"], None
        if not (category and category.code == "EXP.SYSTEM.CUSTODY"):
            return None, None
        if canonical and canonical["active"]:
            self.counterparties.ensure_person(canonical["name"])
            return canonical["name"], None
        if not is_transfer and cp_text and not similar:
            # The person named on the row owns it; a name that is new and like no other is saved.
            new_id = self._create_once(cp_text, kind="PERSON")
            return self.counterparties.get(new_id)["name"], new_id
        raise ValidationError(f"CSV row {line}: choose who owns this money.", "whom")

    def _link_import_row(self, row_id, row, match: str) -> None:
        """Stand this statement row behind a transaction already recorded. No money moves and the
        transaction keeps its own date, amount and category."""
        try:
            txn_id = int(match.split(":", 1)[1])
        except ValueError:
            raise ValidationError(f"CSV row {row['_line']}: choose an entry to link to.", "match") from None
        if txn_id not in {c["id"] for c in row["_link_candidates"]}:
            raise ValidationError(f"CSV row {row['_line']}: that entry no longer matches this row; "
                                  "choose again or post it as new.", "match")
        if self.db.scalar("SELECT 1 FROM bank_import_rows WHERE transaction_id=? AND account_id=? "
                          "AND batch_id=(SELECT batch_id FROM bank_import_rows WHERE id=?) "
                          "AND status IN ('POSTED','LINKED')", (txn_id, row["_account_id"], row_id)):
            raise ValidationError(f"CSV row {row['_line']}: another statement row is already linked to that "
                                  "entry in this import. Post this one as new if it is a second payment.", "match")
        self.db.execute("UPDATE bank_import_rows SET status='LINKED',transaction_id=? WHERE id=?",
                        (txn_id, row_id))

    def _post_import_row(self, batch, row_id, decision, row, accounts):
        cp_text = str(decision.get("counterparty", row["Counterparty"])).strip()
        try:
            day = _date(str(decision.get("date", row["Date"])))
            amount = Decimal(_amount(str(decision.get("amount", row["Amount"]))))
        except ValueError as exc:
            raise ValidationError(f"CSV row {row['_line']}: {exc}", "row") from None
        notes = str(decision.get("notes", row["Notes"])).strip()
        account_matches = [a for a in accounts if a.name.casefold() == cp_text.casefold()]
        if len(account_matches) > 1:
            raise ValidationError(f"CSV row {row['_line']}: account name is ambiguous; use a unique name.",
                                  "counterparty")
        target = account_matches[0] if account_matches else None
        if "transfer_account_id" not in decision and row.get("_transfer_account_id"):
            decision = decision | {"transfer_account_id": row["_transfer_account_id"]}
        selected_target = str(decision.get("transfer_account_id", "")).strip()
        if row.get("_internal") and not target and not selected_target:
            raise ValidationError(f"CSV row {row['_line']}: this is an internal transfer. Pick the account the money "
                                  "moved to or from.", "transfer_account_id")
        if selected_target:
            source_currency = self.accounts.get(batch["account_id"]).currency
            target = next((a for a in accounts if str(a.id) == selected_target and a.id != batch["account_id"]
                           and a.currency == source_currency), None)
            if target is None:
                raise ValidationError(f"CSV row {row['_line']}: choose another active account for this transfer.", "transfer_account_id")
        counterparty_id = decision.get("counterparty_id") or (row["_counterparty_id"] if cp_text == row["Counterparty"] else None)
        if cp_text and not counterparty_id:
            exact = self.counterparties.resolve(cp_text)
            counterparty_id = exact["id"] if exact else None
        similar = self.counterparties.suggestions(cp_text) if cp_text and not counterparty_id else []
        choice = str(decision.get("counterparty_choice", ""))
        alias_text = str(decision.get("alias_text") or "").strip()  # the statement's own spelling, when the name was picked
        if choice.startswith("existing:"):
            counterparty_id = int(choice.split(":", 1)[1])
        elif choice == "unlinked":
            counterparty_id = None
        elif choice == "typed":
            pass  # the typed text is kept as written: linked only when it is exactly a saved name
        elif choice == "new":
            name = str(decision.get("new_counterparty", cp_text)).strip()
            if name:
                counterparty_id = self._create_once(name, alias_text or cp_text)
        elif row.get("_suggestions") and not row.get("_counterparty_id") and not choice:
            raise ValidationError(f"CSV row {row['_line']}: choose a Counterparty match or leave it unlinked.",
                                  "counterparty")
        if counterparty_id and not target:
            if alias_text:
                if not self.counterparties.resolve(alias_text):
                    self.counterparties.add_alias(int(counterparty_id), alias_text)
            elif cp_text:
                self.counterparties.add_alias(int(counterparty_id), cp_text)
        category_id = None if decision.get("force_uncategorized") else (decision.get("category_id") or row["_category_id"])
        if category_id:
            category_id = int(category_id)
        else:
            fallback_code = "EXP.UNACCOUNTED" if amount < 0 else "INC.UNACCOUNTED"
            category_id = self.categories.repo.get_by_code(fallback_code).id
        if decision.get("remember_category") and counterparty_id and category_id:
            self.counterparties.set_default_category(int(counterparty_id), int(category_id))
        canonical = self.counterparties.get(int(counterparty_id)) if counterparty_id else None
        if target:
            fee = self._transfer_fee(row, decision, amount)
            txn = self.transactions.record_transfer(
                day, batch["account_id"] if amount < 0 else target.id,
                target.id if amount < 0 else batch["account_id"], abs(amount) - fee,
                notes=notes, source=TxnSource.IMPORT,
            )
            if fee:
                # The bank took the fee out of the same debit: it is its own expense, so the transfer shows
                # what arrived and the fee shows in reports.
                self.transactions.record_outflow(
                    day, batch["account_id"], fee, self._fee_category(decision), notes=notes,
                    source=TxnSource.IMPORT)
            category = self.categories.get(int(category_id)) if category_id else None
            if self.money_from_others:
                owner, _ = self._held_for(row, decision, category, canonical, cp_text, similar, True)
                if owner:
                    source_id, target_id = ((batch["account_id"], target.id) if amount < 0
                                            else (target.id, batch["account_id"]))
                    self.money_from_others.sync_transfer(txn.id, day, owner, source_id, target_id,
                                                        abs(amount) - fee, notes)
        else:
            movement = Movement.OUTFLOW if amount < 0 else Movement.INFLOW
            self.categories.require(int(category_id), movement, allow_system=True)
            category = self.categories.get(int(category_id))
            owner, owner_id = self._held_for(row, decision, category, canonical, cp_text, similar, False)
            if owner_id:
                counterparty_id = counterparty_id or owner_id
            if owner and amount > 0 and category.code != "EXP.SYSTEM.CUSTODY":
                # Money in that you hold for someone is custody, whatever category the row had.
                category = self.categories.repo.get_by_code("EXP.SYSTEM.CUSTODY")
                category_id = category.id
                self.categories.require(int(category_id), movement, allow_system=True)
            linked_name = canonical["name"] if canonical else (
                "" if (similar and choice != "typed") or choice == "unlinked" else cp_text)
            kwargs = {"source": TxnSource.IMPORT, "counterparty": linked_name, "notes": notes}
            if amount < 0:
                txn = self.transactions.record_outflow(day, batch["account_id"], abs(amount), int(category_id),
                                                      allow_system_category=True, **kwargs)
                # A rule's split, while the row keeps the rule's category; the parts follow an edited amount.
                parts = (self.rules.split_for(row.get("_rule_id"), abs(amount))
                         if self.rules and not owner and int(category_id) == row.get("_category_id") else None)
                if parts:
                    txn = self.transactions.update_expense_split(txn.id, parts)
            elif category.movement == Movement.OUTFLOW:
                txn = self.transactions.record_refund(day, batch["account_id"], amount, int(category_id), **kwargs)
            else:
                txn = self.transactions.record_inflow(day, batch["account_id"], amount, int(category_id),
                                                     allow_system_category=True, **kwargs)
            if owner and self.money_from_others:
                self.money_from_others.sync_transaction(txn.id, txn.date, owner, batch["account_id"], amount, notes)
            if counterparty_id:
                self.db.execute("UPDATE transactions SET counterparty_id=? WHERE id=?",
                                (int(counterparty_id), txn.id))
        self.db.execute("UPDATE bank_import_rows SET status='POSTED',transaction_id=? WHERE id=?",
                        (txn.id, row_id))
        if self.reserves:
            return self.reserves.auto_link_transaction(txn.id)
        return 0

