"""Reviewed, idempotent bank CSV imports into the transaction ledger."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from lightning.core.dates import now_iso
from lightning.core.errors import ConflictError, LightningError, NotFoundError, ValidationError
from lightning.core.money import from_e6

# Re-export the original helpers for the UI, journal capture and existing callers.
from lightning.bank_import_rows import (INTERNAL_WORDS as INTERNAL_WORDS, MAX_BYTES as MAX_BYTES, OPTIONAL, REQUIRED, SEPARATE_AMOUNT_FIELDS, direction_sign,
                                          _amount as _amount, _date as _date, _decimal_amount as _decimal_amount,
                                          _separate_amount as _separate_amount, decode_csv, is_internal as is_internal)
from lightning.bank_import_proposals import ImportProposals, LINK_WINDOW_DAYS as LINK_WINDOW_DAYS
from lightning.bank_import_posting import ImportPoster
from lightning.bank_import_parsing import normalize_rows


class _ImportReviewRequired(Exception):
    """Abort the whole import while returning row-level validation errors."""

    def __init__(self, errors):
        self.errors = errors


class BankImportService:
    def __init__(self, db, accounts, categories, counterparties, transactions, money_from_others=None, reserves=None,
                 rules=None):
        self.db, self.accounts, self.categories = db, accounts, categories
        self.counterparties, self.transactions = counterparties, transactions
        self.money_from_others = money_from_others
        self.reserves = reserves
        self.rules = rules
        self._proposals = ImportProposals(db, accounts, categories, counterparties, transactions, rules)
        self._poster = ImportPoster(db, accounts, categories, counterparties, transactions, money_from_others, reserves, rules)

    def first_pending_review(self):
        """Earliest staged import row still requiring a decision."""
        return self.db.one(
            "SELECT r.id,r.batch_id,r.row_number,r.raw_json,b.account_id,b.file_name,b.created_at "
            "FROM bank_import_rows r JOIN bank_import_batches b ON b.id=r.batch_id "
            "WHERE r.status='REVIEW' ORDER BY r.id LIMIT 1"
        )

    def history(self, limit: int = 20) -> list[dict]:
        """Recent statements, newest first, with how many entries each one created that are still posted."""
        return [dict(r) for r in self.db.all(
            "SELECT b.id, b.account_id, b.file_name, b.status, b.created_at, b.posted_at, a.name AS account,"
            " (SELECT COUNT(*) FROM bank_import_rows r JOIN transactions t ON t.id=r.transaction_id"
            "  WHERE r.batch_id=b.id AND r.status='POSTED' AND t.source='IMPORT' AND t.status='POSTED') AS live"
            " FROM bank_import_batches b JOIN accounts a ON a.id=b.account_id ORDER BY b.id DESC LIMIT ?", (limit,))]

    def has_posted_import(self, account_id: int) -> bool:
        """True once a statement into this account has been posted: later imports are not the first one."""
        return bool(self.db.one("SELECT 1 FROM bank_import_batches WHERE account_id=? AND status='POSTED' LIMIT 1", (account_id,)))

    def source_header(self, batch_id: int) -> list[str]:
        """The statement's own column names, as the file had them (names only, never a row's values)."""
        row = self.db.one("SELECT raw_json FROM bank_import_rows WHERE batch_id=? ORDER BY row_number LIMIT 1", (batch_id,))
        return [key for key in json.loads(row["raw_json"])["raw"] if key != "__line__"] if row else []

    def created_transactions(self, batch_id: int) -> list[int]:
        """The entries a statement created (not the ones it only linked to), still in the books: what undo removes."""
        return [int(r["transaction_id"]) for r in self.db.all(
            "SELECT r.transaction_id FROM bank_import_rows r JOIN transactions t ON t.id=r.transaction_id"
            " WHERE r.batch_id=? AND r.status='POSTED' AND t.source='IMPORT' AND t.status='POSTED'", (batch_id,))]

    def waiting_all(self) -> list[dict]:
        """Every statement with rows still waiting for a decision, oldest first, with its first waiting row."""
        return [dict(row) for row in self.db.all(
            "SELECT w.*,f.row_number AS first_row_number,f.raw_json AS first_raw_json FROM ("
            "SELECT b.id AS batch_id,b.account_id,b.file_name,b.created_at,COUNT(r.id) AS waiting,"
            "MIN(r.id) AS first_row_id FROM bank_import_batches b "
            "JOIN bank_import_rows r ON r.batch_id=b.id AND r.status='REVIEW' GROUP BY b.id) w "
            "JOIN bank_import_rows f ON f.id=w.first_row_id ORDER BY w.first_row_id")]

    def suggested_mapping(self, account_id: int, headers: list[str], rows: list[dict] | None = None) -> dict[str, str]:
        """Return saved or best-effort column matches for the reviewable map step."""
        saved = self.saved_mapping(account_id, headers)
        if saved:
            return saved
        normalized = {header: " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in header).split())
                      for header in headers}
        aliases = {
            "Date": ("date", "transaction date", "posting date", "booking date", "value date"),
            "Amount": ("amount", "transaction amount", "net amount", "value"),
            "Inflow": ("inflow", "money in", "credit", "credits", "deposit", "deposits"),
            "Outflow": ("outflow", "money out", "debit", "debits", "withdrawal", "withdrawals"),
            "Counterparty": ("counterparty", "merchant", "payee", "beneficiary", "party", "name"),
            "Category": ("category", "subcategory", "sub category"),
            "Direction": ("direction", "dr cr", "cr dr", "debit credit", "credit debit", "in out", "income expense",
                          "expense income", "transaction type", "type of transaction", "dr or cr", "debit or credit"),
            "Group": ("category group", "group", "parent category", "main category", "master category",
                      "category parent"),
            "Currency": ("currency", "currency code", "ccy", "cur"),
            "Notes": ("notes", "memo", "narrative", "details", "description"),
            "Reference": ("reference", "ref", "transaction id", "transaction reference"),
        }
        result = {}
        for target, names in aliases.items():
            found = next((header for header, name in normalized.items() if name in names), None)
            if found:
                result[target] = found
        if "Direction" not in result and rows:
            # A bare "Type" column is a direction only when every value in it says money in or out.
            for header in headers:
                if normalized[header] == "type" and header not in result.values():
                    values = {row.get(header, "") for row in rows if row.get(header, "")}
                    try:
                        if values and all(direction_sign(v) for v in values):
                            result["Direction"] = header
                    except ValueError:
                        pass
        if "Amount" in result:
            result["amount_model"] = "SINGLE"
        elif "Inflow" in result and "Outflow" in result and result["Inflow"] != result["Outflow"]:
            result["amount_model"] = "SEPARATE"
        else:
            result["amount_model"] = "SINGLE"
        return result

    def saved_mapping(self, account_id: int, headers: list[str]) -> dict[str, str] | None:
        """Return a prior user-confirmed mapping for these exact headers, if available."""
        signature = hashlib.sha256(json.dumps(headers, ensure_ascii=False).encode()).hexdigest()
        saved = self.db.one("SELECT mapping_json,invert_amount FROM bank_import_column_maps WHERE account_id=? AND header_signature=?",
                            (account_id, signature))
        if not saved:
            institution = (self.accounts.get(account_id).institution or "").strip().casefold()
            if not institution:
                return None
            # Reuse actual confirmed bank columns, never a guessed bank-specific format. Conflicting
            # interpretations of the same headers must return to the mapping step.
            candidates = [row for row in self.db.all(
                "SELECT m.mapping_json,m.invert_amount,a.institution FROM bank_import_column_maps m "
                "JOIN accounts a ON a.id=m.account_id WHERE m.header_signature=?", (signature,))
                if (row["institution"] or "").strip().casefold() == institution]
            distinct = {(row["mapping_json"], row["invert_amount"]) for row in candidates}
            if len(distinct) != 1:
                return None
            mapping_json, invert_amount = next(iter(distinct))
            return json.loads(mapping_json) | {"amount_sign": "invert" if invert_amount else "normal"}
        return json.loads(saved["mapping_json"]) | {"amount_sign": "invert" if saved["invert_amount"] else "normal"}

    def stage(self, account_id: int, filename: str, data: bytes, mapping: dict[str, str] | None = None, invert_amount: bool = False):
        self.accounts.require_usable(account_id)
        digest = hashlib.sha256(data).hexdigest()
        attempts = self.db.all("SELECT id,status,file_hash FROM bank_import_batches WHERE account_id=? "
                               "AND (file_hash=? OR file_hash LIKE ?) ORDER BY id DESC",
                               (account_id, digest, digest + "#%"))
        file_hash = digest
        if attempts:
            old = attempts[0]
            if old["status"] == "REVIEW":
                file_hash = old["file_hash"]
            else:
                # Preserve every posted import attempt, but let an intentional
                # re-upload go through review again (including duplicate flags).
                file_hash = f"{digest}#{len(attempts) + 1}"
            if old["status"] == "REVIEW":
                with self.db.transaction():
                    self.db.execute("DELETE FROM bank_import_rows WHERE batch_id=?", (old["id"],))
                    self.db.execute("DELETE FROM bank_import_batches WHERE id=?", (old["id"],))
        headers, raw_rows = decode_csv(data)
        header_signature = hashlib.sha256(json.dumps(headers, ensure_ascii=False).encode()).hexdigest()
        saved = self.db.one("SELECT mapping_json,invert_amount FROM bank_import_column_maps WHERE account_id=? AND header_signature=?",
                            (account_id, header_signature))
        if mapping is None and saved:
            mapping = json.loads(saved["mapping_json"])
        if mapping is None:
            if all(key in headers for key in SEPARATE_AMOUNT_FIELDS) and "Amount" not in headers:
                mapping = {"amount_model": "SEPARATE", "Date": "Date", "Inflow": "Inflow", "Outflow": "Outflow"}
            else:
                mapping = {"amount_model": "SINGLE"} | {key: key for key in (*REQUIRED, *OPTIONAL) if key in headers}
        amount_model = str(mapping.get("amount_model") or
                           ("SEPARATE" if any(mapping.get(key) for key in SEPARATE_AMOUNT_FIELDS) else "SINGLE"))
        if amount_model not in {"SINGLE", "SEPARATE"}:
            raise ValidationError("Choose one amount column or separate inflow/outflow columns.", "mapping")
        missing = [key for key in (("Date", *SEPARATE_AMOUNT_FIELDS) if amount_model == "SEPARATE" else REQUIRED)
                   if mapping.get(key) not in headers]
        if amount_model == "SEPARATE" and mapping.get("Inflow") == mapping.get("Outflow"):
            missing.append("different inflow and outflow columns")
        if missing:
            raise ValidationError(
                "Map Date and either a signed Amount column or two different columns for Inflow and Outflow.", "mapping")
        stored = normalize_rows(raw_rows, mapping, amount_model, invert_amount, self.accounts.get(account_id).currency)
        now = now_iso()
        with self.db.transaction():
            canonical_fields = ("Date", *SEPARATE_AMOUNT_FIELDS, *OPTIONAL) if amount_model == "SEPARATE" else (*REQUIRED, *OPTIONAL)
            if mapping and (saved is not None or amount_model == "SEPARATE"
                            or any(mapping.get(key) != key for key in canonical_fields if mapping.get(key)) or invert_amount):
                self.db.execute("INSERT INTO bank_import_column_maps(account_id,header_signature,mapping_json,invert_amount,created_at,updated_at) "
                                "VALUES (?,?,?,?,?,?) ON CONFLICT(account_id,header_signature) DO UPDATE SET "
                                "mapping_json=excluded.mapping_json,invert_amount=excluded.invert_amount,updated_at=excluded.updated_at",
                                (account_id, header_signature, json.dumps(mapping | {"amount_model": amount_model}),
                                 int(invert_amount), now, now))
            cur = self.db.execute(
                "INSERT INTO bank_import_batches(account_id,file_hash,file_name,status,created_at) "
                "VALUES (?,?,?,'REVIEW',?)", (account_id, file_hash, filename[:255], now)
            )
            batch_id = int(cur.lastrowid)
            for raw, parsed in stored:
                ref = parsed["Reference"].strip() or None
                self.db.execute(
                    "INSERT INTO bank_import_rows(batch_id,account_id,row_number,raw_json,bank_reference,status) "
                    "VALUES (?,?,?,?,?,?)", (batch_id, account_id, int(raw["__line__"]),
                    json.dumps({"raw": raw, "parsed": parsed}, ensure_ascii=False), ref, "REVIEW")
                )
        return batch_id, False

    def preview(self, batch_id: int):
        return self._proposals.preview(batch_id)

    def _category_for(self, parsed, counterparty, outcome=None, usual=None):
        return self._proposals._category_for(parsed, counterparty, outcome, usual)

    def waiting(self, account_id: int) -> list[dict]:
        """Statements this account left half-reviewed, oldest first: Import CSV offers to finish or
        discard them before another one starts."""
        return [dict(row) for row in self.db.all(
            "SELECT b.id,b.file_name,b.created_at,COUNT(r.id) AS waiting FROM bank_import_batches b "
            "JOIN bank_import_rows r ON r.batch_id=b.id AND r.status='REVIEW' "
            "WHERE b.account_id=? AND b.status='REVIEW' GROUP BY b.id ORDER BY b.id", (account_id,))]

    def discard(self, batch_id: int) -> int:
        """Throw away a statement still in review. Rows already posted stay posted; the rest are
        marked skipped, or the whole batch is removed when nothing from it was posted. Returns the
        number of rows discarded."""
        batch = self.db.one("SELECT * FROM bank_import_batches WHERE id=?", (batch_id,))
        if not batch:
            raise NotFoundError("Import batch not found.")
        if batch["status"] == "POSTED":
            raise ConflictError("This statement has already been posted.")
        waiting = self.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='REVIEW'", (batch_id,))
        posted = self.db.scalar("SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='POSTED'", (batch_id,))
        with self.db.transaction():
            if posted:
                self.db.execute("UPDATE bank_import_rows SET status='SKIPPED' WHERE batch_id=? AND status='REVIEW'", (batch_id,))
                self.db.execute("UPDATE bank_import_batches SET status='POSTED',posted_at=? WHERE id=?", (now_iso(), batch_id))
            else:
                self.db.execute("DELETE FROM bank_import_rows WHERE batch_id=?", (batch_id,))
                self.db.execute("DELETE FROM bank_import_batches WHERE id=?", (batch_id,))
        return int(waiting or 0)

    def confirm(self, batch_id: int, decisions: dict[int, dict]):
        batch = self.db.one("SELECT * FROM bank_import_batches WHERE id=?", (batch_id,))
        if not batch:
            raise NotFoundError("Import batch not found.")
        if batch["status"] == "POSTED":
            raise ConflictError("This statement has already been posted.")
        _, rows = self.preview(batch_id)
        row_by_id = {r["_import_row_id"]: r for r in rows}
        accounts = self.accounts.list(active_only=True)
        def parsed(item):
            row_id, decision = item
            row = row_by_id.get(int(row_id), {})
            try:
                day = _date(str(decision.get("date", row.get("Date", ""))))
            except ValueError:
                day = "9999-12-31"
            try:
                amount = Decimal(_amount(str(decision.get("amount", row.get("Amount", "0")))))
            except (ValueError, ArithmeticError):
                amount = Decimal(0)
            match = str(decision.get("match") or "")
            posts = not (decision.get("skip") or match == "skip" or match.startswith("link:"))
            return day, int(row.get("_line", 0)), amount if posts else Decimal(0), posts

        # Same-day order: a day whose account balance ends at or above zero posts its inflows first (a newest-first
        # statement lists the day's spending before the salary); a day ending below zero keeps the statement's order.
        items = {int(k): parsed((k, v)) for k, v in decisions.items()}
        day_total: dict[str, Decimal] = {}
        for day, _line, amount, posts in items.values():
            if posts:
                day_total[day] = day_total.get(day, Decimal(0)) + amount
        inflows_first: set[str] = set()
        running = None
        for day in sorted(day_total):
            if running is None:
                running = from_e6(self.db.scalar(
                    "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                    "WHERE le.account_id=? AND le.date<? AND t.status='POSTED' "
                    "AND le.asset_id IN (SELECT id FROM financial_assets WHERE is_cash=1)",
                    (batch["account_id"], day)) or 0)
            running += day_total[day]
            if running >= 0:
                inflows_first.add(day)

        def posting_order(item):
            day, line, amount, _ = items[int(item[0])]
            return day, int(day in inflows_first and amount <= 0), line

        errors = {}
        ambiguous_reserves = 0
        # A merchant typed as new on several rows (salary every month) is
        # created once; later rows in this batch reuse it.
        self._poster._created_in_batch = {}
        try:
            with self.db.transaction():
                # Custody debits depend on earlier credits. Statements often arrive
                # newest-first, so post in date order rather than CSV display order.
                for row_id, decision in sorted(decisions.items(), key=posting_order):
                    row = row_by_id.get(int(row_id))
                    if not row or self.db.scalar("SELECT status FROM bank_import_rows WHERE id=?", (row_id,)) != "REVIEW":
                        continue
                    match = str(decision.get("match") or "")
                    if decision.get("skip") or match == "skip":
                        skip_status = "DUPLICATE" if row["_possible_duplicate"] else "SKIPPED"
                        self.db.execute("UPDATE bank_import_rows SET status=? WHERE id=?", (skip_status, row_id))
                        continue
                    if match.startswith("link:"):
                        try:
                            with self.db.transaction():
                                self._link_import_row(row_id, row, match)
                        except LightningError as exc:
                            errors[int(row_id)] = exc.message
                        continue
                    checked = self.db.scalar("SELECT date FROM reconciled_through WHERE account_id=?", (batch["account_id"],))
                    try:
                        effective_date = _date(str(decision.get("date", row["Date"])))
                    except ValueError:
                        effective_date = None
                    if checked and effective_date and effective_date <= checked:
                        self.db.execute("UPDATE bank_import_rows SET status='SKIPPED' WHERE id=?", (row_id,))
                        continue
                    self._poster._pending_created = {}
                    try:
                        with self.db.transaction():
                            matched = self._post_import_row(batch, row_id, decision, row, accounts)
                            ambiguous_reserves += int(matched < 0)
                        self._poster._created_in_batch.update(self._poster._pending_created)
                    except LightningError as exc:
                        errors[int(row_id)] = exc.message
                if errors:
                    # Validation used temporary postings to check dependent rows;
                    # roll all of them back so this CSV remains completely unposted.
                    raise _ImportReviewRequired(errors)
                remaining = self.db.scalar(
                    "SELECT COUNT(*) FROM bank_import_rows WHERE batch_id=? AND status='REVIEW'", (batch_id,))
                if not remaining:
                    self.db.execute("UPDATE bank_import_batches SET status='POSTED',posted_at=? WHERE id=?",
                                    (now_iso(), batch_id))
        except _ImportReviewRequired as exc:
            errors = exc.errors
        return self.summary(batch_id) | {"errors": errors, "ambiguous_reserves": ambiguous_reserves}

    def _link_import_row(self, row_id, row, match: str) -> None:
        self._poster._link_import_row(row_id, row, match)

    def _post_import_row(self, batch, row_id, decision, row, accounts):
        return self._poster._post_import_row(batch, row_id, decision, row, accounts)

    def summary(self, batch_id: int) -> dict[str, int]:
        counts = {row["status"]: row["n"] for row in self.db.all(
            "SELECT status,COUNT(*) AS n FROM bank_import_rows WHERE batch_id=? GROUP BY status", (batch_id,))}
        return {"posted": counts.get("POSTED", 0), "linked": counts.get("LINKED", 0),
                "skipped": counts.get("SKIPPED", 0), "duplicates": counts.get("DUPLICATE", 0)}
