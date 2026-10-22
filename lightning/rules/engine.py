"""Rules with conditions: pure functions over a transaction dict, no database inside.

A rule says "when these hold, file it here": conditions on the counterparty, notes, amount, account or
direction, joined by all or any; actions that set a category, add #tags to the notes, or split part of an
expense into other categories. Rules run most specific first (Actual Budget's scores: "is" beats "one of",
which beats a range, which beats "more than", which beats "contains"), then in the order they were made.
The first matching rule that sets a category decides it; every matching rule adds its tags.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from lightning.core.money import ascii_digits

FIELDS = ("counterparty", "notes", "amount", "account", "direction")
TEXT_OPS = ("is", "contains", "one_of")
AMOUNT_OPS = ("is", "about", "between", "more", "less")
ABOUT = Decimal("0.075")  # "about 300" means within 7.5% of it, as in Actual Budget
_SCORE = {"is": 10, "one_of": 9, "about": 5, "between": 5, "more": 1, "less": 1, "contains": 0}
_CENT = Decimal("0.01")


@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: str
    value_to: str | None = None


@dataclass(frozen=True)
class Part:
    """A share of an expense filed elsewhere: a fixed amount, or a percent of what the fixed parts leave."""
    category_id: int
    method: str     # "fixed" or "percent"
    value: Decimal


@dataclass(frozen=True)
class Rule:
    id: int
    conditions: tuple[Condition, ...]
    match_all: bool = True
    category_id: int | None = None
    tags: tuple[str, ...] = ()
    parts: tuple[Part, ...] = ()
    position: int = 0


@dataclass(frozen=True)
class Outcome:
    category_id: int | None = None
    rule_id: int | None = None          # the rule that chose the category
    tags: tuple[str, ...] = ()
    parts: tuple[Part, ...] = ()        # that rule's split, if any
    matched: tuple[int, ...] = field(default=())


def text_key(value: object) -> str:
    """Case, spacing and Arabic-Indic digits do not matter when names and notes are compared."""
    return " ".join(ascii_digits(str(value or "")).casefold().split())


def _amount(value: object) -> Decimal | None:
    try:
        return abs(Decimal(str(value)))
    except (ArithmeticError, ValueError):
        return None


def holds(condition: Condition, txn: dict) -> bool:
    """Whether one condition holds for a transaction. A field the transaction lacks never matches."""
    op, field_name = condition.op, condition.field
    if field_name in ("counterparty", "notes"):
        texts = txn.get("counterparty") if field_name == "counterparty" else [txn.get("notes")]
        texts = [text_key(t) for t in (texts or []) if text_key(t)]
        wanted = text_key(condition.value)
        if not texts or not wanted:
            return False
        if op == "is":
            return wanted in texts
        if op == "contains":
            return any(wanted in t for t in texts)
        if op == "one_of":
            options = {text_key(v) for v in condition.value.split(",") if text_key(v)}
            return any(t in options for t in texts)
        return False
    if field_name == "amount":
        amount, value = _amount(txn.get("amount")), _amount(condition.value)
        if amount is None or value is None:
            return False
        if op == "is":
            return amount == value
        if op == "about":
            return abs(amount - value) <= value * ABOUT
        if op == "between":
            top = _amount(condition.value_to)
            return top is not None and min(value, top) <= amount <= max(value, top)
        if op == "more":
            return amount > value
        if op == "less":
            return amount < value
        return False
    if field_name == "account":
        code = txn.get("account_code")
        if code is not None:
            # Older local profiles stored integer ids in account conditions.
            # Keep those rules working while all newly saved rules use codes.
            if condition.value.isdigit() and txn.get("account_id") is not None:
                return str(txn["account_id"]) == condition.value
            return str(code) == condition.value
        return txn.get("account_id") is not None and str(txn.get("account_id")) == condition.value
    if field_name == "direction":
        amount = txn.get("amount")
        try:
            direction = "in" if Decimal(str(amount)) > 0 else "out"
        except (ArithmeticError, ValueError):
            return False
        return direction == condition.value
    return False


def matches(rule: Rule, txn: dict) -> bool:
    if not rule.conditions:
        return False
    results = (holds(c, txn) for c in rule.conditions)
    return all(results) if rule.match_all else any(results)


def score(rule: Rule) -> int:
    """How specific a rule is: each condition by its kind, doubled when every condition is exact."""
    total = sum(_SCORE.get(c.op, 0) for c in rule.conditions)
    return total * 2 if rule.conditions and all(c.op == "is" for c in rule.conditions) else total


def rank(rules) -> list[Rule]:
    """Most specific first, then the order they were made."""
    return sorted(rules, key=lambda r: (-score(r), r.position, r.id))


def run(rules, txn: dict) -> Outcome:
    """What the rules say about one transaction: the category (and split) of the first matching rule that
    sets one, and the tags of every matching rule."""
    category_id = rule_id = None
    parts: tuple[Part, ...] = ()
    tags: list[str] = []
    matched = []
    for rule in rank(rules):
        if not matches(rule, txn):
            continue
        matched.append(rule.id)
        if category_id is None and rule.category_id:
            category_id, rule_id, parts = rule.category_id, rule.id, rule.parts
        tags += [t for t in rule.tags if t not in tags]
    return Outcome(category_id, rule_id, tuple(tags), parts, tuple(matched))


def split(amount: Decimal, parts, rest_category_id: int) -> list[tuple[int, Decimal]] | None:
    """An expense of ``amount`` shared out: fixed parts first, then percents of what they leave, and the rest
    to ``rest_category_id``. Each part is rounded to the piastre and the rest takes the difference, so the parts
    always add up to the amount. None when the parts would leave nothing for the rest."""
    amount = abs(Decimal(amount))
    out: dict[int, Decimal] = {}
    left = amount
    for part in (p for p in parts if p.method == "fixed"):
        value = Decimal(part.value).quantize(_CENT, ROUND_HALF_UP)
        out[part.category_id] = out.get(part.category_id, Decimal(0)) + value
        left -= value
    base = left
    for part in (p for p in parts if p.method == "percent"):
        value = (base * Decimal(part.value) / 100).quantize(_CENT, ROUND_HALF_UP)
        out[part.category_id] = out.get(part.category_id, Decimal(0)) + value
        left -= value
    if left <= 0 or not out:
        return None
    out[rest_category_id] = out.get(rest_category_id, Decimal(0)) + left
    return [(category_id, value) for category_id, value in out.items() if value > 0]
