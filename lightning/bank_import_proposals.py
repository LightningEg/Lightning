"""Build reviewable proposals for staged bank statement rows."""
from __future__ import annotations

import difflib
import functools
import json
import re
from decimal import Decimal

from lightning.bank_import_rows import is_balance_row, is_internal, split_category_path
from lightning.categories.domain import Movement
from lightning.core.errors import NotFoundError, ValidationError
from lightning.transactions.tags import tags_in

# A bank may post a purchase days after the transaction already in the ledger.
LINK_WINDOW_DAYS = 3


class ImportProposals:
    def __init__(self, db, accounts, categories, counterparties, transactions, rules):
        self.db, self.accounts, self.categories = db, accounts, categories
        self.counterparties, self.transactions, self.rules = counterparties, transactions, rules

    def _active(self):
        """The active accounts, read once per preview: they do not change while one is built (IT-7AA8)."""
        if self._accounts_seen is None:
            return self.accounts.list(active_only=True)
        if "active" not in self._accounts_seen:
            self._accounts_seen["active"] = self.accounts.list(active_only=True)
        return self._accounts_seen["active"]

    def _account(self, account_id: int):
        if self._accounts_seen is None:
            return self.accounts.get(account_id)
        key = ("one", account_id)
        if key not in self._accounts_seen:
            self._accounts_seen[key] = self.accounts.get(account_id)
        return self._accounts_seen[key]

    _accounts_seen = None
    _remembered: dict = {}

    def _remembered_names(self, account_id: int) -> dict:
        """IT-7Z1: what the person chose before for a name in this account's files (kept by `remember_names`)."""
        from lightning.database.settings import SettingsStore
        try:
            return {str(k): int(v) for k, v in json.loads(SettingsStore(self.db).get(f"import_names_{account_id}") or "{}").items()}
        except (ValueError, TypeError):
            return {}

    def preview(self, batch_id: int):
        self._accounts_seen = {}
        self._remembered = {}
        try:
            return self._preview(batch_id)
        finally:
            self._accounts_seen = None

    def _preview(self, batch_id: int):
        batch = self.db.one("SELECT * FROM bank_import_batches WHERE id=?", (batch_id,))
        self._remembered = self._remembered_names(batch["account_id"]) if batch else {}
        if not batch:
            raise NotFoundError("Import batch not found.")
        rows = self.db.all("SELECT * FROM bank_import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,))
        result = []
        amount_dates = {}
        for source_row in rows:
            staged = json.loads(source_row["raw_json"])["parsed"]
            if not staged.get("_errors") and not staged.get("_skip_reason"):
                key = (staged["Date"], staged["Amount"])
                amount_dates[key] = amount_dates.get(key, 0) + 1
        # The same date and amount waiting in another review of this account (an SMS and a statement, or two
        # copies of one message): flagged like a posted look-alike, so neither posts twice unnoticed.
        pending_elsewhere = {}
        for other in self.db.all(
                "SELECT r.raw_json, b.file_name FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
                "WHERE b.account_id=? AND b.id<>? AND r.status='REVIEW'", (batch["account_id"], batch_id)):
            try:
                staged = json.loads(other["raw_json"])["parsed"]
                pending_elsewhere.setdefault((staged["Date"], staged["Amount"]), other["file_name"])
            except (TypeError, ValueError, KeyError):
                continue
        active_accounts = self._active()
        pairs = self._paired_rows(rows)
        seen_refs = set()
        # A full-history query: run it at most once per preview, not once per row (7O).
        usual = functools.cache(self.transactions.usual_categories)
        for row in rows:
            record = json.loads(row["raw_json"])
            parsed = record["parsed"]
            raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
            parsed["_message"] = str(raw.get("Message", ""))[:1000]  # a bank SMS row keeps its message (IV-3AU)
            ref_duplicate = bool(row["bank_reference"] and (row["bank_reference"] in seen_refs or self.db.scalar(
                "SELECT 1 FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
                "JOIN transactions t ON t.id=r.transaction_id AND t.status='POSTED' "
                "WHERE b.account_id=? AND r.bank_reference=? AND b.id<>? AND r.status IN ('POSTED','LINKED') LIMIT 1",
                (batch["account_id"], row["bank_reference"], batch_id))))
            file_digest = batch["file_hash"].split("#", 1)[0]
            repeat_import = bool(self.db.scalar(
                "SELECT 1 FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
                "WHERE b.account_id=? AND b.id<>? AND (b.file_hash=? OR b.file_hash LIKE ?) "
                "AND r.row_number=? AND r.status<>'REVIEW' LIMIT 1",
                (batch["account_id"], batch_id, file_digest, file_digest + "#%", row["row_number"])))
            if row["bank_reference"]:
                seen_refs.add(row["bank_reference"])
            cp = self.counterparties.resolve(parsed["Counterparty"])
            parsed["_counterparty_id"] = cp["id"] if cp else None
            parsed["_suggestions"] = self.counterparties.suggestions(parsed["Counterparty"])
            parsed["_reference_duplicate"] = ref_duplicate
            parsed["_repeat_import"] = repeat_import
            parsed["_pending_elsewhere"] = pending_elsewhere.get((parsed.get("Date"), parsed.get("Amount")), "")
            parsed["_similarity_warning"] = (self._similarity_warning(batch["account_id"], parsed)
                or amount_dates.get((parsed["Date"], parsed["Amount"]), 0) > 1 or bool(parsed["_pending_elsewhere"]))
            parsed["_voided_earlier"] = not ref_duplicate and self._voided_earlier(batch["account_id"], batch_id,
                                                                                row["bank_reference"], parsed)
            parsed["_link_candidates"] = ([] if ref_duplicate or repeat_import or row["status"] != "REVIEW"
                                          else self._link_candidates(batch["account_id"], parsed, batch["id"]))
            self._split_path(parsed)
            if row["id"] in pairs and not parsed.get("_skip_reason"):
                parsed["_skip_reason"] = (f"Pairs with line {pairs[row['id']]}: the same movement written twice (opposite "
                                          "amounts, same day). Skipped; untick Skip to post it on its own.")
            parsed["_internal"] = is_internal(parsed["Category"])
            parsed["_balance_row"] = bool(parsed.get("_skip_reason")) or is_balance_row(parsed["Category"], parsed["Counterparty"])
            outcome = self._rules_outcome(batch["account_id"], parsed, cp)
            parsed["_category_id"] = None if parsed["_internal"] else self._category_for(parsed, cp, outcome, usual)
            if parsed.get("_file_split") and not parsed["_internal"]:
                parts = self._file_split_parts(parsed)
                if parts:
                    parsed["_file_split_ids"] = parts
                    parsed["_category_id"] = parts[0][0]
                    parsed["_split_note"] = " · ".join(
                        f"{self.categories.get(cid).name} {format(amount, 'f')}" for cid, amount in parts)
                else:
                    parsed["_category_ambiguous"] = ("Your file splits this purchase, but a part names a category "
                                                     "Lightning does not have.")
                    parsed["_category_id"] = None
            parsed["_transfer_target_suggestion"] = (self._own_account(batch["account_id"], parsed["Counterparty"])
                or self._transfer_target_suggestion(batch["account_id"], parsed["Notes"])
                or self._transfer_target_suggestion(batch["account_id"], parsed["Counterparty"])
                or self._matching_bank_transfer(batch["account_id"], parsed))
            # One of your accounts as the counterparty, or "Internal" in the category, is a transfer.
            # A transfer whose account is known needs no category; one marked internal whose account
            # cannot be matched waits for the user to pick it.
            target = next((a for a in self._active()
                           if a.name == parsed["_transfer_target_suggestion"]), None)
            same_name = [a for a in active_accounts if a.id != batch["account_id"]
                         and a.name.casefold() == parsed["Counterparty"].strip().casefold()]
            parsed["_identity_ambiguous"] = len(same_name) > 1 or bool(same_name and cp)
            if parsed["_identity_ambiguous"]:
                target = None
                parsed["_transfer_target_suggestion"] = None
            is_transfer = parsed["_internal"] or self._own_account(batch["account_id"], parsed["Counterparty"])
            parsed["_transfer_target"] = target.name if target and is_transfer else None
            parsed["_transfer_account_id"] = str(target.id) if target and is_transfer else ""
            parsed["_needs_account"] = parsed["_internal"] and not parsed["_transfer_target"]
            # The file's own category name that matched none of yours: the review sets it once for all its rows.
            group = (parsed.get("Group") or "").strip()
            parsed["_file_label"] = ("" if parsed["_category_id"] or parsed["_internal"] or parsed["_balance_row"]
                                     or parsed["_transfer_target"] or not parsed["Category"].strip()
                                     else f"{group} › {parsed['Category'].strip()}" if group else parsed["Category"].strip())
            if parsed["_transfer_target"]:
                parsed["_suggestions"] = []
            category = self.categories.get(parsed["_category_id"]) if parsed["_category_id"] else None
            parsed["_is_custody"] = bool(category and category.code == "EXP.SYSTEM.CUSTODY")
            # Keep the canonical owner ready in the form: the user may choose
            # the custody category during review rather than in the CSV.
            parsed["_whom"] = cp["name"] if cp and cp["active"] else ""
            parsed["_possible_duplicate"] = bool(ref_duplicate or repeat_import or parsed["_similarity_warning"]
                                                 or parsed["_voided_earlier"] or parsed["_link_candidates"])
            parsed["_ready"] = bool(not parsed.get("_errors") and not parsed["_possible_duplicate"]
                                    and not parsed["_balance_row"]
                                    and not parsed["_suggestions"] and not parsed["_needs_account"] and not parsed["_identity_ambiguous"]
                                    and (parsed["_category_id"] or parsed["_transfer_target"]))
            parsed["_import_row_id"] = row["id"]
            parsed["_account_id"] = batch["account_id"]
            parsed["_status"] = row["status"]
            parsed["_transaction_id"] = row["transaction_id"]
            result.append(parsed)
        claimed = set()
        for parsed in result:
            free = [c for c in parsed["_link_candidates"] if c["id"] not in claimed]
            # A single candidate can be a useful default. When more than one
            # transaction fits, require the reviewer to choose explicitly.
            if len(parsed["_link_candidates"]) == 1 and free and not free[0].get("source_count"):
                parsed["_default_match"] = f"link:{free[0]['id']}"
                claimed.add(free[0]["id"])
            else:
                parsed["_default_match"] = "skip" if parsed["_possible_duplicate"] else "new"
        return batch, result

    def _link_candidates(self, account_id: int, parsed: dict, batch_id: int | None = None) -> list[dict]:
        """Posted transactions this source row may already stand for: the same signed amount on
        this account within LINK_WINDOW_DAYS. Existing source rows from other batches are evidence,
        not a reason to hide the transaction. A transaction can be linked at most once per batch.
        Amount and date only suggest a match; the user confirms it in the review."""
        if parsed.get("_errors"):
            return []
        amount_e6 = int(Decimal(parsed["Amount"]) * 1_000_000)
        rows = self.db.all(
            "SELECT t.id,t.date,t.type,t.counterparty,t.notes, "
            "(SELECT COUNT(*) FROM bank_import_rows r WHERE r.transaction_id=t.id AND r.account_id=? "
            "AND r.status IN ('POSTED','LINKED')) AS source_count, "
            "(SELECT GROUP_CONCAT(DISTINCT b.file_name) FROM bank_import_rows r "
            "JOIN bank_import_batches b ON b.id=r.batch_id WHERE r.transaction_id=t.id AND r.account_id=? "
            "AND r.status IN ('POSTED','LINKED')) AS source_files FROM transactions t "
            "JOIN ledger_entries l ON l.transaction_id=t.id AND l.account_id=? AND (t.type<>'CNV' OR l.owner_id IS NULL) AND l.asset_id IN (SELECT id FROM financial_assets WHERE is_cash=1) "
            "WHERE t.status='POSTED' AND julianday(t.date) BETWEEN julianday(?)-? AND julianday(?)+? "
            "AND (? IS NULL OR NOT EXISTS (SELECT 1 FROM bank_import_rows r "
            "WHERE r.transaction_id=t.id AND r.account_id=? AND r.batch_id=? "
            "AND r.status IN ('POSTED','LINKED'))) "
            "GROUP BY t.id HAVING SUM(l.amount_e6)=? "
            "ORDER BY abs(julianday(t.date)-julianday(?)), t.id",
            (account_id, account_id, account_id, parsed["Date"], LINK_WINDOW_DAYS, parsed["Date"],
             LINK_WINDOW_DAYS, batch_id, account_id, batch_id, amount_e6, parsed["Date"]))
        return [{"id": r["id"], "date": r["date"], "type": r["type"],
                 "counterparty": r["counterparty"] or "", "notes": r["notes"] or "",
                 "amount": parsed["Amount"], "source_count": r["source_count"],
                 "conversion": self._conversion_legs(r["id"]) if r["type"] == "CNV" else "",
                 "source_files": r["source_files"] or ""} for r in rows]

    def _voided_earlier(self, account_id: int, batch_id: int, reference: str | None, parsed: dict) -> bool:
        """An earlier import of this row was voided: importing it again must not quietly bring it back."""
        if parsed.get("_errors"):
            return False
        if reference:
            return bool(self.db.scalar(
                "SELECT 1 FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
                "JOIN transactions t ON t.id=r.transaction_id AND t.status='VOID' "
                "WHERE b.account_id=? AND b.id<>? AND r.bank_reference=? LIMIT 1",
                (account_id, batch_id, reference)))
        amount_e6 = int(Decimal(parsed["Amount"]) * 1_000_000)
        return bool(self.db.scalar(
            "SELECT 1 FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
            "JOIN transactions t ON t.id=r.transaction_id AND t.status='VOID' AND t.date=? "
            "JOIN ledger_entries l ON l.transaction_id=t.id AND l.account_id=b.account_id "
            "WHERE b.account_id=? AND b.id<>? GROUP BY t.id HAVING SUM(l.amount_e6)=? LIMIT 1",
            (parsed["Date"], account_id, batch_id, amount_e6)))

    def _own_account(self, source_account_id: int, name: str):
        """The name of another of your accounts typed as the counterparty, if it is one."""
        wanted = " ".join((name or "").split()).casefold()
        matches = [a.name for a in self._active()
                   if a.id != source_account_id and a.name.casefold() == wanted]
        return matches[0] if len(matches) == 1 else None

    def _transfer_target_suggestion(self, source_account_id: int, notes: str):
        """Suggest an internal destination from an account name or transfer wording."""
        destination = re.search(r"\b(?:transfer(?:red)?|send|sent|payment)\s+(?:to|into)\s+(.+)",
                                notes or "", re.IGNORECASE)

        def compact(value):
            return "".join(character.casefold() for character in value if character.isalnum())

        tokens = re.findall(r"[\w]+", destination.group(1), re.UNICODE) if destination else []
        candidates = []
        source_currency = self._account(source_account_id).currency
        accounts = [account for account in self._active()
                    if account.id != source_account_id and account.currency == source_currency]
        for account in accounts:
            name = compact(account.name)
            if not name:
                continue
            if compact(notes or "") == name:
                candidates.append((1.0, account))
                continue
            score = 0.0
            for start in range(len(tokens)):
                for width in range(1, min(4, len(tokens) - start) + 1):
                    phrase = compact(" ".join(tokens[start:start + width]))
                    if phrase == name:
                        score = 1.0
                    elif min(len(phrase), len(name)) >= 4:
                        score = max(score, difflib.SequenceMatcher(None, phrase, name).ratio())
            if score >= 0.8:
                candidates.append((score, account))
        candidates.sort(key=lambda match: (-match[0], match[1].name.casefold()))
        if not candidates or (len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.08):
            return None
        return candidates[0][1].name

    def _matching_bank_transfer(self, source_account_id: int, parsed: dict):
        """Spot the opposite side already posted in another bank on this date."""
        if parsed.get("_errors"):
            return None
        amount_e6 = int(Decimal(parsed["Amount"]) * 1_000_000)
        rows = self.db.all(
            "SELECT DISTINCT le.account_id FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id "
            "WHERE t.status='POSTED' AND t.type IN ('IN','OUT') AND t.date=? "
            "AND le.account_id<>? AND le.amount_e6=?",
            (parsed["Date"], source_account_id, -amount_e6))
        source_currency = self._account(source_account_id).currency
        bank_ids = {account.id: account.name for account in self._active()
                    if account.account_type.value == "BANK" and account.currency == source_currency}
        matches = {bank_ids[row["account_id"]] for row in rows if row["account_id"] in bank_ids}
        return next(iter(matches)) if len(matches) == 1 else None

    def _rules_outcome(self, account_id, parsed, counterparty):
        """What the user's rules say about a row (Rules with conditions). Their tags go into the row's notes
        now, so the review shows them and the user can remove them; a split is shown and applied on posting."""
        parsed["_rule_id"], parsed["_rule_split"] = None, []
        if self.rules is None or parsed.get("_errors") or parsed["_internal"]:
            return None
        names = [parsed["Counterparty"], counterparty["name"] if counterparty else ""]
        outcome = self.rules.outcome(names, parsed["Notes"], parsed["Amount"], account_id)
        missing = [t for t in outcome.tags if t not in tags_in(parsed["Notes"])]
        if missing:
            parsed["Notes"] = " ".join([parsed["Notes"].strip(), *(f"#{t}" for t in missing)]).strip()
        return outcome

    @staticmethod
    def _paired_rows(rows) -> dict[int, int]:
        """IT-7Z3: a movement another app wrote as two lines ("Ownership to you" and "Ownership from Mama": the same
        day, opposite amounts, the same first word of the note). The later line is offered as skipped, pointing at the
        first, so the movement is posted once. Returns {row id: line of its partner}."""
        seen: dict[tuple, tuple[int, int]] = {}
        out: dict[int, int] = {}
        for source in rows:
            parsed = json.loads(source["raw_json"])["parsed"]
            if parsed.get("_errors") or parsed.get("_skip_reason"):
                continue
            words = re.findall(r"[^\W\d_]+", (parsed.get("Notes") or "").split("|")[0].casefold())
            if not words or words[0] not in {"ownership", "transfer"}:
                continue
            try:
                amount = Decimal(parsed["Amount"])
            except ArithmeticError:
                continue
            key = (parsed["Date"], abs(amount), words[0])
            partner = seen.get(key)
            if partner and partner[0] != (1 if amount > 0 else -1) and source["id"] not in out:
                out[source["id"]] = partner[1]
            elif not partner:
                seen[key] = (1 if amount > 0 else -1, int(parsed.get("_line") or source["row_number"]))
        return out

    def _split_path(self, parsed) -> None:
        """"Personal:Food", "Work > Transportation" in the Category cell are a group and a name (IT-7AA7), unless the
        whole text is already one of your categories ("Bills/Utilities")."""
        text = (parsed.get("Category") or "").strip()
        if not text or (parsed.get("Group") or "").strip():
            return
        group, name = split_category_path(text)
        if not group:
            return
        try:
            self.categories.find_by_text(text)
            return
        except ValidationError as exc:
            if str(exc.message).startswith("Which one"):
                return
        parsed["Group"], parsed["Category"] = group, name

    def _file_split_parts(self, parsed):
        """The parts of a split from the file as (category id, amount), or None when a part names no category."""
        parts = []
        for part in parsed.get("_file_split") or []:
            try:
                text = f"{part['group']} › {part['category']}" if part["group"] else part["category"]
                try:
                    category = self.categories.find_by_text(text)
                except ValidationError:
                    category = self.categories.find_by_text(part["category"])
            except ValidationError:
                return None
            parts.append((category.id, Decimal(part["amount"])))
        return parts or None

    def _category_for(self, parsed, counterparty, outcome=None, usual=None):
        """`usual` returns `transactions.usual_categories()`; a preview passes one that computes it once."""
        if outcome and outcome.category_id:
            category = self.categories.get(outcome.category_id)
            # Money out needs a spending category; money in takes income or, as a refund, spending.
            if category.active and (Decimal(parsed["Amount"]) > 0 or category.movement == Movement.OUTFLOW):
                parsed["_rule_id"] = outcome.rule_id
                if Decimal(parsed["Amount"]) < 0:
                    parsed["_rule_split"] = [
                        {"category": self.categories.get(category_id).name, "amount": format(value, "f")}
                        for category_id, value in self.rules.split_for(outcome.rule_id, parsed["Amount"]) or []]
                return category.id
        group = (parsed.get("Group") or "").strip()
        label = (f"{group} › {parsed['Category'].strip()}" if group else (parsed["Category"] or "").strip()).casefold()
        if label and label in self._remembered:
            try:
                saved = self.categories.get(self._remembered[label])
                if saved.active and (Decimal(parsed["Amount"]) > 0 or saved.movement == Movement.OUTFLOW):
                    return saved.id
            except Exception:  # a category deleted since: the name is asked again
                pass
        if parsed["Category"] and group:
            # The file's own group says which of two same-named categories it means ("Work › Transportation").
            try:
                return self.categories.find_by_text(f"{group} › {parsed['Category']}").id
            except ValidationError:
                pass
        if parsed["Category"]:
            try:
                return self.categories.find_by_text(parsed["Category"]).id
            except ValidationError as exc:
                if str(exc.message).startswith("Which one"):
                    # "Transportation" under Personal and under Work: say so and leave it for the person, never let the
                    # counterparty's history pick one of two same-named categories (owner, 2026-10-30: ids, not names).
                    parsed["_category_ambiguous"] = exc.message
                    return None
        if counterparty and counterparty["default_category_id"]:
            return counterparty["default_category_id"]
        found = (usual or self.transactions.usual_categories)()
        name = counterparty["name"] if counterparty else parsed["Counterparty"]
        return (found.get(name) or {}).get("category_id")

    def _similarity_warning(self, account_id, parsed):
        if parsed["_errors"]:
            return False
        amount = Decimal(parsed["Amount"])
        targets = self.db.all("SELECT id FROM accounts WHERE active=1 AND lower(name)=lower(?)",
                              (parsed["Counterparty"].strip(),))
        target = targets[0] if len(targets) == 1 else None
        if target:
            transfer = self.db.scalar(
                "SELECT 1 FROM transactions t "
                "JOIN ledger_entries mine ON mine.transaction_id=t.id AND mine.account_id=? "
                "JOIN ledger_entries other ON other.transaction_id=t.id AND other.account_id=? "
                "WHERE t.status='POSTED' AND t.type='TRF' AND t.date=? "
                "AND mine.amount_e6=? AND other.amount_e6=? LIMIT 1",
                # The imported row is from this account's point of view. If it
                # is the other side of an existing transfer, its signed amount
                # must match this account's existing ledger line exactly.
                (account_id, target["id"], parsed["Date"], int(amount * 1_000_000), int(-amount * 1_000_000)),
            )
            if transfer:
                return True
        row = self.db.one(
            "SELECT 1 FROM transactions t JOIN ledger_entries l ON l.transaction_id=t.id "
            "WHERE t.status='POSTED' AND t.date=? AND l.account_id=? "
            "AND l.amount_e6=? LIMIT 1",
            (parsed["Date"], account_id, int(amount * 1_000_000)),
        )
        return bool(row)



    def _conversion_legs(self, txn_id):
        from lightning.core.money import from_e6
        rows = self.db.all("SELECT a.name,a.currency,SUM(l.quantity_e6) quantity FROM ledger_entries l "
                           "JOIN accounts a ON a.id=l.account_id JOIN financial_assets f ON f.id=l.asset_id "
                           "WHERE l.transaction_id=? AND l.owner_id IS NULL AND f.is_cash=1 "
                           "GROUP BY a.id ORDER BY a.id", (txn_id,))
        return " · ".join(f"{r['name']}: {from_e6(r['quantity']):f} {r['currency']}" for r in rows)
