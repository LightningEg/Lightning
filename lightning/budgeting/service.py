"""Public API of the budgeting module: the month view (budget vs actual) and saving budgets."""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal
import math
from datetime import timedelta
import json

from lightning.categories.domain import Category, CategoryFamily, Movement, Scope
from lightning.categories.service import CategoryService
from lightning.core.dates import month_of, parse_month
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, check_places, fmt, from_e6, to_decimal
from lightning.database.connection import Database
from lightning.database.settings import raw_setting
from lightning.reporting.service import ReportingService

from .domain import (EMERGENCY_BASES, INCOME_FROM_RECURRING, BudgetFillProposal, BudgetFillRow, BudgetLine, BudgetMonth,
                     BudgetSection, EmergencyFund, IncomeAverage, SpendingAverage)
from .repository import BudgetRepository

SECTION_NAMES = {Scope.PERSONAL: "Personal", Scope.WORK: "Work"}


OVER_PLAN_MARGIN = Decimal(50)  # a category a few pounds over its plan is not worth a move


MAX_BUDGET = 100_000_000  # EGP a month for one category; above it is a typo, not a plan


class BudgetService:
    def __init__(self, db: Database, categories: CategoryService, reporting: ReportingService):
        self.db = db
        self.repo = BudgetRepository(db)
        self.categories = categories
        self.reporting = reporting
        # Set by the composition root: month -> {category_id: loan payments scheduled that month}, and
        # month -> {category_id: {"amount", "items"}} for bills and subscriptions. A category with no
        # budget rule is planned at exactly what is scheduled (owner decision 2026-10-05: bills as loans).
        self.scheduled_loans = lambda month: {}
        self.scheduled_bills = lambda month: {}
        self.scheduled_income = lambda: None
        self.reserve_goal_needs = lambda month: []

    def first_owned_spending_date(self) -> str | None:
        """Earliest posted, personally owned entry in a spending category."""
        return self.db.scalar(
            "SELECT MIN(le.date) FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
            "WHERE t.status='POSTED' AND le.category_id IS NOT NULL AND le.owner_id IS NULL"
        )

    def snapshot_rows(self, category_ids: list[int]) -> list[dict]:
        """Capture all stored rules for an undoable bulk edit."""
        if not category_ids:
            return []
        marks = ",".join("?" for _ in category_ids)
        return [dict(row) for row in self.db.all(
            f"SELECT * FROM budgets WHERE category_id IN ({marks})", tuple(category_ids)
        )]

    def restore_rows(self, category_ids: list[int], rows: list[dict]) -> None:
        """Restore the exact rules captured before a bulk edit."""
        if not category_ids:
            return
        columns = ("id", "category_id", "month", "one_off", "amount_e6", "created_at", "updated_at",
                   "average_months", "income_percent_e6")
        marks = ",".join("?" for _ in category_ids)
        names = ",".join(columns)
        values = ",".join("?" for _ in columns)
        with self.db.transaction():
            self.db.execute(f"DELETE FROM budgets WHERE category_id IN ({marks})", tuple(category_ids))
            for row in rows:
                self.db.execute(f"INSERT INTO budgets({names}) VALUES ({values})",
                                tuple(row.get(key) for key in columns))

    # ------------------------------------------------------------------ reading
    def scheduled_payments(self, month: str) -> dict[int, Decimal]:
        """Loan payments, bills and subscriptions scheduled in a month, by spending category."""
        out = {cid: amount for cid, amount in self.scheduled_loans(month).items() if amount}
        for cid, data in self.scheduled_bills(month).items():
            if data["amount"]:
                out[cid] = out.get(cid, ZERO) + data["amount"]
        return out

    def bill_lines(self, month: str) -> dict[int, Decimal]:
        """Categories planned from scheduled bills and subscriptions because no budget rule is set for them."""
        explicit = self.amounts_for(month, loans=False)
        return {cid: data["amount"] for cid, data in self.scheduled_bills(month).items()
                if data["amount"] and cid not in explicit}

    def loan_lines(self, month: str) -> dict[int, Decimal]:
        """Categories planned from scheduled loan payments because no budget rule is set for them."""
        explicit = self.amounts_for(month, loans=False)
        return {cid: amount for cid, amount in self.scheduled_loans(month).items()
                if amount and cid not in explicit}

    def below_scheduled(self, month: str) -> list[dict]:
        """Categories whose own rule plans less than the bills, subscriptions and loan payments scheduled
        in them that month: the plan cannot hold what is already promised."""
        explicit = self.amounts_for(month, loans=False)
        names = {category.id: category.name for category in self.categories.tree()}
        rows = []
        for cid, scheduled in self.scheduled_payments(month).items():
            planned = explicit.get(cid, (None,))[0]
            if planned is not None and planned < scheduled:
                rows.append({"category_id": cid, "name": names.get(cid, ""), "planned": planned, "scheduled": scheduled})
        return rows

    def over_twice(self, month: str) -> list[dict]:
        """Categories over their own plan (by OVER_PLAN_MARGIN or more) in both of the two completed months
        before `month`, with how much more a month they needed (the larger overspend, rounded up to 50) and, when one exists, a category
        whose plan was left with at least that much in both months to move it from."""
        start = parse_month(month)[0]
        earlier = month_of(start - timedelta(days=1))
        months = (month_of(parse_month(earlier)[0] - timedelta(days=1)), earlier)
        views = [{line.category_id: line for section in self.month_view(key).sections for line in section.lines}
                 for key in months]
        now = {line.category_id: line for section in self.month_view(month).sections for line in section.lines}

        def own(line) -> bool:  # a rule you set, not a line planned from loans or bills
            return line is not None and line.depth >= 2 and line.direct is not None and line.remaining is not None

        rows = []
        for cid, line in views[1].items():
            before = views[0].get(cid)
            if not (own(line) and own(before) and own(now.get(cid))
                    and min(-line.remaining, -before.remaining) >= OVER_PLAN_MARGIN):
                continue
            short = max(-line.remaining, -before.remaining)
            if now[cid].direct - line.direct >= short:  # this month's plan already has what it lacked
                continue
            amount = Decimal(math.ceil(short / 50) * 50)
            related = lambda other: other.code.startswith(line.code + ".") or line.code.startswith(other.code + ".")
            donors = [(min(views[0][d].remaining, other.remaining), other) for d, other in views[1].items()
                      if d != cid and own(other) and own(views[0].get(d)) and own(now.get(d)) and not related(other)
                      and min(views[0][d].remaining, other.remaining) >= amount and now[d].direct >= amount]
            donor = max(donors, key=lambda pair: pair[0])[1] if donors else None
            rows.append({"category_id": cid, "name": line.name, "months": months, "amount": amount,
                         "plan": now[cid].direct, "from_id": donor.category_id if donor else None,
                         "from_name": donor.name if donor else None,
                         "from_plan": now[donor.category_id].direct if donor else None})
        return rows

    def move_room(self, month: str, to_id: int, from_id: int, amount: object) -> None:
        """Move plan from one category to another from `month` on: both keep fixed amounts, the total is unchanged."""
        value = to_decimal(amount, "amount")
        if value <= 0:
            raise ValidationError("Move an amount above zero.", "amount")
        if to_id == from_id:
            raise ValidationError("Choose two different categories.", "category")
        current = self.amounts_for(month, loans=False)
        give, take = current.get(from_id, (None,))[0], current.get(to_id, (None,))[0]
        if give is None or take is None:
            raise ValidationError("Both categories need a plan of their own this month.", "category")
        if give < value:
            raise ValidationError(f"{self.categories.get(from_id).name} plans only {fmt(give, 0)} this month.", "amount")
        with self.db.transaction():
            self.save_month(month, {to_id: take + value, from_id: give - value})

    @request_cached  # has_plan, loan_lines, bill_lines and month_view all ask for it
    def amounts_for(self, month: str, loans: bool = True) -> dict[int, tuple[Decimal | None, bool, int | None, Decimal | None]]:
        """Effective amount, one-off flag, average window, and income percentage.

        With ``loans``, a category that has scheduled loan payments, bills or subscriptions and no rule
        of its own is planned at what is due that month (Planned = scheduled payments)."""
        parse_month(month)
        repeating: dict[int, tuple[Decimal | None, int | None, Decimal | None]] = {}
        one_off: dict[int, tuple[Decimal | None, int | None, Decimal | None]] = {}
        for e in self.repo.entries_up_to(month):  # ordered by category, month
            if e.one_off:
                one_off[e.category_id] = (e.amount, e.average_months, e.income_percent)
            else:
                repeating[e.category_id] = (e.amount, e.average_months, e.income_percent)
        result = {cid: (amount, False, period, percent) for cid, (amount, period, percent) in repeating.items()}
        result.update({cid: (amount, True, period, percent) for cid, (amount, period, percent) in one_off.items()})
        result = {cid: v for cid, v in result.items() if v[0] is not None or v[2] is not None or v[3] is not None}
        for cid, (amount, oneoff, period, percent) in list(result.items()):
            if percent is not None:
                income = self.budgeting_income(month)
                amount = None if income is None else (income * percent / Decimal(100)).quantize(Decimal("0.01"))
            elif period:
                cats = [c for c in self.categories.tree(Movement.OUTFLOW) if not c.is_root]
                children = {}
                for cat in cats:
                    if cat.parent_id:
                        children.setdefault(cat.parent_id, []).append(cat.id)
                amount = self._rolling_average(cid, month, period, children, {})
            result[cid] = (amount, oneoff, period, percent)
        if loans:
            for cid, amount in self.scheduled_payments(month).items():
                if amount and cid not in result:
                    result[cid] = (amount, False, None, None)
        return result

    # -- category flags kept with the budget settings (one list each, edited from Categories or Budget)
    def _id_list(self, key: str) -> set[int] | None:
        raw = raw_setting(self.db, key)
        if raw is None:
            return None
        try:
            values = json.loads(raw)
            ids = set()
            by_code = {category.code: category.id for category in self.categories.tree()}
            for value in values:
                try:
                    ids.add(int(value))
                except (ValueError, TypeError):
                    if str(value) in by_code:
                        ids.add(by_code[str(value)])
            return ids
        except (ValueError, TypeError):
            return set()

    def _save_id_list(self, key: str, ids: set[int]) -> None:
        from lightning.database.settings import SettingsStore
        SettingsStore(self.db).set(key, json.dumps(sorted(ids)))

    def recurring_income_ids(self) -> set[int]:
        """Income categories you can count on (salary, rent received): the income average and the
        forecast use these. Bonuses and other irregular income are left out."""
        chosen = self._id_list("budget_income_categories")
        if chosen is None:
            chosen = {category.id for category in self.categories.tree() if category.income_class is not None
                      and category.code != "EXP.WORK.BONUS" and (category.family == CategoryFamily.WORK or any(
                          word in category.name.casefold() for word in ("salary", "wage", "pay")))}
        return chosen

    def set_recurring_income(self, category_id: int, recurring: bool) -> None:
        ids = self.recurring_income_ids()
        ids = ids | {category_id} if recurring else ids - {category_id}
        self._save_id_list("budget_income_categories", ids)

    def one_off_ids(self, with_children: bool = True) -> set[int]:
        """Expense categories marked one-off: their spending stays in cash flow and analysis but is
        left out of the budget's totals and of every estimate."""
        ids = self._id_list("budget_one_off_exclusions") or set()
        if with_children:
            for category_id in list(ids):
                try:
                    ids |= {child.id for child in self.categories.descendants(category_id)}
                except NotFoundError:  # a deleted category; any other error must not change the budget unseen (9K)
                    continue
        return ids

    def set_one_off(self, category_id: int, one_off: bool) -> None:
        ids = self.one_off_ids(with_children=False)
        ids = ids | {category_id} if one_off else ids - {category_id}
        self._save_id_list("budget_one_off_exclusions", ids)

    def budgeting_income(self, month: str) -> Decimal | None:
        """Average monthly income for a month's budget (see income_average)."""
        return self.income_average(month).amount

    @request_cached(deep=True)
    def income_average(self, month: str) -> IncomeAverage:
        """Average monthly income: owned income in the chosen income categories, averaged over
        the last 3 (or 6) completed months before `month` that had any. A manual amount in
        Settings replaces the average. Before any completed month has income, the income set up in
        Cash planning › Recurring stands in, so a new plan is checked from day one. The budget, reserves
        and the cash forecast all use this."""
        chosen = self.recurring_income_ids()
        categories = self.categories.tree()
        by_id = {category.id: category for category in categories}
        lookback = self._average_months()
        manual = raw_setting(self.db, "budget_manual_monthly_income")
        if manual:
            return IncomeAverage(to_decimal(manual, "manual_income"), 0, lookback, "", "", True)
        if raw_setting(self.db, INCOME_FROM_RECURRING) == "1":
            scheduled = self.scheduled_income()  # chosen after a raise: plan with what Recurring expects
            if scheduled is not None:
                return IncomeAverage(scheduled, 0, lookback, "", "", False, scheduled=True)
        end = parse_month(month)[0] - timedelta(days=1)
        last_month = month_of(end)
        observed = []
        for _ in range(lookback):
            start, _ = parse_month(month_of(end))
            if chosen:
                marks = ",".join("?" for _ in chosen)
                rows = self.db.all(
                    "SELECT le.category_id,SUM(le.amount_base_e6) AS total_e6 "
                    "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                    "LEFT JOIN planned_payments pp ON pp.transaction_id=t.id AND pp.status='PAID' "
                    "LEFT JOIN planned_items pi ON pi.id=pp.planned_item_id AND pi.kind='INCOME' "
                    "WHERE t.status='POSTED' AND le.effect='INFLOW' AND le.owner_id IS NULL "
                    "AND le.category_id NOT IN (SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY') "
                    f"AND le.category_id IN ({marks}) "
                    "AND CASE WHEN pi.id IS NOT NULL THEN substr(pp.due_date,1,7) "
                    "ELSE substr(le.date,1,7) END=? GROUP BY le.category_id",
                    (*chosen, month_of(end)),
                )
            else:
                rows = []
            included = [row for row in rows if by_id.get(row["category_id"]) and
                        by_id[row["category_id"]].income_class is not None and
                        by_id[row["category_id"]].code != "EXP.INVEST" and
                        not any(word in by_id[row["category_id"]].code.casefold()
                                for word in ("sale", "opening", "valuation"))]
            if included:
                observed.append(sum((from_e6(row["total_e6"]) for row in included), ZERO))
            end = start - timedelta(days=1)
        if not observed:
            scheduled = self.scheduled_income()
            if scheduled is not None:
                return IncomeAverage(scheduled, 0, lookback, "", "", False, scheduled=True)
            return IncomeAverage(None, 0, lookback, month_of(end + timedelta(days=1)), last_month, False)
        amount = (sum(observed, ZERO) / len(observed)).quantize(Decimal("0.01"))
        return IncomeAverage(amount, len(observed), lookback, month_of(end + timedelta(days=1)), last_month, False)

    def _average_months(self) -> int:
        """3 or 6 completed months, from Settings › Budget; both averages use it."""
        return 6 if str(raw_setting(self.db, "budget_income_months")) == "6" else 3

    def spending_average(self, month: str) -> SpendingAverage:
        """Average monthly spending: money out in budget categories (investments and one-off categories
        left out, as in the budget), averaged over the same last 3 (or 6) completed months before
        `month` as Average monthly income, counting only months that had any."""
        lookback, one_off = self._average_months(), self.one_off_ids()
        end = parse_month(month)[0] - timedelta(days=1)
        last_month = month_of(end)
        observed = []
        for _ in range(lookback):
            start, finish = parse_month(month_of(end))
            spent = [value for cid, value in self.owned_spending(start, finish).items() if cid not in one_off]
            if spent:
                observed.append(sum(spent, ZERO))
            end = start - timedelta(days=1)
        amount = (sum(observed, ZERO) / len(observed)).quantize(Decimal("0.01")) if observed else None
        return SpendingAverage(amount, len(observed), lookback, month_of(end + timedelta(days=1)), last_month)

    def emergency_basis(self) -> str:
        """What the emergency fund is counted in: "spending" (the default) or "income"."""
        value = raw_setting(self.db, "emergency_fund_basis")
        return value if value in EMERGENCY_BASES else "spending"

    def set_emergency_basis(self, basis: str) -> None:
        if basis not in EMERGENCY_BASES:
            raise ValidationError("Count the emergency fund in months of income or of spending.", "emergency_basis")
        from lightning.database.settings import SettingsStore
        SettingsStore(self.db).set("emergency_fund_basis", basis)

    def emergency_fund(self, month: str, set_aside: Decimal | None) -> EmergencyFund:
        """The emergency fund in months of the chosen average, and its six-month target."""
        basis = self.emergency_basis()
        average = self.income_average(month) if basis == "income" else self.spending_average(month)
        return EmergencyFund(set_aside, basis, average)

    def has_plan(self, month: str) -> bool:
        return bool(self.amounts_for(month, loans=False))

    @request_cached(deep=True)
    def month_view(self, month: str) -> BudgetMonth:
        first, last = parse_month(month)
        direct = self.amounts_for(month)
        from_loans = self.loan_lines(month)
        from_bills = self.bill_lines(month)
        spent = self.owned_spending(first, last)
        cats = [c for c in self.categories.tree(Movement.OUTFLOW) if not c.is_root
                and c.family != CategoryFamily.INVESTMENT]  # investments are never budget spending
        by_id = {c.id: c for c in cats}
        children: dict[int, list[int]] = {}
        for c in cats:
            if c.parent_id in by_id:
                children.setdefault(c.parent_id, []).append(c.id)

        one_offs = self.one_off_ids()
        actual: dict[int, Decimal] = {}
        planned_actual: dict[int, Decimal] = {}
        budget: dict[int, Decimal | None] = {}
        average_cache: dict[tuple[int, int], Decimal | None] = {}
        for c in reversed(cats):  # children before parents
            kids = children.get(c.id, [])
            # A one-off child keeps its own actual but does not add to its parent's (unless it has a plan).
            actual[c.id] = spent.get(c.id, ZERO) + sum((actual[k] for k in kids
                                                        if k not in one_offs or k in direct), ZERO)
            if c.id in direct:
                amount, _, period, percent = direct[c.id]
                budget[c.id] = amount
            else:
                kid_budgets = [budget[k] for k in kids if budget[k] is not None]
                budget[c.id] = sum(kid_budgets, ZERO) if kid_budgets else None
            if budget[c.id] is not None and c.id in direct:
                planned_actual[c.id] = actual[c.id]
            else:
                planned_actual[c.id] = sum((planned_actual[k] for k in kids), ZERO)

        def ancestor_has_direct(c: Category) -> bool:
            parent = by_id.get(c.parent_id)
            while parent is not None:
                if parent.id in direct:
                    return True
                parent = by_id.get(parent.parent_id)
            return False

        sections = {scope: BudgetSection(name) for scope, name in SECTION_NAMES.items()}
        sections["INVESTMENT"] = BudgetSection("Investment")
        warnings: list[str] = []
        carryover_settings = self.repo.carryover_settings(month)
        opening_carryovers = {category_id: self._opening_carryover(category_id, month,
                                                                    carryover_settings.get(category_id, False) and category_id in direct,
                                                                    children)
                              for category_id in carryover_settings if carryover_settings[category_id]}
        for category in reversed(cats):
            if category.id not in direct:
                opening_carryovers[category.id] = sum(
                    (opening_carryovers.get(child_id, ZERO) for child_id in children.get(category.id, [])), ZERO)
        for c in cats:
            section = sections["INVESTMENT"] if c.family == CategoryFamily.INVESTMENT else sections[c.scope or Scope.PERSONAL]
            covered = ancestor_has_direct(c)
            if c.id in one_offs and c.id not in direct:
                if c.parent_id not in one_offs:
                    section.one_off += actual[c.id]
            elif c.id not in direct and not covered:
                section.unbudgeted += spent.get(c.id, ZERO)
            shows = c.active or actual[c.id] != ZERO or c.id in direct
            if c.is_system and actual[c.id] == ZERO and c.id not in direct:
                shows = False
            if not shows:
                continue
            amount, one_off, average_months, income_percent = direct.get(c.id, (None, False, None, None))
            section.lines.append(BudgetLine(
                category_id=c.id, code=c.code, name=c.name, depth=c.depth, direct=amount, one_off=one_off,
                average_months=average_months, budget=budget[c.id], actual=actual[c.id],
                planned_actual=planned_actual[c.id], covered=covered,
                opening_carryover=opening_carryovers.get(c.id, ZERO),
                carryover_enabled=carryover_settings.get(c.id, False),
                income_percent=income_percent, from_loans=c.id in from_loans, from_bills=c.id in from_bills,
            ))
            kids_total = sum(((budget[k] or ZERO) + opening_carryovers.get(k, ZERO)
                              for k in children.get(c.id, []) if budget[k] is not None), ZERO)
            parent_available = (budget[c.id] or ZERO) + opening_carryovers.get(c.id, ZERO)
            if budget[c.id] is not None and kids_total > parent_available:
                warnings.append(f"{self.categories.display_name(c.id)}: its categories add up to "
                                f"{fmt(kids_total)}, more than its budget / available limit of {fmt(parent_available)}.")
        income = self.reporting.cash_flow(first, last).inflows
        return BudgetMonth(month, [s for s in sections.values() if s.lines], income, warnings)

    def suggested_plan(self, month: str) -> dict[int, Decimal]:
        """Return stable, rounded suggestions for categories with recent spending."""
        parse_month(month)
        cats = [c for c in self.categories.tree(Movement.OUTFLOW) if not c.is_root]
        children: dict[int, list[int]] = {}
        by_id = {c.id: c for c in cats}
        for category in cats:
            if category.parent_id in by_id:
                children.setdefault(category.parent_id, []).append(category.id)
        cache: dict[tuple[int, int], Decimal | None] = {}
        result = {}
        for category in cats:
            if children.get(category.id):
                continue
            avg = self._rolling_average(category.id, month, 3, children, cache)
            # Whole EGP: a plan of 67.50 shows as 68, and 80 spent beside it would read "13 over".
            avg = avg.quantize(Decimal("1"), ROUND_HALF_UP) if avg is not None else None
            if avg is not None and avg > ZERO:
                result[category.id] = avg
        return result

    def fill_proposal(self, month: str, source: str) -> BudgetFillProposal:
        """Build a read-only month-fill preview; all returned amounts are base limits in EGP."""
        first, _ = parse_month(month)
        if source not in {"last_month", "schedule", "goal"}:
            raise ValidationError("Choose Last month, Schedule, or Goal as the fill source.", "source")
        categories = [c for c in self.categories.tree(Movement.OUTFLOW)
                      if not c.is_root and c.family != CategoryFamily.INVESTMENT]
        by_id = {c.id: c for c in categories}
        current = self.amounts_for(month, loans=False)
        current_rules = {cid: rule for cid, rule in current.items() if cid in by_id}
        candidates: dict[int, tuple[Decimal | None, str]] = {}

        if source == "last_month":
            previous = month_of(first - timedelta(days=1))
            for category_id, (amount, _, period, percent) in self.amounts_for(previous, loans=False).items():
                if category_id in by_id:
                    detail = (f"{period}-month average" if period else
                              f"{fmt(percent)}% of income" if percent is not None else "fixed")
                    candidates[category_id] = (amount, f"From {previous} · {detail}")
        elif source == "schedule":
            for category_id, data in self.scheduled_bills(month).items():
                if category_id in by_id and data["amount"] > ZERO:
                    names = ", ".join(dict.fromkeys(data["items"]))
                    candidates[category_id] = (data["amount"], f"Scheduled: {names}")
        else:
            rows = tuple(BudgetFillRow(
                category_id=None,
                category_name=f"{item['name']} · reserve goal",
                source="Goal",
                amount=item["amount"],
                conflict="Savings goals are managed in Reserves, not in spending budgets.",
                selectable=False,
                note=f"Set aside monthly · due {item['due_date']}",
            ) for item in self.reserve_goal_needs(month))
            return BudgetFillProposal(month, source, rows)

        loans = self.scheduled_payments(month)
        rows = []
        for category_id, (amount, note) in candidates.items():
            rule = current_rules.get(category_id)
            current_amount = rule[0] if rule else None
            current_rule = self._fill_rule_name(rule) if rule else ""
            same = rule is not None and amount is not None and current_amount == amount
            auto_loan = loans.get(category_id, ZERO) if rule is None else ZERO
            conflict = ""
            if same:
                conflict = ("Already using last month's plan" if source == "last_month"
                            else "Matches the current base limit.")
            elif rule is not None:
                conflict = f"Current limit: {current_rule}. Applying replaces it for {month} only."
            elif auto_loan:
                conflict = (f"{fmt(auto_loan)} of scheduled payments are already planned automatically. "
                            "Applying this amount would replace that automatic line.")
            rows.append(BudgetFillRow(
                category_id=category_id,
                category_name=self.categories.display_name(category_id),
                source="Last month" if source == "last_month" else "Schedule",
                amount=amount,
                current_amount=current_amount,
                current_rule=current_rule,
                conflict=conflict,
                selectable=amount is not None,
                selected=amount is not None and rule is None and not auto_loan,
                already_using_last_month=source == "last_month" and same,
                note=note,
            ))

        # Forecast child allocations against every direct parent ceiling without changing it.
        direct = {cid: rule[0] for cid, rule in current_rules.items() if rule[0] is not None}
        direct.update({cid: amount for cid, (amount, _) in candidates.items() if amount is not None})
        direct.update({cid: amount for cid, amount in loans.items() if cid not in current_rules})
        children: dict[int, list[int]] = {}
        for category in categories:
            if category.parent_id in by_id:
                children.setdefault(category.parent_id, []).append(category.id)

        def allocated(category_id: int) -> Decimal:
            if category_id in direct:
                return direct[category_id]
            return sum((allocated(child) for child in children.get(category_id, [])), ZERO)

        for parent_id, child_ids in children.items():
            ceiling = direct.get(parent_id)
            if ceiling is None:
                continue
            child_total = sum((allocated(child_id) for child_id in child_ids), ZERO)
            if child_total <= ceiling:
                continue
            warning = (f"Child limits total {fmt(child_total)}, above the "
                       f"{self.categories.display_name(parent_id)} ceiling of {fmt(ceiling)}.")
            affected = {parent_id, *self._descendant_ids(parent_id, children)}
            rows = [replace(row, conflict=" ".join(x for x in (row.conflict, warning) if x), selected=False)
                    if row.category_id in affected else row for row in rows]
        rows.sort(key=lambda row: (by_id[row.category_id].sort_order, row.category_name.casefold()))
        return BudgetFillProposal(month, source, tuple(rows))

    @staticmethod
    def _fill_rule_name(rule) -> str:
        amount, _, period, percent = rule
        if percent is not None:
            return f"{fmt(percent)}% of income" + (f" (currently {fmt(amount)})" if amount is not None else "")
        if period:
            return f"{period}-month average" + (f" (currently {fmt(amount)})" if amount is not None else "")
        return f"{fmt(amount)} fixed" if amount is not None else "No resolved monthly amount"

    @staticmethod
    def _descendant_ids(category_id: int, children: dict[int, list[int]]) -> set[int]:
        descendants: set[int] = set()
        pending = list(children.get(category_id, []))
        while pending:
            child = pending.pop()
            if child in descendants:
                continue
            descendants.add(child)
            pending.extend(children.get(child, []))
        return descendants

    def owned_spending(self, start, end) -> dict[int, Decimal]:
        # Report queries already filter to posted, user-owned categorized ledger
        # effects; investment buys, transfers, and revaluations have no outflow
        # expense effect and therefore do not appear as spending here.
        # Investment fees and moves into investments are not household spending, so the budget never
        # counts them (cash flow and the Overview still do).
        investment = self._investment_ids()
        return {cid: v for cid, v in self.reporting.money_out_by_category(start, end).items() if cid not in investment}

    def _investment_ids(self) -> set[int]:
        return {c.id for c in self.categories.tree() if c.family == CategoryFamily.INVESTMENT}

    def set_carryover(self, month: str, settings: dict[int, bool]) -> int:
        parse_month(month)
        changed = 0
        current = self.repo.carryover_settings(month)
        with self.db.transaction():
            for category_id, enabled in settings.items():
                self._budgetable(category_id)
                if enabled and category_id not in self.amounts_for(month):
                    raise ValidationError("Carryover needs a monthly limit on that category or group first.")
                if current.get(category_id, False) == enabled:
                    continue
                self.repo.set_carryover(category_id, month, enabled)
                changed += 1
        return changed

    def _opening_carryover(self, category_id: int, month: str, enabled_now: bool,
                           children: dict[int, list[int]]) -> Decimal:
        if not enabled_now:
            return ZERO
        first, _ = parse_month(month)
        earliest = self.repo.first_carryover_month(category_id, month)
        if not earliest:
            return ZERO
        cursor = parse_month(earliest)[0]
        settings = self.repo.carryover_settings_up_to(month, category_id)
        active = False
        setting_index = 0
        balance = ZERO
        reset_month = self.repo.reset_month(category_id, month)
        if reset_month == month:
            return ZERO
        enabling_now = bool(settings and settings[-1] == (month, True))
        preceding_month = month_of(first - timedelta(days=1))
        descendants = {category_id}
        pending = [category_id]
        while pending:
            kids = children.get(pending.pop(), [])
            descendants.update(kids)
            pending.extend(kids)
        # One-off spending is left out of each month's budget, so it is left out of what carries over
        # too (audit 2026-10-05 #11).
        descendants -= self.one_off_ids()
        while cursor < first:
            current_month = month_of(cursor)
            if reset_month == current_month:
                balance = ZERO
            while setting_index < len(settings) and settings[setting_index][0] <= current_month:
                active = settings[setting_index][1]
                setting_index += 1
            next_month = month_of(parse_month(current_month)[1] + timedelta(days=1))
            # An opt-in effective in the next month immediately carries this
            # month's final result, even if carryover was previously off.
            if setting_index < len(settings) and settings[setting_index] == (next_month, True):
                active = True
            if enabling_now and current_month == preceding_month:
                active = True
            next_cursor = (parse_month(current_month)[1] + timedelta(days=1))
            if active:
                direct = self.amounts_for(current_month).get(category_id)
                if direct:
                    amount, _, period, percent = direct
                    if period:
                        amount = self._rolling_average(category_id, current_month, period, children, {})
                    elif percent is not None:
                        amount = self.budgeting_income(current_month)
                        if amount is not None:
                            amount = amount * percent / Decimal(100)
                    start, end = parse_month(current_month)
                    spent = self.owned_spending(start, end)
                    actual = sum((spent.get(cid, ZERO) for cid in descendants), ZERO)
                    balance = (amount or ZERO) + balance - actual
                else:
                    balance = ZERO
            else:
                balance = ZERO
            cursor = next_cursor
        return balance

    # ------------------------------------------------------------------ writing
    def set_budget(self, category_id: int, month: str, amount: object, only_this_month: bool = False,
                   average_months: int | None = None) -> bool:
        return self.save_month(month, {category_id: amount}, only_this_month,
                               {category_id: average_months} if average_months else None) > 0

    def save_month(self, month: str, amounts: dict[int, object], only_this_month: bool = False,
                   average_months: dict[int, object] | None = None) -> int:
        """Save several budget cells at once (the budget page). Returns how many changed."""
        parse_month(month)
        current = self.amounts_for(month)
        average_months = average_months or {}
        changed = 0
        carryover_now = self.repo.carryover_settings(month)
        with self.db.transaction():
            for category_id, raw in amounts.items():
                category = self._budgetable(category_id)
                period = self._average_period(average_months.get(category_id))
                value = None if period else self._parse(raw, category)
                old = current.get(category_id, (None, False, None, None))
                if old[0] == value and old[2] == period and old[3] is None:
                    continue
                before = self._repeating_before(category_id, month)
                desired = (value, period)
                if only_this_month:
                    if desired == self._repeating_through(category_id, month):
                        self.repo.delete(category_id, month, one_off=True)
                    else:
                        self.repo.upsert(category_id, month, True, value, period)
                else:
                    self.repo.delete(category_id, month, one_off=True)
                    if desired == before:
                        self.repo.delete(category_id, month, one_off=False)  # same as before: nothing to store
                    else:
                        self.repo.upsert(category_id, month, False, value, period)
                if value is None and period is None and carryover_now.get(category_id, False):
                    self.repo.set_carryover(category_id, month, False)
                changed += 1
        return changed

    def apply_fill(self, month: str, amounts: dict[int, object]) -> int:
        """Apply selected fill amounts as one atomic, one-month-only edit."""
        parse_month(month)
        if not amounts:
            raise ValidationError("Choose at least one category to fill.", "categories")
        with self.db.transaction():
            return self.save_month(month, amounts, only_this_month=True)

    # ------------------------------------------------------------------ helpers
    def _repeating_before(self, category_id: int, month: str) -> tuple[Decimal | None, int | None]:
        rows = [e for e in self.repo.entries_up_to(month) if e.category_id == category_id and not e.one_off
                and e.month < month]
        return (rows[-1].amount, rows[-1].average_months) if rows else (None, None)

    def _repeating_through(self, category_id: int, month: str) -> tuple[Decimal | None, int | None]:
        rows = [e for e in self.repo.entries_up_to(month) if e.category_id == category_id and not e.one_off]
        return (rows[-1].amount, rows[-1].average_months) if rows else (None, None)

    def _rolling_average(self, category_id: int, month: str, months: int,
                         children: dict[int, list[int]], cache: dict[tuple[int, int], Decimal | None]) -> Decimal | None:
        key = (category_id, months)
        if key in cache:
            return cache[key]
        tree = {category_id} | self._descendant_ids(category_id, children)
        cache[key] = self._tree_average(tree, self._completed_months(month, months))[0]
        return cache[key]

    def _completed_months(self, month: str, months: int) -> list[dict[int, Decimal]]:
        """Owned spending by category in each of the completed months before `month`, newest first."""
        spending, cursor = [], parse_month(month)[0]
        for _ in range(months):
            start, end = parse_month((cursor - timedelta(days=1)).strftime("%Y-%m"))
            spending.append(self.owned_spending(start, end))
            cursor = start
        return spending

    @staticmethod
    def _tree_average(tree: set[int], spending: list[dict[int, Decimal]]) -> tuple[Decimal | None, int]:
        """A category tree's average over the months that had spending in it, and how many months that was."""
        observed = [sum((amounts.get(cid, ZERO) for cid in tree), ZERO)
                    for amounts in spending if any(cid in amounts for cid in tree)]
        return ((sum(observed, ZERO) / len(observed)).quantize(Decimal("0.01")) if observed else None), len(observed)

    def _outflow_children(self) -> tuple[dict[int, Category], dict[int, list[int]]]:
        categories = self.categories.tree(Movement.OUTFLOW)
        children: dict[int, list[int]] = {}
        for category in categories:
            if category.parent_id:
                children.setdefault(category.parent_id, []).append(category.id)
        return {category.id: category for category in categories}, children

    def tracked_ids(self, month: str) -> set[int]:
        """Categories you track in a month: those with a rule of their own, and those you chose to track."""
        view = self.month_view(month)
        tracked = {line.category_id for section in view.sections for line in section.lines
                   if line.direct is not None or line.average_months or line.income_percent is not None}
        return tracked | (self._id_list("budget_tracked_categories") or set())

    def category_averages(self, month: str) -> dict[int, dict]:
        """Each budget line's spending (its subcategories included) averaged over the three and the six
        completed months before `month` that had spending in it, and how many months each saw."""
        view = self.month_view(month)
        _, children = self._outflow_children()
        six = self._completed_months(month, 6)
        averages = {}
        for section in view.sections:
            for line in section.lines:
                tree = {line.category_id} | self._descendant_ids(line.category_id, children)
                average3, observed3 = self._tree_average(tree, six[:3])
                average6, observed6 = self._tree_average(tree, six)
                averages[line.category_id] = {"average3": average3, "observed3": observed3,
                                              "average6": average6, "observed6": observed6,
                                              "spent6": sum((amounts.get(cid, ZERO) for amounts in six for cid in tree), ZERO)}
        return averages

    def tracking_suggestions(self, month: str, percent: Decimal) -> list[dict]:
        """Untracked categories whose six-month average is at least `percent` of the month's budgeting
        income, unless one-off or dismissed (for good or for this month)."""
        income = self.budgeting_income(month)
        if not income:
            return []
        view = self.month_view(month)
        tracked, exclusions = self.tracked_ids(month), self.one_off_ids(with_children=False)
        by_id, _ = self._outflow_children()
        try:
            suppressed = json.loads(raw_setting(self.db, "budget_suppressed_categories") or "{}")
        except (ValueError, TypeError):
            suppressed = {}
        if isinstance(suppressed, list):
            suppressed = {str(category_id): "never" for category_id in suppressed}
        averages = self.category_averages(month)
        suggestions = []
        for line in (line for section in view.sections for line in section.lines
                     if line.depth > 1 and line.category_id not in tracked):
            category = by_id.get(line.category_id)
            if (not category or suppressed.get(str(line.category_id)) in {"never", month}
                    or category.id in exclusions):
                continue
            average = averages[line.category_id]
            if average["average6"] is None or average["spent6"] <= ZERO:
                continue
            share = average["average6"] / income * 100
            if share < percent:
                continue
            parent = category
            while parent.depth > 1 and parent.parent_id and by_id.get(parent.parent_id):
                parent = by_id[parent.parent_id]
            suggestions.append({"id": category.id, "name": line.name, "share": share, "group_id": parent.id,
                                "spent": average["spent6"]})
        return suggestions

    def background_estimates(self, month: str) -> list[dict]:
        """Monthly expectations for untracked spending categories: the average of the last three
        completed months that had spending. They count in the month's plan (owner decision
        2026-10-03); an estimate from one observed month is low confidence and the screens say so.
        Categories that are tracked, one-off, have children, or sit under a parent's own limit
        (covered) are left out, so nothing is counted twice."""
        return [line for line in self.background(month) if line["estimate"] is not None]

    def background(self, month: str, tracked: set[int] | None = None) -> list[dict]:
        """Every untracked category background_estimates considers, with `estimate` None when it had no
        spending in the three completed months. `tracked` replaces the month's own tracked categories."""
        view = self.month_view(month)
        tracked = self.tracked_ids(month) if tracked is None else tracked
        exclusions = self.one_off_ids(with_children=False)
        by_id, children = self._outflow_children()
        groups = {group.category_id for section in view.sections for group in section.groups}
        months = self._completed_months(month, 3)  # the three completed months before this one, newest first
        lines = []
        for section in view.sections:
            for line in section.lines:
                if (line.depth <= 1 or line.category_id in tracked or line.covered
                        or children.get(line.category_id) or line.category_id in exclusions):
                    continue
                parent = by_id.get(line.category_id)
                while parent and parent.depth > 1 and parent.parent_id:
                    parent = by_id.get(parent.parent_id)
                if not parent or parent.id not in groups:
                    continue
                estimate, observed = self._tree_average({line.category_id}, months)
                lines.append({"category_id": line.category_id, "name": line.name, "group_id": parent.id,
                              "estimate": estimate, "observed": observed, "low_confidence": observed <= 1})
        return lines

    @request_cached(deep=True)
    def plan_summary(self, month: str) -> dict:
        """The month's plan as every screen shows it: Planned (limits plus background estimates),
        Spent (owned spending, one-off categories left out) and Left in plan."""
        view = self.month_view(month)
        estimates = self.background_estimates(month)
        planned = view.available + sum((e["estimate"] for e in estimates), ZERO)
        first, last = parse_month(month)
        one_offs = self.one_off_ids()
        spent = sum((v for cid, v in self.owned_spending(first, last).items() if cid not in one_offs), ZERO)
        return {"planned": planned, "spent": spent, "left": planned - spent, "estimates": estimates,
                "low_confidence": [e for e in estimates if e["low_confidence"]]}

    def set_income_percentage(self, category_id: int, month: str, percent: object,
                              only_this_month: bool = False) -> bool:
        parse_month(month); category = self._budgetable(category_id)
        value = check_places(to_decimal(percent, "percentage"), 2, "percentage")
        if value < ZERO or value > 10000:
            raise ValidationError("Enter an income percentage from 0 to 10,000.", "percentage")
        rows = self.repo.entries_up_to(month)
        prior = next((row for row in reversed(rows) if row.category_id == category_id and not row.one_off
                      and row.month < month), None)
        previous = ((prior.amount, prior.average_months, prior.income_percent) if prior else (None, None, None))
        desired = (None, None, value)
        with self.db.transaction():
            if only_this_month:
                if previous == desired:
                    self.repo.delete(category_id, month, True)
                else:
                    self.repo.upsert(category_id, month, True, None, None, value)
            else:
                self.repo.delete(category_id, month, True)
                if previous == desired:
                    self.repo.delete(category_id, month, False)
                else:
                    self.repo.upsert(category_id, month, False, None, None, value)
        return True

    def reset_carryover(self, category_id: int, month: str) -> None:
        """Set a dated boundary clearing carryover from this month onward."""
        parse_month(month)
        self._budgetable(category_id)
        if category_id not in self.amounts_for(month):
            raise ValidationError("Reset carryover is available for tracked categories only.")
        self.repo.reset(category_id, month)

    @staticmethod
    def _average_period(raw: object) -> int | None:
        value = str(raw or "").strip()
        if value in ("", "manual"):
            return None
        if value not in ("3", "6"):
            raise ValidationError("Choose a 3-month or 6-month average, or enter a manual budget.", "budget")
        return int(value)

    def _budgetable(self, category_id: int) -> Category:
        category = self.categories.get(category_id)
        if category.movement != Movement.OUTFLOW or category.is_root:
            raise ValidationError(f"{category.name} cannot have a budget — budgets are for money out.", "budget")
        return category

    @staticmethod
    def _parse(raw: object, category: Category) -> Decimal | None:
        if raw is None or str(raw).strip() == "":
            return None
        value = check_places(to_decimal(raw, "budget"), 2, "budget")
        if value < ZERO:
            raise ValidationError(f"The budget for {category.name} cannot be negative.", "budget")
        if value > MAX_BUDGET:
            raise ValidationError(f"A budget of more than {MAX_BUDGET:,} is not realistic. Check the amount.", "budget")
        return value
