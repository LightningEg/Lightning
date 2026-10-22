"""Rules with conditions: make, change and delete them, ask what they say about a transaction, and refile
past transactions when the user asks (with one undo).

Imports and the register ask ``outcome`` before today's order (the counterparty's category, then its usual
one: Architecture › Default category for a counterparty). Rules only suggest: an import still waits for
review, and nothing posted changes unless the user applies a rule to the past.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from decimal import Decimal

from lightning.categories.domain import Direction, Movement
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.money import ZERO, fmt, to_decimal
from lightning.transactions.tags import normalize as normalize_tag

from . import engine
from .engine import AMOUNT_OPS, TEXT_OPS, Condition, Outcome, Part, Rule
from .repository import RuleRepository

MAX_PARTS = 3
UNDO_KEY = "rules_apply_undo"
AMOUNT_WORDS = {"is": "is", "about": "about", "between": "between", "more": "more than", "less": "less than"}
TEXT_WORDS = {"is": "is", "contains": "contains", "one_of": "is one of"}


@dataclass(frozen=True)
class PastChange:
    id: int
    date: str
    counterparty: str
    amount: Decimal
    category_from: str


class RuleService:
    def __init__(self, db, categories, accounts, transactions, settings):
        self.db = db
        self.repo = RuleRepository(db)
        self.categories = categories
        self.accounts = accounts
        self.transactions = transactions
        self.settings = settings

    # ------------------------------------------------------------------ reading
    def list(self) -> list[Rule]:
        return self.repo.rules(active_only=False)

    def get(self, rule_id: int) -> Rule:
        rule = next((r for r in self.repo.rules(active_only=False) if r.id == rule_id), None)
        if rule is None:
            raise NotFoundError("That rule no longer exists.")
        return rule

    def outcome(self, counterparty: list[str] | str | None = None, notes: str = "", amount=None,
                account_id: int | None = None) -> Outcome:
        """What the rules say about one transaction. ``counterparty`` may hold several spellings (the bank's
        text and the saved name); a condition holds when any of them fits."""
        names = [counterparty] if isinstance(counterparty, str) else list(counterparty or [])
        account_code = self.db.scalar("SELECT code FROM accounts WHERE id=?", (account_id,)) if account_id is not None else None
        txn = {"counterparty": [n for n in names if n], "notes": notes or "", "amount": amount,
               "account_id": account_id, "account_code": account_code}
        return engine.run(self.repo.rules(), txn)

    def category_for_name(self, name: str) -> int | None:
        """The category rules give a counterparty on its name alone, for filling the register as you type.
        Only rules that look at nothing but the counterparty count; the others need the amount, so they
        decide when the row is saved."""
        rules = [r for r in self.repo.rules() if all(c.field == "counterparty" for c in r.conditions)]
        return engine.run(rules, {"counterparty": [name]}).category_id

    def depends_on_more_than_name(self, name: str) -> bool:
        """A rule names this counterparty and also looks at the amount, notes, account or direction."""
        txn = {"counterparty": [name]}
        for rule in self.repo.rules():
            named = [c for c in rule.conditions if c.field == "counterparty"]
            if named and len(named) < len(rule.conditions) and any(engine.holds(c, txn) for c in named):
                return True
        return False

    def split_for(self, rule_id: int | None, amount) -> list[tuple[int, Decimal]] | None:
        """A rule's split of an expense of ``amount``; None when it has none or leaves nothing for the rest."""
        rule = next((r for r in self.repo.rules() if r.id == rule_id), None) if rule_id else None
        if not rule or not rule.parts or not rule.category_id:
            return None
        return engine.split(abs(Decimal(amount)), rule.parts, rule.category_id)

    def describe(self, rule: Rule) -> dict:
        """The rule in words: "Counterparty contains Vodafone · amount between 100 and 300" and "Phone"."""
        when = []
        for c in rule.conditions:
            if c.field in ("counterparty", "notes"):
                when.append(f"{c.field.capitalize()} {TEXT_WORDS[c.op]} {c.value}")
            elif c.field == "amount":
                text = (f"{fmt(Decimal(c.value), 0)} and {fmt(Decimal(c.value_to), 0)}" if c.op == "between"
                        else fmt(Decimal(c.value), 0))
                when.append(f"Amount {AMOUNT_WORDS[c.op]} {text}")
            elif c.field == "account":
                when.append(f"Account is {self._account_name(c.value)}")
            elif c.field == "direction":
                when.append("Money in" if c.value == "in" else "Money out")
        then = []
        if rule.category_id:
            then.append(self._category_name(rule.category_id))
        for part in rule.parts:
            share = f"{fmt(part.value, 0)}%" if part.method == "percent" else fmt(part.value, 0)
            then.append(f"{share} to {self._category_name(part.category_id)}")
        then += [f"#{t}" for t in rule.tags]
        return {"when": (" · " if rule.match_all else " or ").join(when), "then": " · ".join(then), "when_parts": when}

    def form_values(self, rule: Rule | None = None) -> dict:
        """The rule as the form's fields."""
        values = {"match": "all", "counterparty_op": "contains", "counterparty": "", "notes": "", "amount_op": "",
                  "amount": "", "amount_to": "", "account_id": "", "direction": "", "category_id": "", "tag": ""}
        for i in range(1, MAX_PARTS + 1):
            values[f"part_category_{i}"] = values[f"part_value_{i}"] = ""
        if rule is None:
            return values
        values["match"] = "all" if rule.match_all else "any"
        for c in rule.conditions:
            if c.field == "counterparty":
                values["counterparty_op"], values["counterparty"] = c.op, c.value
            elif c.field == "notes":
                values["notes"] = c.value
            elif c.field == "amount":
                values["amount_op"], values["amount"], values["amount_to"] = c.op, c.value, c.value_to or ""
            elif c.field == "account":
                values["account_id"] = str(self._account_id(c.value) or c.value)
            elif c.field == "direction":
                values["direction"] = c.value
        values["category_id"] = str(rule.category_id or "")
        values["tag"] = " ".join(f"#{t}" for t in rule.tags)
        for i, part in enumerate(rule.parts, 1):
            values[f"part_category_{i}"] = str(part.category_id)
            values[f"part_value_{i}"] = f"{part.value.normalize():f}" + ("%" if part.method == "percent" else "")
        return values

    # ------------------------------------------------------------------ writing
    def save(self, values: dict, rule_id: int | None = None) -> int:
        if rule_id is not None:
            self.get(rule_id)
        match_all, conditions = self._conditions(values)
        category_id = self._category(values.get("category_id"), "category_id")
        tags = []
        for word in str(values.get("tag") or "").replace(",", " ").split():
            tag = normalize_tag(word)
            if not tag:
                raise ValidationError("A tag is a word with at least one letter, like #eid.", "tag")
            if tag not in tags:
                tags.append(tag)
        parts = self._parts(values, category_id, conditions)
        if not category_id and not tags:
            raise ValidationError("Choose a category or a tag for the rule to set.", "category_id")
        with self.db.transaction():
            return self.repo.save(rule_id, match_all, conditions, category_id, tags, parts)

    def delete(self, rule_id: int) -> None:
        self.get(rule_id)
        with self.db.transaction():
            self.repo.delete(rule_id)

    # ------------------------------------------------------------------ the past
    def past(self, rule_id: int) -> list[PastChange]:
        """Posted transactions this rule would refile if applied to the past: it is the rule that decides
        their category among all the rules, the category differs from theirs, and it fits their direction."""
        rule = self.get(rule_id)
        if not rule.category_id:
            return []
        target = self.categories.get(rule.category_id)
        rules = self.repo.rules()
        out = []
        locked = {row["transaction_id"] for row in self.db.all(
            "SELECT DISTINCT le.transaction_id FROM ledger_entries le JOIN reconciled_through r "
            "ON r.account_id=le.account_id WHERE le.date<=r.date")}
        for row in self.repo.single_category_history():
            if row["id"] in locked:
                continue
            if row["category_id"] == rule.category_id:
                continue
            wanted = Direction.IN if row["type"] == "IN" else Direction.OUT
            if target.direction not in (wanted, Direction.BOTH):
                continue
            current = self.categories.get(row["category_id"])
            if current.is_system:
                continue  # held for others and loan payments are filed by the app, not by rules
            account_code = self.db.scalar("SELECT code FROM accounts WHERE id=?", (row["account_id"],))
            txn = {"counterparty": [row["counterparty"], row["canonical"]], "notes": row["notes"],
                   "amount": row["amount"], "account_id": row["account_id"], "account_code": account_code}
            if engine.run(rules, txn).rule_id != rule.id:
                continue
            out.append(PastChange(row["id"], row["date"], row["canonical"] or row["counterparty"] or "",
                                  row["amount"], current.name))
        return out

    def past_token(self, rule_id, changes=None):
        from hashlib import sha256
        data = {"rule": asdict(self.get(rule_id)),
                "changes": [asdict(change) for change in (self.past(rule_id) if changes is None else changes)]}
        return sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def apply_past(self, rule_id: int, selected_ids=None, fingerprint=None) -> tuple[int, str]:
        with self.db.transaction(undo_label="Apply rule to selected activity"):
            rule = self.get(rule_id)
            changes = self.past(rule_id)
            if fingerprint is not None and fingerprint != self.past_token(rule_id, changes):
                raise ValidationError("The rule preview changed. Review it again before applying.")
            if selected_ids is not None:
                chosen = set(selected_ids)
                if chosen - {change.id for change in changes}:
                    raise ValidationError("The rule preview changed. Review it again before applying.")
                changes = [change for change in changes if change.id in chosen]
            if not changes:
                return 0, ""
            old = {}
            for change in changes:
                txn = self.transactions.get(change.id)
                old[str(change.id)] = next(line.category_id for line in txn.lines if line.category_id)
            changed, _ = self.transactions.set_category([c.id for c in changes], rule.category_id)
            token = secrets.token_hex(8)
            self.settings.set(UNDO_KEY, json.dumps({"token": token, "rule_id": rule_id,
                                                    "old": {k: v for k, v in old.items() if int(k) in changed}}))
        return len(changed), token

    def undo(self, token: str) -> int:
        """Put back the categories the last "apply to past" changed."""
        snapshot = json.loads(self.settings.get(UNDO_KEY) or "{}")
        if not token or snapshot.get("token") != token:
            raise ValidationError("That change can no longer be undone.")
        by_category: dict[int, list[int]] = {}
        for txn_id, category_id in snapshot["old"].items():
            by_category.setdefault(int(category_id), []).append(int(txn_id))
        count = 0
        with self.db.transaction():
            for category_id, ids in by_category.items():
                count += len(self.transactions.set_category(ids, category_id)[0])
            self.settings.set(UNDO_KEY, "")
        return count

    def can_undo(self, token: str) -> bool:
        try:
            return bool(token) and json.loads(self.settings.get(UNDO_KEY) or "{}").get("token") == token
        except ValueError:
            return False

    # ------------------------------------------------------------------ checks
    def _conditions(self, values: dict) -> tuple[bool, list[Condition]]:
        match_all = str(values.get("match") or "all") != "any"
        conditions = []
        name = str(values.get("counterparty") or "").strip()
        if name:
            op = str(values.get("counterparty_op") or "contains")
            if op not in TEXT_OPS:
                raise ValidationError("Choose is, contains or one of.", "counterparty_op")
            if op == "one_of":
                name = ", ".join(n.strip() for n in name.split(",") if n.strip())
            conditions.append(Condition("counterparty", op, name))
        notes = str(values.get("notes") or "").strip()
        if notes:
            conditions.append(Condition("notes", "contains", notes))
        op = str(values.get("amount_op") or "")
        if op:
            if op not in AMOUNT_OPS:
                raise ValidationError("Choose how to compare the amount.", "amount_op")
            low = abs(to_decimal(values.get("amount"), "amount"))
            if low <= ZERO:
                raise ValidationError("Enter an amount above zero.", "amount")
            top = None
            if op == "between":
                top = abs(to_decimal(values.get("amount_to"), "amount_to"))
                if top <= low:
                    raise ValidationError("The second amount must be above the first.", "amount_to")
            conditions.append(Condition("amount", op, format(low, "f"), format(top, "f") if top is not None else None))
        account = str(values.get("account_id") or "").strip()
        if account:
            # Rules persist a stable account code so they remain correct across
            # journal devices whose local integer ids differ.
            try:
                stable_code = (self.accounts.get(int(account)).code if account.isdigit()
                               else self.db.scalar("SELECT code FROM accounts WHERE code=?", (account,)))
            except (NotFoundError, ValueError):
                stable_code = None
            if not stable_code:
                raise ValidationError("Choose one of your accounts.", "account_id")
            conditions.append(Condition("account", "is", stable_code))
        direction = str(values.get("direction") or "")
        if direction in ("in", "out"):
            conditions.append(Condition("direction", "is", direction))
        if not conditions:
            raise ValidationError("Say when the rule applies: a counterparty, words in the notes or an amount.",
                                  "counterparty")
        return match_all, conditions

    def _category(self, raw, field: str) -> int | None:
        text = str(raw or "").strip()
        if not text:
            return None
        if not text.isdigit():
            raise ValidationError("Choose a category from the list.", field)
        category = self.categories.get(int(text))
        if not category.active or category.is_system or category.depth < 2:
            raise ValidationError("Choose a spending or income category.", field)
        return category.id

    def _parts(self, values: dict, category_id: int | None, conditions) -> list[Part]:
        parts = []
        for i in range(1, MAX_PARTS + 1):
            raw_category = str(values.get(f"part_category_{i}") or "").strip()
            raw_value = str(values.get(f"part_value_{i}") or "").strip()
            if not raw_category and not raw_value:
                continue
            field = f"part_value_{i}"
            if not raw_category or not raw_value:
                raise ValidationError("Give each part of the split a category and an amount or %.", field)
            part_category = self._category(raw_category, f"part_category_{i}")
            if self.categories.get(part_category).movement != Movement.OUTFLOW:
                raise ValidationError("Only money out is split: choose spending categories.", f"part_category_{i}")
            percent = raw_value.endswith("%")
            value = to_decimal(raw_value.rstrip("%").strip(), field)
            if value <= ZERO or (percent and value >= 100):
                raise ValidationError("Enter an amount above zero, or a percent under 100.", field)
            parts.append(Part(part_category, "percent" if percent else "fixed", value))
        if parts:
            if not category_id:
                raise ValidationError("Choose the category the rest of the split goes to.", "category_id")
            if self.categories.get(category_id).movement != Movement.OUTFLOW:
                raise ValidationError("Only money out is split: choose a spending category.", "category_id")
            if any(c.field == "direction" and c.value == "in" for c in conditions):
                raise ValidationError("Only money out is split.", "direction")
            if sum((p.value for p in parts if p.method == "percent"), ZERO) >= 100:
                raise ValidationError("The percents must leave something for the rest.", "part_value_1")
        return parts

    def _category_name(self, category_id: int) -> str:
        """The category's own name: a rule reads "Utilities & Bills", never "Personal › Utilities & Bills" (A16)."""
        try:
            return self.categories.get(category_id).name
        except NotFoundError:
            return "a removed category"

    def _account_name(self, account_id: str) -> str:
        try:
            account = self._account_id(account_id)
            return self.accounts.get(account).name if account is not None else "a removed account"
        except (NotFoundError, ValueError):
            return "a removed account"

    def _account_id(self, value: str) -> int | None:
        text = str(value)
        if text.isdigit():
            return int(text)
        return self.db.scalar("SELECT id FROM accounts WHERE code=?", (text,))
