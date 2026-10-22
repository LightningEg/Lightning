"""Atomic app workflows that combine several ordinary service writes."""
import hashlib
import json
from .spec import AMOUNT, DATE, FLAG, INT, MONTH, RATE, TEXT, Command, choice, listof, optional, ref

TABLES = ()  # These workflows touch tables owned by their underlying financial areas.


def _encode_activity(adapter, values):
    payment = values["payment"]
    if payment:
        item_id, due_date = payment.split("|", 1)
        payment = adapter.uid("planned_items", int(item_id)) + "|" + due_date
    return values | {"payment": payment}


def _decode_activity(adapter, values):
    payment = values["payment"]
    if payment:
        item_id, due_date = payment.split("|", 1)
        payment = str(adapter.local("planned_items", item_id)) + "|" + due_date
    return values | {"payment": payment}


def _activity_args(values):
    return values | {"reserve_amount": values["reserve_amount"] or ""}


COMMANDS = {
    "activity_review.apply": Command("activity_review.apply", dict(
        transaction_id=ref("transactions"), fingerprint=TEXT, category_id=optional(ref("categories")),
        payment=TEXT, reserve_id=optional(ref("cash_reserves")), reserve_amount=optional(AMOUNT)),
        target=("transactions", "transaction_id"), adapt=_activity_args,
        encode=_encode_activity, decode=_decode_activity),
    "salary_setup.set_up_salary": Command("salary_setup.set_up_salary", dict(
        account_id=ref("accounts"), amount=AMOUNT, payday=INT), creates="planned_items"),
    "journal_workflows.save_budget_settings": Command("journal_workflows.save_budget_settings", dict(
        income_categories=listof(ref("categories")), income_months=choice("3", "6"), manual_income=TEXT,
        exclusions=listof(ref("categories")), carryover=FLAG, carry_month=MONTH,
        recurring_shown=FLAG, income_from_recurring=FLAG, emergency_basis=optional(TEXT),
        fingerprint=TEXT)),
    "journal_workflows.setup_currencies": Command("journal_workflows.setup_currencies", dict(
        code=TEXT, extras=listof(TEXT), was_empty=FLAG)),
    "journal_workflows.save_fx_rate": Command("journal_workflows.save_fx_rate", dict(
        currency=TEXT, day=DATE, rate=RATE)),
    "journal_workflows.apply_bulk_budget": Command("journal_workflows.apply_bulk_budget", dict(
        month=MONTH, category_ids=listof(ref("categories")), action=choice("percentage", "average3", "average6"),
        percentage=TEXT, token=TEXT, fingerprint=TEXT), targets=("categories", "category_ids")),
    "journal_workflows.undo_bulk_budget": Command("journal_workflows.undo_bulk_budget", dict(key=TEXT, token=TEXT),
                                                  target=("settings", ("key",))),
    "journal_workflows.save_category_rule": Command("journal_workflows.save_category_rule", dict(
        category_id=ref("categories"), month=MONTH, mode=choice("fixed", "percentage", "average3"),
        value=TEXT, fingerprint=TEXT), target=("categories", "category_id")),
}


