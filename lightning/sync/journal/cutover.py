"""Explicit, resumable conversion of a returned encrypted legacy home.

The caller holds the profile/session lock and has stopped request and sync work.
This creates a retained verified checkpoint before installing journal metadata.
It is an engineering conversion primitive; production pairing remains a
separate authority-enrollment and native-acceptance gate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from lightning.database.snapshot import _inventory, snapshot, verify_connection

from .codec import JournalError


def _file_hash(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _account_code(db, reference) -> str:
    if type(reference) not in (str, int):
        raise JournalError("Legacy account reference is damaged; repair it before cutover")
    code_row = db.one("SELECT id,code FROM accounts WHERE code=?", (str(reference),))
    id_row = (db.one("SELECT id,code FROM accounts WHERE id=?", (int(reference),))
              if type(reference) is int or reference.isdecimal() else None)
    if code_row is not None and id_row is not None and code_row["id"] != id_row["id"]:
        raise JournalError("Legacy account reference is ambiguous; repair it before cutover")
    account = code_row or id_row
    if account is None:
        raise JournalError("A saved account no longer exists; repair it before cutover")
    return account["code"]


def _category_code(db, reference) -> str:
    if type(reference) not in (str, int):
        raise JournalError("Legacy budget category reference is damaged; repair it before cutover")
    by_code = db.one("SELECT id,code FROM categories WHERE code=?", (str(reference),))
    by_id = (db.one("SELECT id,code FROM categories WHERE id=?", (int(reference),))
             if type(reference) is int or reference.isdecimal() else None)
    if by_code is not None and by_id is not None and by_code["id"] != by_id["id"]:
        raise JournalError("Legacy budget category reference is ambiguous; repair it before cutover")
    category = by_code or by_id
    if category is None:
        raise JournalError("A saved budget category no longer exists; repair it before cutover")
    return category["code"]


def _budget_rows_fingerprint(db, category_ids) -> str:
    if not category_ids:
        return hashlib.sha256(b"[]").hexdigest()
    marks = ",".join("?" for _ in category_ids)
    rows = [dict(row) for row in db.all(f"SELECT * FROM budgets WHERE category_id IN ({marks}) "
                                         "ORDER BY category_id,month,one_off", tuple(category_ids))]
    codes = {row["id"]: row["code"] for row in db.all("SELECT id,code FROM categories")}
    for row in rows:
        row.pop("id", None)
        row["category_code"] = codes.get(row.pop("category_id"), "")
    rows.sort(key=lambda row: (row["category_code"], row["month"], row["one_off"]))
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _normalize_legacy_references(db) -> bool:
    """Replace device-local account/category IDs in remembered references and settings."""
    changed = False
    if db.has_table("settings") and db.has_table("accounts"):
        row = db.one("SELECT value FROM settings WHERE key='sms_account_endings'")
        if row is not None:
            try:
                endings = json.loads(row[0])
            except (TypeError, ValueError) as error:
                raise JournalError("Legacy SMS account mapping is damaged; repair it before cutover") from error
            if type(endings) is not dict:
                raise JournalError("Legacy SMS account mapping is damaged; repair it before cutover")
            normalized = {}
            for ending, reference in endings.items():
                if type(ending) is not str:
                    raise JournalError("Legacy SMS account mapping is damaged; repair it before cutover")
                normalized[ending] = _account_code(db, reference)
            encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if encoded != row[0]:
                with db.transaction():
                    db.execute("UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key='sms_account_endings'", (encoded,))
                changed = True
    if db.has_table("rule_conditions") and db.has_table("accounts"):
        for row in db.all("SELECT id,value FROM rule_conditions WHERE field='account'"):
            code = _account_code(db, row["value"])
            if code != row["value"]:
                with db.transaction():
                    db.execute("UPDATE rule_conditions SET value=? WHERE id=?", (code, row["id"]))
                changed = True
    if db.has_table("settings") and db.has_table("categories"):
        for key in ("budget_tracked_categories", "budget_income_categories", "budget_one_off_exclusions"):
            row = db.one("SELECT value FROM settings WHERE key=?", (key,))
            if row is None:
                continue
            try:
                values = json.loads(row[0])
            except (TypeError, ValueError) as error:
                raise JournalError("Legacy budget category settings are damaged; repair them before cutover") from error
            if type(values) is not list:
                raise JournalError("Legacy budget category settings are damaged; repair them before cutover")
            normalized = sorted({_category_code(db, value) for value in values})
            encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
            if encoded != row[0]:
                with db.transaction():
                    db.execute("UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key=?", (encoded, key))
                changed = True
        row = db.one("SELECT value FROM settings WHERE key='budget_suppressed_categories'")
        if row is not None:
            try:
                values = json.loads(row[0])
            except (TypeError, ValueError) as error:
                raise JournalError("Legacy budget suggestions are damaged; repair them before cutover") from error
            if type(values) is list:
                normalized = {_category_code(db, value): "never" for value in values}
            elif type(values) is dict:
                normalized = {_category_code(db, key): str(value) for key, value in values.items()}
            else:
                raise JournalError("Legacy budget suggestions are damaged; repair them before cutover")
            encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if encoded != row[0]:
                with db.transaction():
                    db.execute("UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key='budget_suppressed_categories'", (encoded,))
                changed = True
        row = db.one("SELECT value FROM settings WHERE key='budget_bulk_undo'")
        if row is not None and row[0]:
            try:
                snapshot = json.loads(row[0])
                if type(snapshot) is not dict or not snapshot.get("token") or type(snapshot.get("rows")) is not list:
                    raise ValueError("unsupported snapshot")
                if "category_codes" in snapshot and "category_ids" not in snapshot:
                    if type(snapshot["category_codes"]) is not list:
                        raise ValueError("unsupported category selection")
                    codes = [_category_code(db, value) for value in snapshot["category_codes"]]
                else:
                    category_ids = snapshot.get("category_ids", [])
                    if type(category_ids) is not list:
                        raise ValueError("unsupported category selection")
                    codes = [_category_code(db, value) for value in category_ids]
                code_by_id = {int(item["id"]): item["code"] for item in db.all("SELECT id,code FROM categories")}
                portable_rows = []
                for saved in snapshot["rows"]:
                    if type(saved) is not dict:
                        raise ValueError("unsupported budget row")
                    row_data = dict(saved)
                    row_data.pop("id", None)
                    row_data["category_code"] = _category_code(db, row_data.pop("category_id")) if "category_id" in row_data else _category_code(db, row_data["category_code"])
                    portable_rows.append(row_data)
                snapshot.pop("category_ids", None)
                snapshot["category_codes"] = sorted(set(codes))
                snapshot["rows"] = portable_rows
                snapshot["after_fingerprint"] = _budget_rows_fingerprint(db, [db.scalar(
                    "SELECT id FROM categories WHERE code=?", (code,)) for code in snapshot["category_codes"]])
                encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            except (KeyError, TypeError, ValueError, JournalError):
                # This is an optional, short-lived undo affordance; do not let a local-ID token replay
                # against a promoted device with different category IDs.
                encoded = ""
            if encoded != row[0]:
                with db.transaction():
                    db.execute("UPDATE settings SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key='budget_bulk_undo'", (encoded,))
                changed = True
    return changed


def _complete_normalization(store) -> None:
    db = store.db
    pending = db.scalar("SELECT value FROM journal_local WHERE name='cutover_normalization'")
    if pending is None:
        return
    if pending != "pending":
        raise JournalError("Cutover normalization state is damaged; keep this profile locked")
    with db.transaction():
        with store.adapter.writing():
            _normalize_legacy_references(db)
        db.execute("DELETE FROM journal_local WHERE name='cutover_normalization'")


def _verified_baseline(container, paths, *, retain_stranded: bool) -> tuple[Path, str]:
    db = container.db
    if not db.encrypted or db.path == ":memory:":
        raise JournalError("Journal cutover requires a named encrypted profile")
    if db.conn.in_transaction:
        raise JournalError("Finish the current save before converting this profile")
    # A live WAL would make a hash of the main file an incomplete identity for
    # the baseline; checkpoint it while the caller owns the profile lock.
    result = db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if result and result[0] != 0:
        raise JournalError("Could not checkpoint the encrypted profile for cutover")
    verify_connection(db.conn, encrypted=True)
    folder = Path(paths.backups_dir)
    folder.mkdir(parents=True, exist_ok=True)
    prefix = ".journal-cutover-stranded-" if retain_stranded else ".journal-cutover-baseline-"
    target = folder / f"{prefix}{uuid4().hex}.db"
    try:
        snapshot(db, target)
        candidate = type(db)(target, key=db.copy_key(), read_only=True)
        try:
            verify_connection(candidate.conn, encrypted=True)
            if _inventory(db.conn) != _inventory(candidate.conn):
                raise JournalError("The retained checkpoint does not match the live profile")
        finally:
            candidate.close()
        with target.open("rb") as handle:
            os.fsync(handle.fileno())
        if os.name != "nt":
            directory_fd = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        # The initializer binds the baseline tables to this exact verified
        # encrypted checkpoint. Caller-held profile lock prevents concurrent
        # writes between the logical equality check and initialization.
        return target, _file_hash(target)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def begin(container, paths, identity, *, generation=None, legacy_state="AT_HOME", retain_stranded=False):
    """Convert an encrypted, unlocked legacy ledger into a journal home.

    The caller must hold the profile/session lock. `legacy_state` is the value
    from the existing v1 HomeProtocolModel; an active lend is accepted only
    with an explicit stranded-copy decision, and its current encrypted home
    bytes are retained for later comparison. Returns `(store, device)`.
    """
    from .device import JournalDevice
    from .finance import attach, initialize
    from .home import JournalHome

    db = container.db
    if db.has_table("journal_meta"):
        store = attach(container)
        if store.config["device"] != identity.device_id or store.config["role"] != "home":
            raise JournalError("This journal profile belongs to another device or role")
        _complete_normalization(store)
        store.verify()
        return store, JournalDevice(store, identity, JournalHome(store, identity.sign))
    if legacy_state == "LENT":
        if retain_stranded is not True:
            raise JournalError("Receive the legacy return or explicitly retain the stranded copy before cutover")
    elif legacy_state not in ("AT_HOME", "NONE"):
        raise JournalError("The legacy lend must finish or be explicitly retained before cutover")
    elif retain_stranded not in (False, None):
        raise JournalError("There is no stranded legacy lend to retain")

    baseline_path, snapshot_hash = _verified_baseline(container, paths, retain_stranded=legacy_state == "LENT")
    try:
        # The picker folder suffix is only an eight-hex-character discovery ID,
        # not the journal authority UUID. Persist the ledger's stable profile ID
        # and reuse it when an interrupted cutover resumes.
        from lightning.sync.copies import ensure_profile_id
        from .codec import uuid
        profile = ensure_profile_id(db)
        uuid(profile)
        generation = generation or str(uuid4())
        store = initialize(container, profile=profile, generation=generation,
            device=identity.device_id, incarnation=str(uuid4()), home_key=identity.public_key,
            origin_key=identity.public_key, role="home", verified_baseline=snapshot_hash)
        _complete_normalization(store)
        store.verify()
        home = JournalHome(store, identity.sign)
        return store, JournalDevice(store, identity, home)
    except BaseException:
        # The pre-cutover checkpoint is deliberately retained if initialization
        # began; runtime must keep the profile locked when journal metadata now
        # exists and resume via this function.
        if not db.has_table("journal_meta"):
            baseline_path.unlink(missing_ok=True)
        raise
