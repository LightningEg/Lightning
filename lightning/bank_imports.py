"""Reviewed, idempotent bank CSV imports into the transaction ledger."""

from __future__ import annotations

import csv
import difflib
import functools
import hashlib
import io
import json
import re
from decimal import Decimal, InvalidOperation

from lightning.categories.domain import Movement
from lightning.core.dates import now_iso, parse_date, today
from lightning.core.errors import ConflictError, LightningError, NotFoundError, ValidationError
from lightning.core.limits import MAX_CSV_IMPORT_BYTES
from lightning.core.money import ascii_digits, from_e6
from lightning.core.refs import DocType
from lightning.transactions.domain import TxnSource
from lightning.transactions.tags import tags_in

REQUIRED = ("Date", "Amount")
OPTIONAL = ("Counterparty", "Category", "Notes", "Reference")
SEPARATE_AMOUNT_FIELDS = ("Inflow", "Outflow")
MAX_BYTES = MAX_CSV_IMPORT_BYTES


class _ImportReviewRequired(Exception):
    """Abort the whole import while returning row-level validation errors."""

    def __init__(self, errors):
        self.errors = errors


# A bank often posts a purchase a day or two after it happened: a transaction you
# already recorded this many days either side can stand behind a statement row.
LINK_WINDOW_DAYS = 3

INTERNAL_WORDS = {"internal", "internal transfer", "transfer", "transfers", "own account"}


def is_internal(category: str) -> bool:
    """The Category column says the row moved money between your own accounts."""
    return " ".join((category or "").split()).casefold() in INTERNAL_WORDS


def _date(value: str) -> str:
    try:
        day = parse_date(value)
    except ValidationError as exc:
        raise ValueError(exc.message) from None
    if day > today():  # the same rule as typing it: the review marks the row to fix at once, not when Post fails
        raise ValueError(f"{day.isoformat()} is in the future. Record transactions on or after the day they happen.")
    return day.isoformat()


def _decimal_amount(value: str) -> Decimal:
    try:
        text = ascii_digits((value or "").strip())
        text = text.replace("−", "-").replace("–", "-").replace(" ", "")
        if not text:
            return Decimal("0")
        # Strip a recognized currency wrapper, never arbitrary non-digit text: stripping
        # punctuation would turn .50 into 50 and silently accept values such as 5%.
        currency = r"(?:EGP|USD|EUR|GBP|LE|E£|ج\.?م\.?|[$€£])"
        wrappers = 0

        def strip_currency(text):
            nonlocal wrappers
            text, count = re.subn(rf"^{currency}|{currency}$", "", text, flags=re.IGNORECASE)
            wrappers += count
            if wrappers > 1:
                raise ValueError("Enter a valid number.")
            return text

        text = strip_currency(text)
        negative = False
        if text.startswith("(") and text.endswith(")") and len(text) > 2:
            negative = True
            text = text[1:-1]
        elif text.endswith("-") and len(text) > 1:
            negative = True
            text = text[:-1]
        elif text.startswith(("-", "+")) and len(text) > 1:
            negative = text[0] == "-"
            text = text[1:]
        text = strip_currency(text)
        if not text or "-" in text or "(" in text or ")" in text:
            raise ValueError("Enter a valid number.")
        if not re.fullmatch(r"(?:[0-9][0-9.,]*|[.,][0-9]+)", text):
            raise ValueError("Enter a valid number.")
        if "," in text and ("." not in text or text.rfind(",") > text.rfind(".")):
            tail = text.rsplit(",", 1)[1]
            text = text.replace(".", "").replace(",", ".") if len(tail) == 2 else text.replace(",", "")
        else:
            text = text.replace(",", "")
        amount = Decimal(text)
        if not amount.is_finite():
            raise InvalidOperation
        return -amount if negative else amount
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid number.") from None


def _amount(value: str) -> str:
    amount = _decimal_amount(value)
    if amount == 0:
        raise ValueError("Enter a non-zero amount; use a minus sign for money out.")
    return format(amount, "f")


def _separate_amount(inflow: str, outflow: str) -> str:
    incoming, outgoing = _decimal_amount(inflow), _decimal_amount(outflow)
    if incoming and outgoing:
        raise ValueError("A row cannot have both an inflow and an outflow amount.")
    if not incoming and not outgoing:
        raise ValueError("Enter an amount in either the inflow or outflow column.")
    signed = abs(incoming) if incoming else -abs(outgoing)
    return format(signed, "f")


def decode_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(data) > MAX_BYTES:
        raise ValidationError("CSV files must be 5 MB or smaller.", "file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Save the statement as a UTF-8 CSV file.", "file") from None
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
        reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)
        headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        if not headers or any(not h for h in headers):
            raise ValidationError("The CSV needs a header row with column names.", "file")
        if len(set(headers)) != len(headers):
            raise ValidationError("CSV headers must be unique; rename duplicate columns and try again.", "file")
        rows = []
        for line, row in enumerate(reader, start=2):
            rows.append({h: str(row.get(h, "") or "").strip() for h in headers} | {"__line__": str(line)})
        return headers, rows
    except csv.Error as exc:
        raise ValidationError(f"Could not read this CSV: {exc}", "file") from None