class JournalWorkflowService:
    """The route-level actions which would otherwise stop at their first staged write."""

    def __init__(self, container):
        self.c = container

    def budget_settings_fingerprint(self) -> str:
        c = self.c
        preferences = {key: c.settings.get(key) or "" for key in (
            "budget_income_categories", "budget_income_months", "budget_manual_monthly_income",
            "budget_one_off_exclusions", "budget_carryover_global", "budget_carryover_month",
            "budget_income_from_recurring", "emergency_fund_basis")}
        rows = [dict(row) for row in c.db.all("SELECT category_id,month,one_off,amount_e6,average_months,income_percent_e6 "
                                               "FROM budgets ORDER BY category_id,month")]
        categories = {item.id: item.code for item in c.categories.tree()}
        stable_rows = []
        for row in rows:
            code = categories.get(row.pop("category_id"), "")
            row["category"] = code
            stable_rows.append(row)
        stable_rows.sort(key=lambda row: (row["category"], row["month"], row["one_off"]))
        carry = [dict(row) for row in c.db.all("SELECT category_id,month,enabled FROM budget_carryover ORDER BY category_id,month")]
        stable_carry = []
        for row in carry:
            code = categories.get(row.pop("category_id"), "")
            row["category"] = code
            stable_carry.append(row)
        stable_carry.sort(key=lambda row: (row["category"], row["month"]))
        body = json.dumps([preferences, stable_rows, stable_carry], sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode()).hexdigest()

    def save_budget_settings(self, income_categories, income_months, manual_income, exclusions, carryover,
                             carry_month, recurring_shown, income_from_recurring, emergency_basis, fingerprint):
        c = self.c
        if self.budget_settings_fingerprint() != fingerprint:
            from lightning.core.errors import ValidationError
            raise ValidationError("Budget settings changed on the home. Review them and save again.")
        if recurring_shown:
            from lightning.budgeting.domain import INCOME_FROM_RECURRING
            c.settings.set(INCOME_FROM_RECURRING, "1" if income_from_recurring else "0")
        if emergency_basis:
            c.budgets.set_emergency_basis(emergency_basis)
        code_by_id = {item.id: item.code for item in c.categories.tree()}
        c.settings.set("budget_income_categories", json.dumps(sorted({code_by_id[cid] for cid in set(income_categories)})))
        c.settings.set("budget_income_months", income_months)
        c.settings.set("budget_manual_monthly_income", manual_income)
        c.settings.set("budget_one_off_exclusions", json.dumps(sorted({code_by_id[cid] for cid in set(exclusions)})))
        enabled = bool(carryover)
        c.settings.set("budget_carryover_global", "1" if enabled else "0")
        c.settings.set("budget_carryover_month", carry_month)
        tracked = set(c.budgets.amounts_for(carry_month))
        c.budgets.set_carryover(carry_month, {category_id: enabled for category_id in tracked})

    def setup_currencies(self, code, extras, was_empty):
        c = self.c
        if was_empty and c.accounts.list():
            from lightning.core.errors import ValidationError
            raise ValidationError("An account was added on the home. Review the profile currency before saving.")
        if was_empty:
            c.currencies.register(code)
            c.set_profile_currency(code)
        for extra in extras:
            c.currencies.register(extra)
        c.settings.set("setup_currencies_done", "1")

    def save_fx_rate(self, currency, day, rate):
        self.c.fx.save(currency, day, rate)
        self.c.reevaluations.process_due()

    def _portable_budget_snapshot(self, category_ids):
        c = self.c
        names = {item.id: item.code for item in c.categories.tree()}
        rows = c.budgets.snapshot_rows(category_ids)
        for row in rows:
            row.pop("id", None)
            row["category_code"] = names.get(row.pop("category_id"), "")
        return rows

    def _budget_rows_fingerprint(self, category_ids):
        c = self.c
        names = {item.id: item.code for item in c.categories.tree()}
        rows = [dict(row) for row in c.budgets.snapshot_rows(category_ids)]
        for row in rows:
            row.pop("id", None)
            row["category_code"] = names.get(row.pop("category_id"), "")
        rows.sort(key=lambda row: (row["category_code"], row["month"], row["one_off"]))
        body = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode()).hexdigest()

    def bulk_budget_fingerprint(self, category_ids):
        return self._budget_rows_fingerprint(category_ids)

    def apply_bulk_budget(self, month, category_ids, action, percentage, token, fingerprint):
        c = self.c
        if self._budget_rows_fingerprint(category_ids) != fingerprint:
            from lightning.core.errors import ValidationError
            raise ValidationError("These budget rules changed on the home. Review the categories and try again.")
        snapshot = self._portable_budget_snapshot(category_ids)
        with c.db.transaction():
            if action == "percentage":
                for category_id in category_ids:
                    c.budgets.set_income_percentage(category_id, month, percentage)
            else:
                period = 3 if action == "average3" else 6
                c.budgets.save_month(month, {category_id: "" for category_id in category_ids},
                                     average_months={category_id: period for category_id in category_ids})
            c.settings.set("budget_bulk_undo", json.dumps({"token": token, "month": month,
                "category_codes": sorted(self.c.categories.get(cid).code for cid in category_ids), "rows": snapshot,
                "after_fingerprint": self._budget_rows_fingerprint(category_ids)}))

    def undo_bulk_budget(self, key, token):
        if key != "budget_bulk_undo":
            from lightning.core.errors import ValidationError
            raise ValidationError("This bulk change can no longer be undone.")
        c = self.c
        snapshot = json.loads(c.settings.get("budget_bulk_undo") or "{}")
        if not token or token != snapshot.get("token"):
            from lightning.core.errors import ValidationError
            raise ValidationError("This bulk change can no longer be undone.")
        by_code = {item.code: item.id for item in c.categories.tree()}
        codes = snapshot.get("category_codes", [])
        if not codes or any(code not in by_code for code in codes):
            from lightning.core.errors import ValidationError
            raise ValidationError("A budget category is no longer available. The saved undo is no longer safe.")
        ids = [by_code[code] for code in codes if code in by_code]
        if self._budget_rows_fingerprint(ids) != snapshot.get("after_fingerprint"):
            from lightning.core.errors import ValidationError
            raise ValidationError("These budget rules changed after the bulk edit. The saved undo is no longer safe.")
        rows = []
        for saved in snapshot.get("rows", []):
            row = dict(saved)
            row["category_id"] = by_code.get(row.pop("category_code"), 0)
            row["id"] = None
            rows.append(row)
        with c.db.transaction():
            c.budgets.restore_rows(ids, rows)
            c.settings.set("budget_bulk_undo", "")

    def save_category_rule(self, category_id, month, mode, value, fingerprint):
        if self._budget_rows_fingerprint([category_id]) != fingerprint:
            from lightning.core.errors import ValidationError
            raise ValidationError("This budget rule changed on the home. Review it and try again.")
        c = self.c
        if mode == "percentage":
            c.budgets.set_income_percentage(category_id, month, value)
        elif mode == "average3":
            c.budgets.set_budget(category_id, month, "", average_months=3)
        else:
            c.budgets.set_budget(category_id, month, value)
        tracked = c.budgets._id_list("budget_tracked_categories") or set()
        tracked.add(category_id)
        codes = {c.categories.get(item).code for item in tracked}
        c.settings.set("budget_tracked_categories", json.dumps(sorted(codes)))
