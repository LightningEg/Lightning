"""Stable identity for a received salary's optional payday review."""
from __future__ import annotations

import hashlib
import json

from lightning.core.dates import fmt_date
from lightning.core.money import from_e6


def latest_settled_salary(db, on):
    """The latest posted transaction linked to a scheduled salary payment."""
    row = db.one(
        "SELECT p.id,p.transaction_id,p.due_date,p.amount_e6,t.date,t.ref FROM planned_payments p "
        "JOIN planned_items i ON i.id=p.planned_item_id "
        "JOIN categories cat ON cat.id=i.category_id "
        "JOIN transactions t ON t.id=p.transaction_id "
        "WHERE i.kind='INCOME' AND (cat.code='EXP.WORK.SALARY' OR cat.code LIKE 'EXP.WORK.SALARY.%') "
        "AND p.status='PAID' AND t.status='POSTED' AND t.type='IN' AND t.date<=? "
        "ORDER BY t.date DESC,p.due_date DESC,t.ref DESC LIMIT 1", (fmt_date(on),))
    return dict(row) if row else None


def salary_review(db, on):
    salary = latest_settled_salary(db, on)
    if not salary:
        return None
    # A transaction reference travels unchanged with the transaction, unlike local integer ids.
    return {"label": "Salary received", "detail": "Review bills, reserves, goals and safe to spend.",
            "href": "/payday", "action": "Review", "priority": 2,
            "source_version": [salary["ref"], salary["due_date"]],
            # Home's To do at a glance (IV-11E; workflows.review.glance): "Salary arrived · 45,000  Plan ›"
            "glance": {"name": "Salary arrived", "verb": "Plan", "amount": from_e6(salary["amount_e6"]), "when": "",
                       "n": None, "sa": ""}}


def payday_to_plan(db, settings, on):
    """The salary that arrived in ``on``'s month while its payday plan is not saved yet (3AY9, owner 2026-11-11: the
    strip shows from the salary's day until this month's plan is saved): {amount, date}, or None. Saving the payday
    allocation marks the salary's review reviewed (PaydayFunding), which ends it."""
    salary = latest_settled_salary(db, on)
    if not salary or salary["date"][:7] != fmt_date(on)[:7]:
        return None
    item = salary_review(db, on)
    state = settings.get("review_item_" + review_identity(item)) or ""
    if '"reviewed"' in state:
        return None
    return {"amount": from_e6(salary["amount_e6"]), "date": salary["date"]}


def review_identity(item):
    """The inbox identity also used when an accepted payday allocation handles its reminder."""
    facts = {key: item.get(key) for key in ("label", "detail", "href", "priority", "post", "source_version")}
    return hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()