class BankImportService:
    def __init__(self, db, accounts, categories, counterparties, transactions, money_from_others=None, reserves=None,
                 rules=None):
        self.db, self.accounts, self.categories = db, accounts, categories
        self.counterparties, self.transactions = counterparties, transactions
        self.money_from_others = money_from_others
        self.reserves = reserves
        self.rules = rules

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

    def suggested_mapping(self, account_id: int, headers: list[str]) -> dict[str, str]:
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
            "Category": ("category", "type"),
            "Notes": ("notes", "memo", "narrative", "details", "description"),
            "Reference": ("reference", "ref", "transaction id", "transaction reference"),
        }
        result = {}
        for target, names in aliases.items():
            found = next((header for header, name in normalized.items() if name in names), None)
            if found:
                result[target] = found
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
        fields = ("Date", *SEPARATE_AMOUNT_FIELDS, *OPTIONAL) if amount_model == "SEPARATE" else (*REQUIRED, *OPTIONAL)
        missing = [key for key in (("Date", *SEPARATE_AMOUNT_FIELDS) if amount_model == "SEPARATE" else REQUIRED)
                   if mapping.get(key) not in headers]
        if amount_model == "SEPARATE" and mapping.get("Inflow") == mapping.get("Outflow"):
            missing.append("different inflow and outflow columns")
        if missing:
            raise ValidationError(
                "Map Date and either a signed Amount column or two different columns for Inflow and Outflow.", "mapping")
        stored = []
        for raw in raw_rows:
            parsed = {key: raw.get(mapping.get(key, ""), "") for key in fields}
            for key in ("Amount", *SEPARATE_AMOUNT_FIELDS):
                parsed.setdefault(key, "")
            errors = []
            try:
                parsed["Date"] = _date(parsed["Date"])
                parsed["Amount"] = (_separate_amount(parsed["Inflow"], parsed["Outflow"])
                                     if amount_model == "SEPARATE" else _amount(parsed["Amount"]))
                if invert_amount:
                    parsed["Amount"] = format(-Decimal(parsed["Amount"]), "f")
            except ValueError as exc:
                errors.append(str(exc))
            parsed["_line"] = raw["__line__"]
            parsed["_errors"] = errors
            stored.append((raw, parsed))
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
        batch = self.db.one("SELECT * FROM bank_import_batches WHERE id=?", (batch_id,))
        if not batch:
            raise NotFoundError("Import batch not found.")
        rows = self.db.all("SELECT * FROM bank_import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,))
        result = []
        amount_dates = {}
        for source_row in rows:
            staged = json.loads(source_row["raw_json"])["parsed"]
            if not staged.get("_errors"):
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
        seen_refs = set()
        # A full-history query: run it at most once per preview, not once per row (7O).
        usual = functools.cache(self.transactions.usual_categories)
        for row in rows:
            record = json.loads(row["raw_json"])
            parsed = record["parsed"]
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
            parsed["_internal"] = is_internal(parsed["Category"])
            outcome = self._rules_outcome(batch["account_id"], parsed, cp)
            parsed["_category_id"] = None if parsed["_internal"] else self._category_for(parsed, cp, outcome, usual)
            parsed["_transfer_target_suggestion"] = (self._own_account(batch["account_id"], parsed["Counterparty"])
                or self._transfer_target_suggestion(batch["account_id"], parsed["Notes"])
                or self._transfer_target_suggestion(batch["account_id"], parsed["Counterparty"])
                or self._matching_bank_transfer(batch["account_id"], parsed))
            # One of your accounts as the counterparty, or "Internal" in the category, is a transfer.
            # A transfer whose account is known needs no category; one marked internal whose account
            # cannot be matched waits for the user to pick it.
            target = next((a for a in self.accounts.list(active_only=True)
                           if a.name == parsed["_transfer_target_suggestion"]), None)
            is_transfer = parsed["_internal"] or self._own_account(batch["account_id"], parsed["Counterparty"])
            parsed["_transfer_target"] = target.name if target and is_transfer else None
            parsed["_transfer_account_id"] = str(target.id) if target and is_transfer else ""
            parsed["_needs_account"] = parsed["_internal"] and not parsed["_transfer_target"]
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
                                    and not parsed["_suggestions"] and not parsed["_needs_account"]
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
            "JOIN ledger_entries l ON l.transaction_id=t.id AND l.account_id=? "
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
        matches = [a.name for a in self.accounts.list(active_only=True)
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
        source_currency = self.accounts.get(source_account_id).currency
        accounts = [account for account in self.accounts.list(active_only=True)
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
        source_currency = self.accounts.get(source_account_id).currency
        bank_ids = {account.id: account.name for account in self.accounts.list(active_only=True)
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
        if parsed["Category"]:
            try:
                return self.categories.find_by_text(parsed["Category"]).id
            except ValidationError:
                pass
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
        self._created_in_batch = {}
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
                    self._pending_created = {}
                    try:
                        with self.db.transaction():
                            matched = self._post_import_row(batch, row_id, decision, row, accounts)
                            ambiguous_reserves += int(matched < 0)
                        self._created_in_batch.update(self._pending_created)
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
            txn = self.transactions.record_transfer(
                day, batch["account_id"] if amount < 0 else target.id,
                target.id if amount < 0 else batch["account_id"], abs(amount),
                notes=notes, source=TxnSource.IMPORT,
            )
            category = self.categories.get(int(category_id)) if category_id else None
            if self.money_from_others:
                owner, _ = self._held_for(row, decision, category, canonical, cp_text, similar, True)
                if owner:
                    source_id, target_id = ((batch["account_id"], target.id) if amount < 0
                                            else (target.id, batch["account_id"]))
                    self.money_from_others.sync_transfer(txn.id, day, owner, source_id, target_id,
                                                        abs(amount), notes)
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

    def summary(self, batch_id: int) -> dict[str, int]:
        counts = {row["status"]: row["n"] for row in self.db.all(
            "SELECT status,COUNT(*) AS n FROM bank_import_rows WHERE batch_id=? GROUP BY status", (batch_id,))}
        return {"posted": counts.get("POSTED", 0), "linked": counts.get("LINKED", 0),
                "skipped": counts.get("SKIPPED", 0), "duplicates": counts.get("DUPLICATE", 0)}
