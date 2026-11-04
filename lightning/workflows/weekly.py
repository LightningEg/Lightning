"""A short completion flow over existing decisions, plus explicit reusable-rule offers."""
from __future__ import annotations

from hashlib import sha256
import json
from urllib.parse import urlencode

from lightning.core.dates import now_iso, today
from lightning.core.errors import LightningError, ValidationError
from lightning.rules import engine
from lightning.workflows.review import ReviewInbox, grouped


class WeeklyReview:
    def __init__(self, c):
        self.c = c

    def snapshot(self):
        items = ReviewInbox(self.c).items(today())
        token = sha256(json.dumps(items, sort_keys=True, default=str).encode()).hexdigest()
        return {"items": items, "groups": grouped(items), "token": token,
                "last": self.c.settings.get("weekly_review_at"), "rules": self.rule_offers()}

    def complete(self, token):
        with self.c.db.transaction(undo_label="Record weekly review"):
            state = self.snapshot()
            if token != state["token"]:
                raise ValidationError("The review changed. Read the updated decisions before recording completion.")
            self.c.settings.set("weekly_review_at", now_iso())

    def rule_offers(self):
        c = self.c
        corrections = {}
        evidence = []
        # Audit evidence, rather than another learner over the usual-category rule.
        for record in c.db.all("SELECT entity_id,before_json,after_json FROM audit_log "
                               "WHERE entity='transaction' AND action='edit' ORDER BY id DESC LIMIT 500"):
            try:
                before, after = json.loads(record["before_json"]), json.loads(record["after_json"])
                old = {row["category_id"] for row in before["lines"] if row.get("category_id")}
                new = {row["category_id"] for row in after["lines"] if row.get("category_id")}
                lines = after["lines"]
                accounts = {line["account_id"] for line in lines}
                name = after.get("counterparty", "").strip()
                if (old == new or len(new) != 1 or len(accounts) != 1 or not name
                        or after["type"] not in {"IN", "OUT"} or any(line.get("owner_id") for line in lines)):
                    continue
                cid, account = next(iter(new)), next(iter(accounts))
                key = (name, account, after["type"], cid)
                corrections.setdefault(key, set()).add(record["entity_id"])
                evidence.append((key, record["entity_id"]))
            except (ValueError, TypeError, KeyError, LightningError):
                continue
        candidates = {key: ids for key, ids in corrections.items() if len(ids) >= 3}
        if not candidates:
            return []
        # At most 500 audit rows were read above. Fetch current evidence in one
        # bounded query, rather than loading each transaction and its lines.
        ids = sorted(set().union(*candidates.values()))
        marks = ",".join("?" for _ in ids)
        current = {}
        for row in c.db.all(
            f"SELECT t.id,t.status,l.category_id FROM transactions t "
            f"LEFT JOIN ledger_entries l ON l.transaction_id=t.id WHERE t.id IN ({marks})", tuple(ids)
        ):
            txn = current.setdefault(row["id"], {"status": row["status"], "categories": set()})
            if row["category_id"]:
                txn["categories"].add(row["category_id"])
        # Preserve the order of the first still-valid correction for each offer.
        valid_corrections = {}
        for key, txn_id in evidence:
            txn = current.get(txn_id)
            if key in candidates and txn and txn["status"] != "VOID" and txn["categories"] == {key[3]}:
                valid_corrections.setdefault(key, set()).add(txn_id)
        categories = {r["id"]: r for r in c.db.all("SELECT id,name,active,is_system FROM categories")}
        accounts = {r["id"]: r["code"] for r in c.db.all("SELECT id,code FROM accounts")}
        dismissed = {r["key"] for r in c.db.all(
            "SELECT key FROM settings WHERE key LIKE 'dismiss_rule_%' AND value='1'")}
        rules = c.rules.repo.rules()
        offers = []
        for (name, account, kind, cid), valid in valid_corrections.items():
            if len(valid) < 3:
                continue
            category = categories.get(cid)
            if not category or not category["active"] or category["is_system"]:
                continue
            identity = sha256(json.dumps([name, account, kind, cid]).encode()).hexdigest()[:24]
            if "dismiss_rule_" + identity in dismissed:
                continue
            txn = {"counterparty": [name], "notes": "", "amount": 0,
                   "account_id": account, "account_code": accounts.get(account)}
            if engine.run(rules, txn).category_id == cid:
                continue
            values = {"counterparty": name, "counterparty_op": "is", "account_id": account,
                      "category_id": cid, "match": "all", "direction": "in" if kind == "IN" else "out"}
            offers.append({"id": identity, "name": name, "category": category["name"], "count": len(valid),
                           "href": "/rules/new?" + urlencode(values)})
            if len(offers) == 4:
                break
        return offers[:4]

    def dismiss(self, identity):
        if identity not in {item["id"] for item in self.rule_offers()}:
            raise ValidationError("That rule suggestion is no longer available.")
        with self.c.db.transaction(undo_label="Dismiss rule suggestion"):
            self.c.settings.set("dismiss_rule_" + identity, "1")
