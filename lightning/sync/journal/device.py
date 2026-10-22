"""Register capture and confirmed-only read models for experimental devices."""
from __future__ import annotations

from uuid import uuid4
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json

from .codec import JournalError, origin_id, unpack


class JournalDevice:
    def __init__(self, store, identity, home=None):
        if store.adapter is None:
            raise JournalError("A transaction adapter is required")
        self.store, self.identity, self.home = store, identity, home
        self.adapter, self.c = store.adapter, store.adapter.c

    def draft(self, record=None, *, initial=None):
        """Capture the values/tokens actually displayed, before another sync can run."""
        record = self.store.resolve(record) if record else None
        existing = self.store.record(record) if record else None
        shown = next((item["groups"] for item in self.view() if item["record"] == record and item["state"] != "Not taken"), {}) if record else {}
        if record is not None and (not shown or (existing and existing["deleted"])):
            raise JournalError("This transaction is no longer available. Refresh the register")
        bases = dict(existing["tokens"]) if existing else {}
        dependencies = []
        for wire in self.store.pending():
            item = unpack(wire)["body"]
            if self.store.resolve(item["record"]) == record:
                dependencies = [item["origin"]]
                for group in item["groups"]:
                    bases[group] = None
        identifier = str(uuid4())
        record = record or str(uuid4())
        values = shown if initial is None else initial
        from .codec import canonical
        with self.store.db.transaction():
            self.store.db.execute("INSERT INTO journal_drafts VALUES(?,?,?,?,?,?,NULL,NULL)",
                (identifier, record, "transaction.edit" if existing or dependencies else "transaction.add",
                 canonical(values).decode(), canonical(bases).decode(), canonical(dependencies).decode()))
        return identifier

    def submit_draft(self, identifier, groups, *, delete=False):
        """Idempotent form submission with the original field-group preconditions."""
        from .codec import digest
        request_hash = digest(dict(groups=groups, delete=delete))
        with self.store.db.transaction():
            row = self.store.db.one("SELECT * FROM journal_drafts WHERE id=?", (identifier,))
            if row is None:
                raise JournalError("Open the transaction form again")
            if row["wire"] is not None:
                if row["submission_hash"] != request_hash:
                    raise JournalError("This form was already saved. Open the transaction again")
                wire = bytes(row["wire"])
                self._offer(wire)
                return wire
            original = json.loads(row["groups_json"])
            if delete:
                changed = dict.fromkeys(original)
            else:
                self.adapter.validate_groups(groups, complete=True)
                changed = dict(groups)
                if "source" in original:
                    changed["source"] = original["source"]
                if row["kind"].endswith(".edit"):
                    changed = {key: value for key, value in changed.items() if value != original.get(key)}
                    if not changed:
                        return None
            tokens = json.loads(row["bases_json"])
            wire = self.store.save(kind="transaction.delete" if delete else row["kind"], record=row["record"], groups=changed,
                bases={group: tokens.get(group) for group in changed},
                dependencies=json.loads(row["dependencies_json"]), signer=self.identity.sign)
            self.store.db.execute("UPDATE journal_drafts SET wire=?,submission_hash=? WHERE id=?", (wire, request_hash, identifier))
        self._offer(wire)
        return wire

    def save(self, groups, *, record=None, delete=False, bases=None):
        """`bases` overrides the confirmed tokens a change is checked against (undo
        checks against the result of the action it reverses, not the latest)."""
        record = record or str(uuid4())
        record = self.store.resolve(record)
        current = self.store.record(record)
        if current is None and self.store.db.scalar("SELECT 1 FROM journal_ids WHERE entity='transactions' AND uuid=?", (record,)):
            from lightning.core.errors import ValidationError
            raise ValidationError("This payment was changed on another screen; edit it there")
        pending_parent = None
        pending_groups = {}
        for wire in self.store.pending():
            item = unpack(wire)["body"]
            if self.store.resolve(item["record"]) == record:
                pending_parent = item
                pending_groups.update(item["groups"])
        if delete:
            values = (current["groups"] if current else {}) | pending_groups
            groups = dict.fromkeys(values)
        else:
            self.adapter.validate_groups(groups, complete=current is None and pending_parent is None)
        explicit = bases
        bases = {group: current["tokens"].get(group) if current else None for group in groups}
        if explicit is not None:
            bases = {group: explicit.get(group) for group in groups}
        dependencies = []
        if pending_parent:
            dependencies = [pending_parent["origin"]]
            # A dependent edit refers to the prior proposal result, not a stale
            # confirmed token for any group that prior proposal changes.
            for group in groups:
                if group in pending_groups:
                    bases[group] = None
        wire = self.store.save(kind="transaction." + ("delete" if delete else "edit" if current or pending_parent else "add"),
            record=record, groups=groups, bases=bases, dependencies=dependencies, signer=self.identity.sign)
        self._offer(wire)
        return wire

    def command(self, action, /, *, record=None, **args):
        """Save a covered service action as a proposal; the home runs it."""
        from .commands import command, selection_token, target_slot
        kind, groups = "command." + action, dict(args=args)
        self.adapter.check(kind, groups)
        entry = command(kind)
        slot = target_slot(kind, groups)
        if entry.target:
            # A keyed row (a setting) gets a stable record id, so repeated saves chain.
            from uuid import UUID, uuid5
            keyed = type(entry.target[1]) is tuple
            record = str(uuid5(UUID(self.store.config["profile"]), slot)) if keyed else args[entry.target[1]]
        record = record or str(uuid4())
        base = self.adapter.row_token(slot) if slot else selection_token(self.adapter, kind, groups)
        selected = set(args[entry.targets[1]]) if entry.targets else set()
        dependencies = []
        for wire in self.store.pending():
            item = unpack(wire)["body"]
            if item["record"] == record or item["record"] in selected:
                dependencies, base = [item["origin"]], None  # Based on our own pending change.
        wire = self.store.save(kind=kind, record=record, groups=groups, bases={"args": base},
                               dependencies=dependencies, signer=self.identity.sign)
        self._offer(wire)
        return wire

    def pending_commands(self):
        result = []
        for wire in self.store.pending():
            body = unpack(wire)["body"]
            if body["kind"].startswith("command."):
                identifier = origin_id(body["origin"])
                state = self.home.status(identifier) if self.home else self.store.db.one(
                    "SELECT status,reason FROM journal_remote_states WHERE proposal_id=?", (identifier,))
                result.append(dict(proposal_id=identifier, name=body["kind"][len("command."):], args=body["groups"]["args"],
                                   state="Needs review" if state and state["status"] == "review" else "Pending"))
        return result

    def command_decisions(self):
        """Terminal command proposals and display state, read from journal storage."""
        result = []
        for decision in self.store.decisions():
            identifier = decision["proposal_id"]
            wire = self.store.db.scalar("SELECT wire FROM journal_outbox WHERE proposal_id=?", (identifier,))
            if wire is None:
                continue
            seen = self.store.db.scalar("SELECT first_display_at FROM journal_seen WHERE proposal_id=?", (identifier,))
            result.append(dict(proposal=bytes(wire), decision=bytes(decision["decision"]),
                               first_display_at=seen))
        return result

    def _offer(self, wire):
        """On the home, confirm at once when possible. The edit is already durably
        saved, so a held upload (staging limit, frozen authority) means waiting."""
        if self.home is not None:
            try:
                self.home.receive(wire)
                self.home.process()
            except JournalError:
                pass

    def view(self):
        confirmed = {}
        for row in self.store.db.all("SELECT record_id FROM journal_records ORDER BY record_id"):
            record = self.store.record(row[0])
            if not record["deleted"]:
                confirmed[row[0]] = dict(record=row[0], groups=record["groups"], state="Confirmed", reason="", confirmed=record["groups"])
        blocker = False
        for wire in self.store.pending():
            proposal = unpack(wire)["body"]
            if proposal["kind"].startswith("command."):
                continue  # Shown by pending_commands, not as register rows.
            target = self.store.resolve(proposal["record"])
            item = confirmed.setdefault(target, dict(record=target, groups={}, confirmed=None, reason=""))
            item["groups"] = item["groups"] | proposal["groups"] if not proposal["kind"].endswith("delete") else item["groups"]
            state = self.home.status(origin_id(proposal["origin"])) if self.home else self.store.db.one(
                "SELECT status,reason FROM journal_remote_states WHERE proposal_id=?", (origin_id(proposal["origin"]),))
            item["state"] = "Awaiting deletion" if proposal["kind"].endswith("delete") else "Needs review" if state and state["status"] == "review" else "Pending"
            reasons = {"queued": "Waiting for the home", "conflict": "Another device changed this value",
                       "possible-duplicate": "This may be a payment already recorded",
                       "home-error": "The home could not apply this edit; review it there"}
            item["reason"] = "Waiting for an earlier edit to be reviewed" if blocker else reasons.get(state["reason"], "Waiting for the home") if state else "Saved on this device"
            blocker = blocker or bool(state and state["status"] == "review")
            item["proposal_id"] = origin_id(proposal["origin"])
        for decision in self.store.decisions():
            content = unpack(bytes(decision["decision"]))["body"]
            if content["outcome"] == "rejected":
                seen = self.store.db.scalar("SELECT first_display_at FROM journal_seen WHERE proposal_id=?", (decision["proposal_id"],))
                if seen and datetime.now(timezone.utc) - datetime.fromisoformat(seen) >= timedelta(days=7):
                    continue
                wire = self.store.db.scalar("SELECT wire FROM journal_outbox WHERE proposal_id=?", (decision["proposal_id"],))
                proposal = unpack(bytes(wire))["body"]
                if proposal["kind"].startswith("command."):
                    continue
                current = self.store.record(proposal["record"])
                shown = (current["groups"] if current else {}) if proposal["kind"].endswith(".delete") else proposal["groups"]
                confirmed[decision["proposal_id"]] = dict(record=proposal["record"], groups=shown,
                    state="Not taken", reason={"cancelled": "Kept the confirmed value", "dependency-rejected": "An earlier edit was not taken",
                    "financial-validation": "The home could not apply this action. Review the transaction."}.get(content["reason"], "This edit could not be applied"), confirmed=None, proposal_id=decision["proposal_id"])
        return list(confirmed.values())

    def add_again(self, proposal_id):
        original = self.refused(proposal_id)
        return self.save(original["groups"] if not original["kind"].endswith(".delete") else {},
                         record=None if original["kind"].endswith(".add") else original["record"],
                         delete=original["kind"].endswith(".delete"))

    def refused(self, proposal_id):
        row = self.store.db.one("SELECT wire,decision FROM journal_outbox WHERE proposal_id=?", (proposal_id,))
        if row is None or row["decision"] is None or unpack(bytes(row["decision"]))["body"]["outcome"] != "rejected":
            raise JournalError("Only a refused edit can be added again")
        return unpack(bytes(row["wire"]))["body"]

    def displayed(self, proposal_ids):
        if len(proposal_ids) > 25:
            raise JournalError("Too many display acknowledgements")
        for identifier in proposal_ids:
            self.store.mark_displayed(identifier)

    def undo(self, proposal_id):
        """Reverse only what that action changed, checked against its own result:
        a later change to the same values on any device goes to review."""
        from .codec import digest
        row = self.store.db.one("SELECT revision,wire FROM journal_commits WHERE proposal_id=?", (proposal_id,))
        target = unpack(bytes(row["wire"]))["body"] if row else None
        if target is None or target["outcome"] != "accepted":
            raise JournalError("Only a retained accepted action can be undone")
        effect = target["effects"][0]
        record = self.store.resolve(effect["record"])
        prior = None
        for (wire,) in self.store.db.all("SELECT wire FROM journal_commits WHERE revision<? ORDER BY revision DESC", (row["revision"],)):
            item = unpack(bytes(wire))["body"]
            if item["effects"] and "alias" not in item["effects"][0] and self.store.resolve(item["effects"][0]["record"]) == record:
                prior = item["effects"][0]
                break
        if prior is None:
            return self.save({}, record=record, delete=True, bases=effect["tokens"])
        if effect["deleted"]:
            return self.save({group: value for group, value in prior["groups"].items() if group != "source"})
        changed = [group for group, token in effect["tokens"].items()
                   if token == digest(dict(proposal=target["proposal_hash"], group=group)) and group in prior["groups"]]
        if not changed:
            raise JournalError("That action changed nothing that can be undone")
        return self.save({group: prior["groups"][group] for group in changed},
                         record=record, bases=effect["tokens"])

    def choices(self):
        accounts = {account.name: self.adapter.uid("accounts", account.id) for account in self.c.accounts.list(active_only=True)
                    if account.account_type.value in {"BANK", "CASH"} and account.currency == self.c.base_currency}
        categories = {}
        for parent, children in self.c.categories.groups(include_inactive=False):
            for category in children:
                if not category.is_system:
                    categories[f"{category.name} · {parent.name}"] = self.adapter.uid("categories", category.id)
        return dict(accounts=accounts, categories=categories)

    def review_items(self):
        if self.home is None:
            return []
        result = [self.home.review_state(row[0]) for row in self.store.db.all("SELECT proposal_id FROM journal_inbox WHERE status='review'")]
        for review in result:
            for match in review["matches"]:
                record = self.store.record(match["record"])
                match["shown"] = self.describe(record["groups"])
                match["reference"] = self.c.transactions.get(self.adapter.local("transactions", match["record"])).ref
        return result

    def form_values(self, groups):
        choices = self.choices()
        reverse_accounts = {value: label for label, value in choices["accounts"].items()}
        reverse_categories = {value: label for label, value in choices["categories"].items()}
        money, category, details = groups.get("money", {}), groups.get("category", {}), groups.get("details", {})
        values = dict(account=reverse_accounts.get(money.get("account"), ""),
                      other_account=reverse_accounts.get(money.get("other_account"), ""),
                      date=money.get("date", ""), amount=money.get("amount", ""),
                      category=reverse_categories.get(category.get("category"), ""), **details)
        for index, split in enumerate(category.get("splits", [])[:16]):
            values[f"split_category_{index}"] = reverse_categories.get(split["category"], "")
            values[f"split_amount_{index}"] = split["amount"]
        return values

    def canonical_record(self, record):
        return self.store.resolve(record)

    def describe(self, groups):
        values = self.form_values(groups)
        labels = dict(account="Account", other_account="Transfer to", date="Date", amount="Amount",
                      category="Category", counterparty="Counterparty", notes="Notes")
        return [(label, values.get(key) or "—") for key, label in labels.items()]

    def form_groups(self, values):
        from lightning.core.errors import ValidationError
        from lightning.core.dates import parse_date
        options = self.choices()
        try:
            account = options["accounts"][values["account"]]
            other = options["accounts"][values["other_account"]] if values.get("other_account") else None
            category = options["categories"][values["category"]] if values.get("category") else None
            splits = [dict(category=options["categories"][values[f"split_category_{index}"]], amount=values[f"split_amount_{index}"])
                      for index in range(16) if values.get(f"split_category_{index}")]
        except KeyError as error:
            raise ValidationError("Type and pick a saved account and category") from error
        groups = dict(money=dict(account=account, other_account=other, date=parse_date(values["date"]).isoformat(), amount=values["amount"]),
                      category=dict(category=None if other else category, splits=splits),
                      details=dict(counterparty=values.get("counterparty", ""), notes=values.get("notes", ""), description=""))
        self.adapter.validate_groups(groups, complete=True)
        return groups

    def balances(self):
        return [dict(uuid=self.adapter.uid("accounts", account.id), name=account.name,
                     balance=self.c.reporting.account_balance(account.id))
                for account in self.c.accounts.list() if account.account_type.value in {"BANK", "CASH"}]

    def view_version(self):
        from .codec import digest
        return digest(dict(cursor=self.store.cursor(), pending=[dict(row) for row in self.store.db.all(
            "SELECT status,reason,COUNT(*) AS count FROM journal_remote_states GROUP BY status,reason ORDER BY status,reason")],
            outbox=dict(self.store.db.one("SELECT COUNT(*) AS count,MAX(seq) AS latest,SUM(decision IS NOT NULL) AS decided FROM journal_outbox"))))

    def sync_status(self):
        timestamp = self.store.db.scalar("SELECT value FROM journal_local WHERE name='last_sync'")
        shown = datetime.fromisoformat(timestamp).astimezone(ZoneInfo("Africa/Cairo")).strftime("%Y-%m-%d %H:%M") if timestamp else "Not yet synced"
        return dict(last=shown, pending=len(self.store.pending()))

    def sync_with(self, home):
        """Local delta exchange; transport adapters deliver these same signed bytes."""
        if self.store.config["generation"] != home.store.config["generation"]:
            raise JournalError("Authority generation changed; explicit recovery required")
        for wire in self.store.pending():
            home.receive(wire)
        home.process()
        with self.store.db.transaction():
            for wire in self.store.pending():
                identifier = origin_id(unpack(wire)["body"]["origin"])
                status = home.status(identifier)
                if status:
                    self.store.db.execute("INSERT OR REPLACE INTO journal_remote_states VALUES(?,?,?)",
                                          (identifier, status["status"], status["reason"]))
        count = 0
        while self.store.cursor() != home.store.cursor():
            batch = home.store.commits_after(self.store.cursor())
            if not batch:
                raise JournalError("Missing confirmed history; verified snapshot required")
            for wire in batch:
                from .finance import ChunksMissing
                try:
                    self.store.apply(wire)
                except ChunksMissing as error:  # In process: copy the large effect's chunks, then apply.
                    for item in error.missing:
                        self.store.put_chunk(home.store.chunk(item), error.missing)
                    self.store.apply(wire)
                count += 1
        if count:
            self.store.verify()
        with self.store.db.transaction():
            self.store.db.execute("INSERT OR REPLACE INTO journal_local VALUES('last_sync',?)", (datetime.now(timezone.utc).isoformat(),))
        return count

    def flush_home(self):
        if self.home is None:
            raise JournalError("This device is not the home")
        for wire in self.store.pending():
            self.home.receive(wire)
        return self.home.process()
