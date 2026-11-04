"""Device-local SMS/CSV review candidates, followed by explicit per-payment saves."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4

from lightning.bank_import_rows import decode_csv, _date, _amount
from lightning.sms_imports import parse_sms, fingerprint

from .codec import JournalError, canonical, digest, origin_id, unpack


class JournalCapture:
    def __init__(self, device):
        self.device, self.db = device, device.store.db

    def candidate(self, groups, *, namespace, source_id, batch):
        self.device.adapter.validate_groups(groups, complete=True)
        source = dict(namespace=namespace, id=source_id)
        self.device.adapter.validate_groups({"source": source})
        saved = groups | {"source": source}
        with self.db.transaction():
            prior = self.db.one("SELECT id,groups_json FROM journal_candidates WHERE namespace=? AND source_id=?", (namespace, source_id))
            if prior:
                original_hash = self.db.scalar("SELECT payload_hash FROM journal_candidate_inputs WHERE id=?", (prior["id"],))
                if original_hash != self.device.adapter.source_token(groups["money"]):
                    raise JournalError("Capture source identity reused with different content")
                return prior["id"]
            candidate = str(uuid4())
            self.db.execute("INSERT INTO journal_candidates VALUES(?,?,?,?,?,NULL)",
                            (candidate, namespace, source_id, canonical(saved).decode(), batch))
            self.db.execute("INSERT INTO journal_candidate_inputs VALUES(?,?)", (candidate, self.device.adapter.source_token(groups["money"])))
        return candidate

    def csv(self, data, *, account, category, mapping):
        if len(data) > 5 * 1024 * 1024:
            raise JournalError("CSV size limit exceeded")
        _, rows = decode_csv(data)
        if len(rows) > 5000:
            raise JournalError("Review at most 5000 payments per import")
        batch = str(uuid4())
        candidates = []
        file_hash = hashlib.sha256(data).hexdigest()
        # One transaction stages the complete review; no partially staged file.
        with self.db.transaction():
            for index, row in enumerate(rows, 1):
                groups = dict(money=dict(account=account, other_account=None, date=_date(row[mapping["date"]]),
                                        amount=_amount(row[mapping["amount"]])),
                    category=dict(category=category, splits=[]), details=dict(
                        counterparty=row.get(mapping.get("counterparty"), ""),
                        notes=row.get(mapping.get("notes"), ""), description=""))
                reference = row.get(mapping.get("reference"), "")
                # A bank reference is namespaced to its account. Without one, the
                # file hash + line position proves only repeated import of that file.
                namespace = f"bank:{account}" if reference else f"csv:{account}"
                source_id = reference or digest(dict(file=file_hash, row=index))
                candidates.append(self.candidate(groups, namespace=namespace, source_id=source_id, batch=batch))
        return batch, candidates

    def sms(self, text, *, sender, received, account, category, source_id=None):
        if received.tzinfo is not None:
            received = received.astimezone(ZoneInfo("Africa/Cairo"))
        parsed = parse_sms(text, sender=sender, received=received)
        if parsed is None:
            return None
        account_record = self.device.c.accounts.get(self.device.adapter.local("accounts", account))
        if account_record.last4 and parsed.ending and account_record.last4 != parsed.ending:
            return None
        groups = dict(money=dict(account=account, other_account=None, date=parsed.when[:10], amount=str(parsed.signed)),
                      category=dict(category=category, splits=[]),
                      details=dict(counterparty=parsed.place, notes="", description=""))
        # OS message identity is preferred. Text/time hash is a local candidate key,
        # not proof that a similar CSV payment is the same transaction.
        source_id = source_id or digest(dict(text=fingerprint(text), received=received.isoformat()))
        return self.candidate(groups, namespace=f"sms:{account}", source_id=source_id, batch=str(uuid4()))

    def waiting(self):
        return [dict(id=row["id"], batch=row["batch"], groups=json.loads(row["groups_json"]))
                for row in self.db.all("SELECT * FROM journal_candidates WHERE proposal_id IS NULL ORDER BY rowid")]

    def get(self, candidate):
        row = self.db.one("SELECT groups_json,proposal_id FROM journal_candidates WHERE id=?", (candidate,))
        if row is None or row["proposal_id"] is not None:
            raise JournalError("This payment was already saved. Edit it in the register")
        return json.loads(row["groups_json"])

    def read_source(self, source, *, account, category):
        if source.permission() != "granted":
            raise JournalError("Allow SMS access on this phone before reading bank messages")
        cursor_name = "sms:" + account
        cursor = self.db.scalar("SELECT value FROM journal_capture_cursor WHERE name=?", (cursor_name,)) or 0
        messages = sorted(source.since(cursor), key=lambda item: item[2])
        if len(messages) > 500:
            cutoff = messages[499][2]
            messages = [item for item in messages if item[2] <= cutoff]
        staged = []
        with self.db.transaction():
            for sender, text, received in messages:
                candidate = self.sms(text, sender=sender, received=datetime.fromtimestamp(received / 1000, timezone.utc),
                    account=account, category=category, source_id=f"{received}:{fingerprint(text)}")
                if candidate:
                    staged.append(candidate)
                cursor = max(cursor, received)
            self.db.execute("INSERT OR REPLACE INTO journal_capture_cursor VALUES(?,?)", (cursor_name, cursor))
        return staged

    def save(self, candidate_id, *, groups=None):
        # Outbox + candidate progress commit together. Home confirmation happens
        # after the outer transaction; a process exit cannot lose a saved edit.
        with self.db.transaction():
            row = self.db.one("SELECT * FROM journal_candidates WHERE id=?", (candidate_id,))
            if row is None:
                raise JournalError("Candidate not found")
            if row["proposal_id"]:
                if groups is not None and (json.loads(row["groups_json"]) | groups) != json.loads(row["groups_json"]):
                    raise JournalError("This payment was already saved. Edit it in the register")
                return row["proposal_id"]
            stored = json.loads(row["groups_json"])
            values = stored if groups is None else groups | {"source": stored["source"]}
            self.device.adapter.validate_groups(values, complete=True)
            wire = self.device.store.save(kind="transaction.add", record=str(uuid4()), groups=values,
                bases=dict.fromkeys(values), signer=self.device.identity.sign)
            identifier = origin_id(unpack(wire)["body"]["origin"])
            self.db.execute("UPDATE journal_candidates SET proposal_id=?,groups_json=? WHERE id=?", (identifier, canonical(values).decode(), candidate_id))
        self.device._offer(wire)
        return identifier

    def progress(self, batch):
        rows = self.db.all("SELECT proposal_id FROM journal_candidates WHERE batch=?", (batch,))
        return dict(total=len(rows), saved=sum(row[0] is not None for row in rows),
                    decided=sum(bool(row[0] and self.db.scalar("SELECT decision IS NOT NULL FROM journal_outbox WHERE proposal_id=?", (row[0],))) for row in rows))

    def batches(self):
        result = []
        for row in self.db.all("SELECT batch,MIN(rowid) AS first FROM journal_candidates GROUP BY batch ORDER BY first DESC LIMIT 4"):
            batch = row["batch"]
            first = self.db.scalar("SELECT groups_json FROM journal_candidates WHERE batch=? ORDER BY rowid LIMIT 1", (batch,))
            result.append(dict(batch=batch, date=json.loads(first)["money"]["date"], **self.progress(batch)))
        return result

    def undo_batch(self, batch):
        with self.db.transaction():
            prior = self.db.scalar("SELECT proposals FROM journal_batch_undo WHERE batch=?", (batch,))
            if prior is not None:
                return json.loads(prior)
            rows = self.db.all("SELECT c.proposal_id,o.decision FROM journal_candidates c LEFT JOIN journal_outbox o ON c.proposal_id=o.proposal_id WHERE c.batch=? ORDER BY c.rowid DESC", (batch,))
            if not rows or any(row["proposal_id"] is None or row["decision"] is None for row in rows):
                raise JournalError("Save and sync this import, then resolve its reviews before undoing it")
            proposals = []
            for row in rows:
                if unpack(bytes(row["decision"]))["body"]["outcome"] == "accepted":
                    wire = self.device.undo(row["proposal_id"])
                    proposals.append(origin_id(unpack(wire)["body"]["origin"]))
            # Aliases never posted new money and therefore have nothing to undo.
            self.db.execute("INSERT INTO journal_batch_undo VALUES(?,?)", (batch, json.dumps(proposals)))
        return proposals
