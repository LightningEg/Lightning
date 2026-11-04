"""Submission fingerprints and audit-backed duplicate delivery checks.

Callers retain their surrounding atomic write; this store never commits or
starts a save. Audit rows remain outside Undo and the journal, as before.
"""
import hashlib
import json

from lightning.core.errors import ValidationError
from lightning.database.audit import AuditLog
from lightning.database.connection import Database

from .domain import Transaction
from .repository import TransactionRepository


def fingerprint(token, payload: dict) -> tuple[str, str] | None:
    token = str(token or "")
    if len(token) != 32 or any(char not in "0123456789abcdef" for char in token):
        return None  # Callers without a token keep the old contract.
    body = json.dumps({key: str(value) for key, value in payload.items()}, sort_keys=True, ensure_ascii=False)
    return token, hashlib.sha256(body.encode()).hexdigest()


def revision(snapshot: dict) -> str:
    """Opaque hash of the facade's unchanged header/posting snapshot."""
    payload = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SubmissionStore:
    def __init__(self, db: Database, repo: TransactionRepository, audit: AuditLog):
        self.db, self.repo, self.audit = db, repo, audit

    def submitted(self, token, payload: dict) -> Transaction | None:
        """The transaction an earlier delivery of this same form created, if any. Call inside the write transaction."""
        found = fingerprint(token, payload)
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

    def form_seen(self, token, payload: dict) -> bool:
        """True when an earlier delivery of this same form already saved something that is not one transaction (a
        plan, a held-for-others entry). The same token with other values is refused. Call inside the write transaction."""
        found = fingerprint(token, payload)
        if found is None:
            return False
        row = self.db.one("SELECT after_json FROM audit_log WHERE entity='form' AND summary=?", (found[0],))
        if row is None:
            return False
        if json.loads(row["after_json"]) != found[1]:
            raise ValidationError("This form was already saved. Open a new one to add another.")
        return True

    def remember_form(self, token, payload: dict) -> None:
        """The same, for a form that saved something other than one transaction."""
        found = fingerprint(token, payload)
        if found is not None:
            self.audit.record("form", 0, "SUBMITTED", found[0], after=found[1])

    def remember_submission(self, token, payload: dict, txn_id: int) -> None:
        """Saved in the audit log, in the same write as the transaction; the log is outside Undo and the journal."""
        found = fingerprint(token, payload)
        if found is not None:
            self.audit.record("form", txn_id, "SUBMITTED", found[0], after=found[1])
