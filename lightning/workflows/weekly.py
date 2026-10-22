"""A short completion flow over existing decisions, plus explicit reusable-rule offers."""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from urllib.parse import urlencode

from lightning.core.dates import now_iso, today
from lightning.core.errors import LightningError, ValidationError
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
                txn = c.transactions.get(record["entity_id"])
                if txn.is_void or {line.category_id for line in txn.lines if line.category_id} != {cid}:
                    continue
                key = (name, account, after["type"], cid)
                corrections.setdefault(key, set()).add(txn.id)
            except (ValueError, TypeError, KeyError, LightningError):
                continue
        offers = []
        for (name, account, kind, cid), ids in corrections.items():
            if len(ids) < 3:
                continue
            category = c.categories.get(cid)
            if not category.active or category.is_system:
                continue
            identity = sha256(json.dumps([name, account, kind, cid]).encode()).hexdigest()[:24]
            if c.settings.get("dismiss_rule_" + identity) == "1":
                continue
            if c.rules.outcome([name], "", 0, account).category_id == cid:
                continue
            values = {"counterparty": name, "counterparty_op": "is", "account_id": account,
                      "category_id": cid, "match": "all", "direction": "in" if kind == "IN" else "out"}
            offers.append({"id": identity, "name": name, "category": category.name, "count": len(ids),
                           "href": "/rules/new?" + urlencode(values)})
        return offers[:4]

    def dismiss(self, identity):
        if identity not in {item["id"] for item in self.rule_offers()}:
            raise ValidationError("That rule suggestion is no longer available.")
        with self.c.db.transaction(undo_label="Dismiss rule suggestion"):
            self.c.settings.set("dismiss_rule_" + identity, "1")
