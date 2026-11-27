"""Public API of the budgeting module: the month view (budget vs actual) and saving budgets."""

from __future__ import annotations

from dataclasses import replace
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
import math
from datetime import date, timedelta
import json

from lightning.categories.domain import Category, CategoryFamily, Movement, Scope
from lightning.categories.service import CategoryService
from lightning.core.dates import estimate_date_override, month_of, now_iso, parse_month
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, check_places, fmt, fmt as _fmt, from_e6, quantize, to_decimal
from lightning.database.connection import Database
from lightning.database.settings import raw_setting
from lightning.reporting.service import ReportingService

from .domain import (EMERGENCY_BASES, INCOME_BASIS_FROM, INCOME_FROM_RECURRING, dated_basis, BudgetFillProposal, BudgetFillRow, BudgetLine, BudgetMonth,
                     BudgetSection, EmergencyFund, IncomeAverage, ScheduleView, SpendingAverage)
from .repository import BudgetRepository

SECTION_NAMES = {Scope.PERSONAL: "Personal", Scope.WORK: "Work"}


OVER_PLAN_MARGIN = Decimal(50)  # a category a few pounds over its plan is not worth a move
PACE_MARGIN = Decimal("0.10")  # NF-12AL2: warn only when spending is past the curve by more than this share of the limit
PACE_HISTORY_MONTHS, PACE_HISTORY_NEEDED = 3, 2  # the curve is the category's own from 2 of the last 3 months


MAX_BUDGET = 100_000_000  # EGP a month for one category; above it is a typo, not a plan

LIMIT_STEP_SMALL, LIMIT_STEP, LIMIT_SMALL_BELOW = Decimal(50), Decimal(100), Decimal(1000)


def round_limit(amount: Decimal) -> Decimal:
    """A suggested monthly limit as a number people plan with (BU-3): to the nearest 50 below 1,000 and the nearest
    100 from 1,000, halves up, and never below 50. 68 → 50, 671 → 650, 1,480 → 1,500, 4,666 → 4,700, 15 → 50."""
    step = LIMIT_STEP_SMALL if amount < LIMIT_SMALL_BELOW else LIMIT_STEP
    return max((amount / step).quantize(Decimal("1"), ROUND_HALF_UP) * step, LIMIT_STEP_SMALL)


# NF-12AK5: a purchase this small never asks to be left out of estimates, however it compares with its category.
UNUSUAL_PURCHASE_FLOOR = Decimal("1000")

class BudgetService:
    def __init__(self, db: Database, categories: CategoryService, reporting: ReportingService, *, funding):
        self.db = db
        self.repo = BudgetRepository(db)
        self.categories = categories
        self.reporting = reporting
        if not callable(getattr(funding, "by_category", None)) or not callable(getattr(funding, "adjustments", None)):
            raise TypeError("Budget funding must provide by_category and adjustments")
        self.funding = funding
        # What the plan has scheduled (loans, bills, recurring income, reserve goals) comes in as ``schedule``
        # on every call that needs it. A category with no budget rule is planned at exactly what is scheduled
        # (owner decision 2026-10-05: bills as loans).

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
    def scheduled_payments(self, month: str, *, schedule: ScheduleView) -> dict[int, Decimal]:
        """Loan payments, bills and subscriptions scheduled in a month, by spending category."""
        out = {cid: amount for cid, amount in schedule.loans(month).items() if amount}
        for cid, data in schedule.bills(month).items():
            if data["amount"]:
                out[cid] = out.get(cid, ZERO) + data["amount"]
        return out

    def bill_lines(self, month: str, *, schedule: ScheduleView) -> dict[int, Decimal]:
        """Categories planned from scheduled bills and subscriptions because no budget rule is set for them."""
        explicit = self.amounts_for(month, loans=False, schedule=schedule)
        return {cid: data["amount"] for cid, data in schedule.bills(month).items()
                if data["amount"] and cid not in explicit}

    def loan_lines(self, month: str, *, schedule: ScheduleView) -> dict[int, Decimal]:
        """Categories planned from scheduled loan payments because no budget rule is set for them."""
        explicit = self.amounts_for(month, loans=False, schedule=schedule)
        return {cid: amount for cid, amount in schedule.loans(month).items()
                if amount and cid not in explicit}

    def below_scheduled(self, month: str, *, schedule: ScheduleView) -> list[dict]:
        """Categories whose own rule plans less than the bills, subscriptions and loan payments scheduled
        in them that month: the plan cannot hold what is already promised."""
        explicit = self.amounts_for(month, loans=False, schedule=schedule)
        names = {category.id: category.name for category in self.categories.tree()}
        rows = []
        for cid, scheduled in self.scheduled_payments(month, schedule=schedule).items():
            planned = explicit.get(cid, (None,))[0]
            if planned is not None and planned < scheduled:
                rows.append({"category_id": cid, "name": names.get(cid, ""), "planned": planned, "scheduled": scheduled})
        return rows

    def over_twice(self, month: str, *, schedule: ScheduleView) -> list[dict]:
        """Categories over their own plan (by OVER_PLAN_MARGIN or more) in both of the two completed months
        before `month`, with how much more a month they needed (the larger overspend, rounded up to 50) and, when one exists, a category
        whose plan was left with at least that much in both months to move it from."""
        start = parse_month(month)[0]
        earlier = month_of(start - timedelta(days=1))
        months = (month_of(parse_month(earlier)[0] - timedelta(days=1)), earlier)
        views = [{line.category_id: line for section in self.month_view(key, schedule=schedule).sections for line in section.lines}
                 for key in months]
        now = {line.category_id: line for section in self.month_view(month, schedule=schedule).sections for line in section.lines}

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

    def running_out(self, month: str, on: date, *, schedule: ScheduleView) -> list[dict]:
        """NF-12S, NF-12AL2 (owner rule 3, 2026-11-13): flexible categories whose pace passes their limit before the
        month ends, after day 5, in the current month, for a category with a limit of its own that is not over yet.

        Only the flexible part is paced: the limit less the category's bills and subscriptions this month (paid on
        their day), and the spending less the bills already paid. Expected spending by today is that flexible limit
        times the category's own share-by-day curve (``_spending_curve``); a row appears only when spending is past it
        by more than ``PACE_MARGIN`` of the flexible limit. A category with a loan payment is not paced. Each row has
        the day the flexible limit runs out at this pace, the amount it needs, ``may`` when the curve is a straight
        line for want of history, and, when one exists, a category whose own flexible limit would still have that much
        left at its own pace to move from."""
        first, last = parse_month(month)
        if not first <= on <= last or on.day <= 5:
            return []
        days_gone, days = on.day, last.day
        loans = {cid for cid, amount in schedule.loans(month).items() if amount}
        bills = schedule.bills(month)
        one_offs = self.one_off_ids()
        lines = [line for section in self.month_view(month, schedule=schedule).sections for line in section.lines]
        paced: dict[int, dict] = {}
        for line in lines:
            if line.depth < 2 or line.direct is None or line.available is None or line.available <= ZERO:
                continue
            ids = {line.category_id} | {c.id for c in self.categories.descendants(line.category_id)
                                        if c.id not in one_offs}
            if ids & loans:
                continue
            billed = sum((bills[i]["amount"] for i in ids if i in bills), ZERO)
            paid = sum((bills[i].get("paid", ZERO) for i in ids if i in bills), ZERO)
            limit = line.available - billed
            if limit <= ZERO:
                continue
            spent = max(line.planned_actual - paid, ZERO)
            share, own = self._spending_curve(ids, first, days)
            expected = share[days_gone] if share[days_gone] > ZERO else Decimal(days_gone) / days
            paced[line.category_id] = {"limit": limit, "spent": spent, "share": share, "own": own,
                                       "now": share[days_gone], "projected": spent / expected, "expected": expected}
        rows = []
        for line in lines:
            cid, pace = line.category_id, paced.get(line.category_id)
            if pace is None or pace["spent"] <= ZERO or line.remaining is None or line.remaining < ZERO:
                continue
            if line.average_months or line.income_percent is not None:
                continue
            limit, spent = pace["limit"], pace["spent"]
            if spent - limit * pace["now"] <= limit * PACE_MARGIN or pace["projected"] <= limit:
                continue
            short = Decimal(math.ceil((pace["projected"] - limit) / 50) * 50)
            curve = pace["share"] if pace["now"] > ZERO else [Decimal(t) / days for t in range(days + 1)]
            runs_out = next((t for t in range(days_gone, days + 1) if spent * curve[t] >= limit * pace["expected"]),
                            days)
            related = lambda other: other.code.startswith(line.code + ".") or line.code.startswith(other.code + ".")
            donors = [(paced[other.category_id]["limit"] - paced[other.category_id]["projected"], other)
                      for other in lines if other.category_id in paced and other.category_id != cid
                      and not related(other) and other.direct >= short
                      and paced[other.category_id]["limit"] - paced[other.category_id]["projected"] >= short]
            donor = max(donors, key=lambda pair: pair[0])[1] if donors else None
            rows.append({"category_id": cid, "name": line.name, "limit": limit, "bills": line.available - limit,
                         "day": runs_out, "amount": short, "may": not pace["own"],
                         "can_move": line.direct is not None and donor is not None,
                         "from_id": donor.category_id if donor else None,
                         "from_name": donor.name if donor else None})
        rows.sort(key=lambda r: (r["day"], r["name"].casefold()))
        return rows

    def _spending_curve(self, ids: set[int], first: date, days: int) -> tuple[list[Decimal], bool]:
        """NF-12AL2: the share of a month's spending done by each day (index 0..days, 0 then 1 at the end) for these
        categories, averaged over the last ``PACE_HISTORY_MONTHS`` completed months before ``first`` that had
        spending, when at least ``PACE_HISTORY_NEEDED`` did; else the straight line t / days. A shorter past month
        counts as whole from its last day on. The flag says whether the curve is the category's own."""
        months = []
        end = first - timedelta(days=1)
        for _ in range(PACE_HISTORY_MONTHS):
            months.append((end.replace(day=1), end))
            end = end.replace(day=1) - timedelta(days=1)
        by_day = self.reporting.money_out_by_category_by_day(months[-1][0], months[0][1])
        shares = []
        for start, stop in months:
            daily = [sum((by_day.get((start + timedelta(days=n)).isoformat(), {}).get(i, ZERO) for i in ids), ZERO)
                     for n in range(stop.day)]
            total = sum(daily, ZERO)
            if total <= ZERO:
                continue
            running, cumulative = ZERO, [ZERO]
            for amount in daily:
                running += amount
                cumulative.append(min(max(running / total, ZERO), Decimal(1)))
            shares.append([cumulative[min(t, stop.day)] for t in range(days + 1)])
        if len(shares) < PACE_HISTORY_NEEDED:
            return [Decimal(t) / days for t in range(days + 1)], False
        return [sum((share[t] for share in shares), ZERO) / len(shares) for t in range(days + 1)], True

    def cover_options(self, month: str, to_id: int, overspend: Decimal, room: dict[int, Decimal], *, schedule: ScheduleView) -> list[dict]:
        """Amounts transferable from independent limits, after spending and outstanding bills."""
        plans = self.amounts_for(month, loans=False, schedule=schedule)
        to_limit = plans.get(to_id, (None,))[0]
        if to_limit is None:
            return []
        gap = quantize(overspend)
        categories = {cat.id: cat for cat in self.categories.tree(Movement.OUTFLOW)}
        if to_id not in categories:
            return []
        lines = {line.category_id: line for section in self.month_view(month, schedule=schedule).sections
                 for line in section.lines}
        child_limits, child_room = {}, {}
        for cid, line in lines.items():
            if cid in categories and line.available is not None:
                parent = categories[cid].parent_id
                child_limits[parent] = child_limits.get(parent, ZERO) + max(line.available, ZERO)
                child_room[parent] = child_room.get(parent, ZERO) + max(room.get(cid, ZERO), ZERO)

        def parent_limit(cid):
            parent = categories[cid].parent_id
            while parent in categories:
                if parent in plans:
                    return parent
                parent = categories[parent].parent_id
            return None

        recipient_parent = parent_limit(to_id)
        options = []
        for cid, left in room.items():
            limit = plans.get(cid, (None,))[0]
            if limit is None or cid == to_id or cid not in categories:
                continue
            donor = categories[cid]
            if not donor.active or parent_limit(cid) != recipient_parent:
                continue
            # A parent's remaining limit must still cover the limits assigned to its children.
            unassigned = lines[cid].available - child_limits.get(cid, ZERO)
            available = min(left - child_room.get(cid, ZERO), limit, unassigned).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            amount = min(gap, available)
            if amount > ZERO:
                options.append({"id": cid, "name": donor.name, "amount": amount, "available": available,
                                "new_limit": limit - amount, "target_limit": to_limit + amount, "uncovered": gap - amount,
                                "carryover": lines[cid].carryover_enabled or lines[to_id].carryover_enabled})
        return sorted(options, key=lambda row: (-row["amount"], -row["available"], row["name"], row["id"]))

    def move_room(self, month: str, to_id: int, from_id: int, amount: object, only_this_month: bool = False, *,
                  schedule: ScheduleView) -> None:
        """Move plan from one category to another: both keep fixed amounts and the total is unchanged. With
        ``only_this_month`` it covers `month` alone (limits for this month only, the usual plan stays); otherwise it
        changes the usual plan from `month` on (NF-12AJ)."""
        value = to_decimal(amount, "amount")
        if value <= 0:
            raise ValidationError("Move an amount above zero.", "amount")
        if to_id == from_id:
            raise ValidationError("Choose two different categories.", "category")
        current = self.amounts_for(month, loans=False, schedule=schedule)
        give, take = current.get(from_id, (None,))[0], current.get(to_id, (None,))[0]
        if give is None or take is None:
            raise ValidationError("Both categories need a plan of their own this month.", "category")
        if give < value:
            raise ValidationError(f"{self.categories.get(from_id).name} plans only {fmt(give, 0)} this month.", "amount")
        with self.db.transaction():
            self.save_month(month, {to_id: take + value, from_id: give - value}, only_this_month, schedule=schedule)

    @request_cached  # has_plan, loan_lines, bill_lines and month_view all ask for it
    def amounts_for(self, month: str, loans: bool = True, *, schedule: ScheduleView) -> dict[int, tuple[Decimal | None, bool, int | None, Decimal | None]]:
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
                income = self.budgeting_income(month, schedule=schedule)
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
            for cid, amount in self.scheduled_payments(month, schedule=schedule).items():
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

    # ------------------------------------------------------------- one transaction left out of estimates (NF-12AK2)
    @request_cached
    def left_out_ids(self) -> frozenset[int]:
        """Expenses the person chose to leave out of estimates (owner 2026-11-13). Optional, never automatic; Cash
        flow and Spent still count them. This service is the only writer of ``budget_estimate_exclusions``."""
        return frozenset(int(row["transaction_id"]) for row in
                         self.db.all("SELECT transaction_id FROM budget_estimate_exclusions"))

    def is_left_out(self, transaction_id: int) -> bool:
        return int(transaction_id) in self.left_out_ids()

    def estimate_date(self, transaction_id: int) -> str | None:
        return self.db.scalar("SELECT estimate_date FROM budget_estimate_dates WHERE transaction_id=?", (transaction_id,))

    def can_set_estimate_date(self, transaction_id: int) -> bool:
        return bool(self.db.scalar(
            "SELECT 1 FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "JOIN categories c ON c.id=le.category_id WHERE t.id=? AND t.status='POSTED' "
            "AND t.type IN ('OUT','IN') AND le.owner_id IS NULL AND le.effect IN ('INFLOW','OUTFLOW') "
            "AND c.movement='OUTFLOW' AND c.income_class IS NULL AND c.family<>'INVESTMENT' "
            "AND c.code<>'EXP.SYSTEM.CUSTODY'", (transaction_id,)))

    def set_estimate_date(self, transaction_id: int, estimate_date: str | None) -> None:
        day = estimate_date_override(estimate_date)
        with self.db.transaction(undo_label="Change estimate date"):
            if day is None:
                self.db.execute("DELETE FROM budget_estimate_dates WHERE transaction_id=?", (transaction_id,))
                return
            if not self.can_set_estimate_date(transaction_id):
                raise ValidationError("Choose an entry with personal spending for an estimate date.", "estimate_date")
            self.db.execute("INSERT INTO budget_estimate_dates(transaction_id,estimate_date) VALUES (?,?) "
                            "ON CONFLICT(transaction_id) DO UPDATE SET estimate_date=excluded.estimate_date "
                            "WHERE budget_estimate_dates.estimate_date<>excluded.estimate_date",
                            (transaction_id, day))

    def can_leave_out(self, transaction_id: int) -> bool:
        """A posted expense with the user's own spending in an expense category: the only kind estimates can skip."""
        rows = self.db.all(
            "SELECT DISTINCT le.category_id FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "JOIN categories c ON c.id=le.category_id "
            "WHERE t.id=? AND t.type='OUT' AND t.status='POSTED' AND le.owner_id IS NULL "
            "AND le.effect IN ('INFLOW','OUTFLOW') AND c.movement='OUTFLOW'", (int(transaction_id),))
        investment = self._investment_ids()
        return any(int(row["category_id"]) not in investment for row in rows)

    def set_left_out(self, transaction_id: int, left_out: bool) -> bool:
        """Leave one expense out of estimates, or count it again. Returns whether anything changed."""
        transaction_id = int(transaction_id)
        if not self.db.scalar("SELECT 1 FROM transactions WHERE id=?", (transaction_id,)):
            raise NotFoundError("That transaction no longer exists.")
        current = bool(self.db.scalar("SELECT 1 FROM budget_estimate_exclusions WHERE transaction_id=?",
                                      (transaction_id,)))
        if bool(left_out) == current:
            return False
        with self.db.transaction(undo_label="Leave out of estimates" if left_out else "Count in estimates"):
            if left_out:
                if not self.can_leave_out(transaction_id):
                    raise ValidationError("Only an expense can be left out of estimates.")
                stamp = now_iso()
                self.db.execute("INSERT INTO budget_estimate_exclusions(transaction_id,created_at,updated_at) "
                                "VALUES(?,?,?)", (transaction_id, stamp, stamp))
            else:
                self.db.execute("DELETE FROM budget_estimate_exclusions WHERE transaction_id=?", (transaction_id,))
        return True

    def budgeting_income(self, month: str, *, schedule: ScheduleView) -> Decimal | None:
        """Average monthly income for a month's budget (see income_average)."""
        return self.income_average(month, schedule=schedule).amount

    @request_cached(deep=True)
    def income_average(self, month: str, *, schedule: ScheduleView) -> IncomeAverage:
        """Average monthly income: owned income in the chosen income categories, averaged over
        the last 3 (or 6) completed months before `month` that had any. A manual amount in
        Settings replaces the average. Before any completed month has income, the income set up in
        Cash planning › Recurring stands in, so a new plan is checked from day one. An income drop planned on
        (HealthService.take_income_change) sets the basis from its month on; earlier months keep the average. The
        budget, reserves and the cash forecast all use this."""
        chosen = self.recurring_income_ids()
        categories = self.categories.tree()
        by_id = {category.id: category for category in categories}
        lookback = self._average_months()
        manual = raw_setting(self.db, "budget_manual_monthly_income")
        if manual:
            return IncomeAverage(to_decimal(manual, "manual_income"), 0, lookback, "", "", True)
        if raw_setting(self.db, INCOME_FROM_RECURRING) == "1":
            scheduled = schedule.income()  # chosen after a raise: plan with what Recurring expects
            if scheduled is not None:
                return IncomeAverage(scheduled, 0, lookback, "", "", False, scheduled=True)
        dated = dated_basis(raw_setting(self.db, INCOME_BASIS_FROM))
        if dated and month >= dated[0]:  # an income drop planned on from its month; earlier months keep the average
            return IncomeAverage(dated[1], 0, lookback, "", "", False, since=dated[0])
        end = parse_month(month)[0] - timedelta(days=1)
        last_month = month_of(end)
        observed = []
        for _ in range(lookback):
            start, _ = parse_month(month_of(end))
            if chosen:
                marks = ",".join("?" for _ in chosen)
                rows = self.db.all(
                    "SELECT le.category_id,SUM(le.amount_base_e6-COALESCE(w.amount_e6,0)) AS total_e6 "
                    "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                    "LEFT JOIN work_claim_allocations w ON w.transaction_id=le.transaction_id AND w.line_no=le.line_no "
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
            scheduled = schedule.income()
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

    def emergency_fund(self, month: str, set_aside: Decimal | None, *, schedule: ScheduleView,
                       start: Decimal | None = None, moved: Decimal = ZERO) -> EmergencyFund:
        """The emergency fund in months of the chosen average, and its six-month target. ``start`` and ``moved``
        fix the month's top-up on the 1st (BT-7AV1)."""
        basis = self.emergency_basis()
        average = self.income_average(month, schedule=schedule) if basis == "income" else self.spending_average(month)
        return EmergencyFund(set_aside, basis, average, start, moved)

    def has_plan(self, month: str, *, schedule: ScheduleView) -> bool:
        return bool(self.amounts_for(month, loans=False, schedule=schedule))

    def plan_gap(self, month: str, view: BudgetMonth, *, schedule: ScheduleView):
        """Left to plan: the income the plan stands on, everything the month plans, and what is still without a job
        (None when there is no income to plan from)."""
        income = self.income_average(month, schedule=schedule).amount
        planned = view.budget
        return income, planned, (income - planned if income is not None else None)

    @request_cached(deep=True)
    def month_view(self, month: str, *, schedule: ScheduleView) -> BudgetMonth:
        first, last = parse_month(month)
        direct = self.amounts_for(month, schedule=schedule)
        from_loans = self.loan_lines(month, schedule=schedule)
        from_bills = self.bill_lines(month, schedule=schedule)
        spent = self.owned_spending(first, last)
        funded = self.plan_funded_spending(first, last)
        cats = [c for c in self.categories.tree(Movement.OUTFLOW) if not c.is_root
                and c.family != CategoryFamily.INVESTMENT]  # investments are never budget spending
        by_id = {c.id: c for c in cats}
        children: dict[int, list[int]] = {}
        for c in cats:
            if c.parent_id in by_id:
                children.setdefault(c.parent_id, []).append(c.id)

        one_offs = self.one_off_ids()
        actual: dict[int, Decimal] = {}
        funded_actual: dict[int, Decimal] = {}
        planned_actual: dict[int, Decimal] = {}
        budget: dict[int, Decimal | None] = {}
        for c in reversed(cats):  # children before parents
            kids = children.get(c.id, [])
            # A one-off child keeps its own actual but does not add to its parent's (unless it has a plan).
            actual[c.id] = spent.get(c.id, ZERO) + sum((actual[k] for k in kids
                                                        if k not in one_offs or k in direct), ZERO)
            funded_actual[c.id] = funded.get(c.id, ZERO) + sum((funded_actual[k] for k in kids
                                                               if k not in one_offs or k in direct), ZERO)
            if c.id in direct:
                amount, _, period, percent = direct[c.id]
                budget[c.id] = amount
            else:
                kid_budgets = [budget[k] for k in kids if budget[k] is not None]
                budget[c.id] = sum(kid_budgets, ZERO) if kid_budgets else None
            if budget[c.id] is not None and c.id in direct:
                planned_actual[c.id] = funded_actual[c.id]
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
        opening_carryovers = {
            cid: self._opening_carryover(cid, month, children, one_offs, schedule=schedule)
            for cid, enabled in carryover_settings.items() if enabled and cid in direct
        }
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
                section.unbudgeted += funded.get(c.id, ZERO)
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
            child_limits = [budget[k] + opening_carryovers.get(k, ZERO)
                            for k in children.get(c.id, []) if budget[k] is not None]
            kids_total = sum(child_limits, ZERO)
            parent_available = (budget[c.id] or ZERO) + opening_carryovers.get(c.id, ZERO)
            if child_limits and budget[c.id] is not None and kids_total > parent_available:
                warnings.append(f"{self.categories.display_name(c.id)}: its categories add up to "
                                f"{fmt(kids_total)}, more than its budget / available limit of {fmt(parent_available)}.")
        income = self.reporting.cash_flow(first, last).inflows
        return BudgetMonth(month, [s for s in sections.values() if s.lines], income, warnings)

    def plan_left(self, category_id: int, month: str, *, schedule: ScheduleView) -> dict | None:
        """What is left of the plan for a category this month (the phone's transaction sheet, 3AD2): the limit that
        covers it (its own, else the nearest group above that has one), what is spent against it and what is left,
        negative when over. None when no limit covers the category."""
        view = self.month_view(month, schedule=schedule)
        by_id = {line.category_id: line for section in view.sections for line in section.lines}
        one_offs = self.one_off_ids()
        node = category_id
        while node is not None:
            shown = by_id.get(node)
            if shown is not None and shown.direct is not None:
                return {"name": shown.name, "limit": shown.available, "spent": shown.planned_actual,
                        "left": shown.remaining, "over": shown.over, "inside": node != category_id}
            if node in one_offs:
                break  # An unplanned outside-budget category does not spend its parent's limit.
            node = self.categories.get(node).parent_id
        return None

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

    def first_plan_suggestions(self, month: str) -> dict[int, Decimal]:
        """The limits a first plan offers (BU-3): each suggestion as a round number, see round_limit. Only the
        offer is rounded; what the user types is kept exactly, and demo and sample seeding keep suggested_plan."""
        return {cid: round_limit(amount) for cid, amount in self.suggested_plan(month).items()}

    def fill_proposal(self, month: str, source: str, *, schedule: ScheduleView) -> BudgetFillProposal:
        """Build a read-only month-fill preview; all returned amounts are base limits in EGP."""
        first, _ = parse_month(month)
        if source == "changes":
            return self._fill_changes(month, schedule=schedule)
        if source not in {"last_month", "average", "schedule", "goal"}:
            raise ValidationError("Choose What changed, Last month, Your average, Schedule, or Goal as the fill source.",
                                  "source")
        categories = [c for c in self.categories.tree(Movement.OUTFLOW)
                      if not c.is_root and c.family != CategoryFamily.INVESTMENT]
        by_id = {c.id: c for c in categories}
        current = self.amounts_for(month, loans=False, schedule=schedule)
        current_rules = {cid: rule for cid, rule in current.items() if cid in by_id}
        candidates: dict[int, tuple[Decimal | None, str]] = {}

        if source == "last_month":
            previous = month_of(first - timedelta(days=1))
            for category_id, (amount, only_then, period, percent) in self.amounts_for(previous, loans=False, schedule=schedule).items():
                if category_id in by_id:
                    detail = (f"{period}-month average" if period else
                              f"{fmt(percent)}% of income" if percent is not None else
                              "for that month only" if only_then else "fixed")  # NF-12AI: an exception says so
                    candidates[category_id] = (amount, f"From {previous} · {detail}")
        elif source == "average":
            # NF-12R: what was really spent, averaged over the last three full months (NF-12AK1: over all three once the
            # profile covers them, else over the months with spending), as a tidy figure; categories outside the budget
            # are left out.
            one_offs = self.one_off_ids()
            window, full = self._completed_months(month, 3), self._full_window(month, 3)
            for category_id, amount in self.first_plan_suggestions(month).items():
                if category_id in by_id and category_id not in one_offs:
                    candidates[category_id] = (amount, self._average_note(category_id, window, full))
        elif source == "schedule":
            for category_id, data in schedule.bills(month).items():
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
            ) for item in schedule.goal_needs(month))
            return BudgetFillProposal(month, source, rows)

        loans = self.scheduled_payments(month, schedule=schedule)
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
            elif rule is not None:  # NF-12AI: a limit you set is kept unless you tick the row
                conflict = ""  # r39: the limit is its own column, and the intro says ticking replaces it for the month
            elif auto_loan:
                conflict = (f"{fmt(auto_loan)} of scheduled payments are already planned automatically. "
                            "Applying this amount would replace that automatic line.")
            rows.append(BudgetFillRow(
                category_id=category_id,
                category_name=self.categories.display_name(category_id),
                source={"last_month": "Last month", "average": "Your average"}.get(source, "Schedule"),
                amount=amount,
                current_amount=current_amount,
                current_rule=current_rule,
                conflict=conflict,
                selectable=amount is not None and not same,  # NF-12AI: an unchanged row has nothing to apply
                selected=amount is not None and not auto_loan and rule is None,
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

    def _fill_changes(self, month: str, *, schedule: ScheduleView) -> BudgetFillProposal:
        """NF-12AI (#635): Fill's default view, only what would change this month. Bills scheduled above a limit you
        set, and an average for a category with history: new where there is no limit (ticked), beside your limit where
        it differs (unticked, so a limit you chose is kept). Each row keeps its source; the rest are counted unchanged."""
        bills = {row.category_id: row for row in self.fill_proposal(month, "schedule", schedule=schedule).rows}
        averages = {row.category_id: row for row in self.fill_proposal(month, "average", schedule=schedule).rows}
        rows, unchanged = [], 0
        for category_id in dict.fromkeys([*bills, *averages]):
            bill, average = bills.get(category_id), averages.get(category_id)
            if bill and bill.current_amount is not None and bill.amount is not None and bill.amount > bill.current_amount:
                rows.append(replace(bill, selected=False, note=f"{bill.note} · above your limit"))
            elif average and average.selectable:
                rows.append(average)
            else:
                unchanged += 1
        by_id = {c.id: c for c in self.categories.tree(Movement.OUTFLOW)}
        rows.sort(key=lambda row: (by_id[row.category_id].sort_order, row.category_name.casefold()))
        return BudgetFillProposal(month, "changes", tuple(rows), unchanged=unchanged)

    def _average_note(self, category_id: int, window: list[dict[int, Decimal]], full: bool) -> str:
        """Fill's source label for an average (NF-12AK rule 5): the same words as Budget's average label, so one
        purchase in three covered months reads "1 of 3 months had spending" and a newer profile says so."""
        observed = self._tree_average({category_id}, window, full=full)[1]  # suggested_plan offers leaves only
        head = "Your average of the last 3 months"
        if full:
            return f"{head} · {observed} of 3 months had spending"
        if observed == 1:
            return f"{head} · Low confidence · 1 observed month"
        return f"{head} · Little history · {observed} months with spending"

    @staticmethod
    def _fill_rule_name(rule) -> str:
        amount, _, period, percent = rule
        def fmt(value, *args):  # r39 (A06.1): a whole amount shows no ".00"; piastres show when there are any
            return _fmt(value, 0) if not args and value == value.to_integral_value() else _fmt(value, *args)
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

    def spent_in(self, category_ids, start, end) -> Decimal:
        """What these categories spent between start and end, one-off purchases left out: a Budget category sheet's
        "last month" figure when nothing is spent yet this month (3AN9)."""
        one_offs, wanted = self.one_off_ids(), set(category_ids)
        return sum((v for cid, v in self.owned_spending(start, end).items() if cid in wanted and cid not in one_offs), ZERO)

    def unusual_purchases(self, month: str) -> list[dict]:
        """NF-12AK5 (owner, 2026-11-13): purchases that make up more than half of their category's estimate basis in
        the three completed months before ``month``, in a category that also had spending in another of those months,
        so one large buy stands out against normal spending (a 9,000 laptop beside 1,000 a month of food); below
        UNUSUAL_PURCHASE_FLOOR a purchase is never worth a question. A purchase
        already left out of estimates, paid by a scheduled bill or funded from a reserve or a loan is never offered.
        Largest first, one per category."""
        cursor, windows = parse_month(month)[0], []
        for _ in range(3):
            start, end = parse_month(month_of(cursor - timedelta(days=1)))
            windows.append((start, end))
            cursor = start
        first, last = windows[-1][0], windows[0][1]
        basis = self._completed_months(month, 3)
        totals = {cid: sum((m.get(cid, ZERO) for m in basis), ZERO) for m in basis for cid in m}
        months_with = {cid: sum(1 for m in basis if m.get(cid, ZERO) > ZERO) for cid in totals}
        skip = set(self.left_out_ids()) | {int(row["transaction_id"]) for row in self.db.all(
            "SELECT transaction_id FROM planned_payments WHERE transaction_id IS NOT NULL "
            "UNION SELECT transaction_id FROM reserve_transaction_links "
            "UNION SELECT transaction_id FROM loan_extra_payments")}
        investment = self._investment_ids()
        purchases: dict[tuple[int, int], dict] = {}
        for line in self.reporting.spending_lines(first, last):
            txn, cid = line["transaction_id"], line["category_id"]
            if txn in skip or cid in investment or line["value"] <= ZERO:
                continue
            row = purchases.setdefault((txn, cid), {"transaction_id": txn, "category_id": cid, "date": line["date"],
                                                    "name": line["counterparty"] or line["description"] or "",
                                                    "amount": ZERO})
            row["amount"] += line["value"]
        found: dict[int, dict] = {}
        for row in purchases.values():
            cid, total = row["category_id"], totals.get(row["category_id"], ZERO)
            if (total <= ZERO or months_with.get(cid, 0) < 2 or row["amount"] * 2 <= total
                    or row["amount"] < UNUSUAL_PURCHASE_FLOOR):
                continue
            if cid not in found or row["amount"] > found[cid]["amount"]:
                found[cid] = row | {"window_total": total, "category": self.categories.get(cid).name}
        return sorted(found.values(), key=lambda row: -row["amount"])

    def tree_ids(self, category_id: int) -> set[int]:
        """A category and every category under it."""
        return {int(category_id)} | {c.id for c in self.categories.descendants(category_id)}

    def recoveries(self, category_ids, start, end, *, expected_back: Decimal) -> dict[str, Decimal]:
        """NF-12AK5 (owner, 2026-11-13): a category's month as four figures, never mixed: *paid* (what its purchases
        cost), *returned* (refunds and claim receipts in it), *expected back* (personal claims still open, from
        ``ReimbursementService.expected_back``) and *yours* (paid less both). Personal spending only: work claims are
        out already (NF-12AM)."""
        wanted, paid, returned = set(category_ids), ZERO, ZERO
        investment = self._investment_ids()
        for line in self.reporting.spending_lines(start, end):
            if line["category_id"] not in wanted or line["category_id"] in investment:
                continue
            if line["value"] > ZERO:
                paid += line["value"]
            else:
                returned -= line["value"]
        return {"paid": paid, "returned": returned, "expected_back": expected_back,
                "yours": paid - returned - expected_back}

    def plan_funded_spending(self, start, end) -> dict[int, Decimal]:
        """Gross owned spending less confirmed funding outside this month's plan."""
        gross = self.owned_spending(start, end)
        for cid, adjustment in self.funding.by_category(start, end).items():
            if cid in gross:
                gross[cid] -= adjustment["principal"] + adjustment["reserve"]
        return gross

    def _investment_ids(self) -> set[int]:
        return {c.id for c in self.categories.tree() if c.family == CategoryFamily.INVESTMENT}

    def set_carryover(self, month: str, settings: dict[int, bool], *, schedule: ScheduleView) -> int:
        parse_month(month)
        changed = 0
        current = self.repo.carryover_settings(month)
        with self.db.transaction():
            for category_id, enabled in settings.items():
                self._budgetable(category_id)
                if enabled and category_id not in self.amounts_for(month, schedule=schedule):
                    raise ValidationError("Carryover needs a monthly limit on that category or group first.")
                if current.get(category_id, False) == enabled:
                    continue
                self.repo.set_carryover(category_id, month, enabled)
                changed += 1
        return changed

    def _opening_carryover(self, category_id: int, month: str, children: dict[int, list[int]],
                           one_offs: set[int], *, schedule: ScheduleView) -> Decimal:
        # The first enabled month takes the previous month's closing balance. A pause
        # discards everything carried into that previous month.
        settings = self.repo.carryover_settings_up_to(month, category_id)
        enabled_since = month
        for effective, enabled in reversed(settings):
            if not enabled:
                break
            enabled_since = effective
        first_enabled = parse_month(enabled_since)[0]
        cursor = max(first_enabled - timedelta(days=1), date(1900, 1, 1))
        reset_month = self.repo.reset_month(category_id, month)
        if reset_month:
            cursor = max(cursor, parse_month(reset_month)[0])
        balance = ZERO
        while month_of(cursor) < month:
            current_month = month_of(cursor)
            start, end = parse_month(current_month)
            limits = self.amounts_for(current_month, schedule=schedule)
            amount = limits.get(category_id, (None,))[0]
            if amount is None:
                balance = ZERO
            else:
                spent = self.plan_funded_spending(start, end)
                balance += amount
                pending = [category_id]
                while pending:
                    cid = pending.pop()
                    balance -= spent.get(cid, ZERO)
                    pending.extend(k for k in children.get(cid, []) if k not in one_offs or k in limits)
            cursor = end + timedelta(days=1)
        return balance

    # ------------------------------------------------------------------ writing
    def set_budget(self, category_id: int, month: str, amount: object, only_this_month: bool = False,
                   average_months: int | None = None, *, schedule: ScheduleView) -> bool:
        return self.save_month(month, {category_id: amount}, only_this_month,
                               {category_id: average_months} if average_months else None, schedule=schedule) > 0

    def save_month(self, month: str, amounts: dict[int, object], only_this_month: bool = False,
                   average_months: dict[int, object] | None = None, *, schedule: ScheduleView) -> int:
        """Save several budget cells at once (the budget page). Returns how many changed."""
        parse_month(month)
        current = self.amounts_for(month, schedule=schedule)
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
                self._write_rule(category_id, month, only_this_month, value, period, None)
                if not only_this_month and value is None and period is None and carryover_now.get(category_id, False):
                    self.repo.set_carryover(category_id, month, False)
                changed += 1
        return changed

    def apply_fill(self, month: str, amounts: dict[int, object], *, schedule: ScheduleView) -> int:
        """Apply selected fill amounts as one atomic, one-month-only edit."""
        parse_month(month)
        if not amounts:
            raise ValidationError("Choose at least one category to fill.", "categories")
        with self.db.transaction():
            return self.save_month(month, amounts, only_this_month=True, schedule=schedule)

    # ------------------------------------------------------------------ helpers
    def _write_rule(self, category_id: int, month: str, only_this_month: bool, amount: Decimal | None,
                    average_months: int | None, income_percent: Decimal | None) -> None:
        """Compare an override with the rule in force that month, and a repeating change with the prior rule."""
        rows = self.repo.entries_up_to(month)
        prior = next((r for r in reversed(rows) if r.category_id == category_id and not r.one_off
                      and (only_this_month or r.month < month)), None)
        inherited = (prior.amount, prior.average_months, prior.income_percent) if prior else (None, None, None)
        if not only_this_month:
            self.repo.delete(category_id, month, one_off=True)
        if (amount, average_months, income_percent) == inherited:
            self.repo.delete(category_id, month, one_off=only_this_month)
        else:
            self.repo.upsert(category_id, month, only_this_month, amount, average_months, income_percent)

    def _rolling_average(self, category_id: int, month: str, months: int,
                         children: dict[int, list[int]], cache: dict[tuple[int, int], Decimal | None]) -> Decimal | None:
        key = (category_id, months)
        if key in cache:
            return cache[key]
        tree = {category_id} | self._descendant_ids(category_id, children)
        cache[key] = self._tree_average(tree, self._completed_months(month, months),
                                        full=self._full_window(month, months))[0]
        return cache[key]

    def _completed_months(self, month: str, months: int) -> list[dict[int, Decimal]]:
        """The estimate basis by category in completed months, newest first (NF-12AK1)."""
        spending, cursor = [], parse_month(month)[0]
        for _ in range(months):
            start, end = parse_month((cursor - timedelta(days=1)).strftime("%Y-%m"))
            spending.append(self.estimate_spending(start, end))
            cursor = start
        return spending

    def estimate_spending(self, start, end) -> dict[int, Decimal]:
        """What estimates read for a period (NF-12AK1, owner 2026-11-13): plan-funded spending, with money back that is
        linked to its expense (a reimbursement receipt, or a refund that names its purchase: NF-12AK3) counted in the
        expense's month rather than the month it arrived, and each category floored at zero, so a refund on its own
        never makes a negative month. An expense the person left out (NF-12AK2) is skipped here, with every refund and
        claim receipt linked to it. Cash, Spent and every report keep the real dates; only averages and the estimates
        built on them read this."""
        first, last = str(start)[:10], str(end)[:10]
        basis, moved = self.plan_funded_spending(start, end), set()
        taken: dict[int, Decimal] = {}
        excluded_funding: dict[int, Decimal] = {}
        funding = self.funding.adjustments(start, end)
        for line in self._left_out_lines():  # NF-12AK2: an expense left out, with the money back linked to it
            if first <= line["date"] <= last:
                cid = line["category_id"]
                taken[cid] = taken.get(cid, ZERO) + line["amount"]
                # Only funding linked to this excluded purchase was already removed from the basis.
                key = (line["transaction_id"], cid)
                adjustment = funding.pop(key, None) if line["transaction_id"] is not None else None
                if adjustment:
                    excluded_funding[cid] = excluded_funding.get(cid, ZERO) + min(
                        max(line["amount"], ZERO), adjustment["principal"] + adjustment["reserve"])
        for cid, amount in taken.items():
            basis[cid] = basis.get(cid, ZERO) - amount + excluded_funding.get(cid, ZERO)
            moved.add(cid)
        for shift in self._estimate_portions():
            cid, amount = shift["category_id"], shift["amount"]
            if first <= shift["posting_date"] <= last and first <= shift["effective_date"] <= last:
                continue
            if first <= shift["posting_date"] <= last:
                basis[cid] = basis.get(cid, ZERO) - amount
                moved.add(cid)
            if first <= shift["effective_date"] <= last:
                basis[cid] = basis.get(cid, ZERO) + amount
        # A month whose only line was money back that moved to its expense had no spending of its own.
        return {cid: max(amount, ZERO) for cid, amount in basis.items() if amount or cid not in moved}

    @request_cached(deep=True)
    def _estimate_portions(self, transaction_id: int | None = None) -> list[dict]:
        """Signed portions for display on one entry, or portions that move for the estimate calculation."""
        excluded = self.left_out_ids()
        linked = {}
        shifts = []
        for row in self._recovery_shifts(transaction_id):
            key = (row["receipt_id"], row["category_id"])
            linked[key] = linked.get(key, ZERO) + row["amount"]
            if row["expense_id"] not in excluded and (transaction_id is not None or row["receipt_date"] != row["expense_date"]):
                shifts.append(dict(transaction_id=row["receipt_id"], category_id=row["category_id"], linked=True,
                                   posting_date=row["receipt_date"], effective_date=row["expense_date"], amount=-row["amount"]))
        scope = "AND t.id=?" if transaction_id is not None else "AND d.estimate_date<>t.date"
        args = (transaction_id,) if transaction_id is not None else ()
        rows = self.db.all(
            "SELECT t.id,t.date,COALESCE(d.estimate_date,t.date) estimate_date,le.category_id, "
            "SUM(COALESCE(w.amount_e6,0)-le.amount_base_e6) amount_e6 "
            "FROM transactions t LEFT JOIN budget_estimate_dates d ON d.transaction_id=t.id "
            "JOIN ledger_entries le ON le.transaction_id=t.id JOIN categories c ON c.id=le.category_id "
            "LEFT JOIN work_claim_allocations w ON w.transaction_id=t.id AND w.line_no=le.line_no "
            "WHERE t.status='POSTED' AND t.type IN ('IN','OUT') "
            "AND le.owner_id IS NULL AND le.effect IN ('INFLOW','OUTFLOW') AND c.movement='OUTFLOW' "
            "AND c.income_class IS NULL AND c.family<>'INVESTMENT' AND c.code<>'EXP.SYSTEM.CUSTODY' "
            f"{scope} GROUP BY t.id,le.category_id", args)
        funding_by_day = {}
        for row in rows:
            tid, cid, day = row["id"], row["category_id"], row["date"]
            if tid in excluded:
                continue
            if day not in funding_by_day:
                funding_by_day[day] = self.funding.adjustments(day, day)
            funding = funding_by_day[day].get((tid, cid), {})
            amount = from_e6(row["amount_e6"]) - sum(funding.values(), ZERO) + linked.get((tid, cid), ZERO)
            if amount:
                shifts.append(dict(transaction_id=tid, category_id=cid, linked=False, posting_date=day,
                                   effective_date=row["estimate_date"], amount=amount))
        return shifts

    def estimate_attribution(self, transaction_id: int) -> list[dict]:
        return self._estimate_portions(transaction_id)

    @request_cached(deep=True)
    def _recovery_shifts(self, transaction_id: int | None = None) -> list[dict]:
        """Linked money back with its posting and resolved estimate dates: per receipt and spending category, the
        amount the receipt took off that category (never more than the amount linked) and both dates. Money back is a
        claim's receipt or a refund that names its purchase (NF-12AK3); money that is both counts once, as a receipt. The part
        of a refund that went back to the reserve that paid for the purchase (NF-12AK4) never reduced plan spending, so it
        does not move."""
        scope = "AND r.id=?" if transaction_id is not None else ""
        args = (transaction_id,) if transaction_id is not None else ()
        rows = [*self.db.all(
            "SELECT rr.id link_id,rr.amount_e6 linked_e6,r.id receipt_id,r.date receipt_date,COALESCE(rr.estimate_date_override,d.estimate_date,e.date) expense_date,e.id expense_id,"
            "le.category_id,SUM(le.amount_base_e6) total_e6 "
            "FROM reimbursement_receipts rr JOIN reimbursement_claims rc ON rc.id=rr.claim_id "
            "JOIN transactions r ON r.id=rr.receipt_id JOIN transactions e ON e.id=rc.expense_id "
            "LEFT JOIN budget_estimate_dates d ON d.transaction_id=e.id JOIN ledger_entries le ON le.transaction_id=r.id "
            "WHERE rc.paid_for_work=0 AND r.status='POSTED' AND e.status='POSTED' "
            "AND le.category_id IS NOT NULL AND le.effect IN ('INFLOW','OUTFLOW') AND le.owner_id IS NULL "
            f"{scope} GROUP BY rr.id,le.category_id ORDER BY rr.id,le.category_id", args), *self.db.all(
            "SELECT 'refund:'||rl.id link_id,"
            "rl.amount_e6-COALESCE((SELECT SUM(x.amount_e6) FROM reserve_refunds x WHERE x.refund_id=r.id),0)"
            "-COALESCE((SELECT SUM(work_e6) FROM work_claim_refund_lines WHERE transaction_id=r.id),0) linked_e6,"
            "r.id receipt_id,r.date receipt_date,COALESCE(rl.estimate_date_override,d.estimate_date,e.date) expense_date,e.id expense_id,le.category_id,"
            "SUM(le.amount_base_e6-COALESCE(w.work_e6,0)) total_e6 "
            "FROM refund_links rl JOIN transactions r ON r.id=rl.refund_id JOIN transactions e ON e.id=rl.expense_id "
            "LEFT JOIN budget_estimate_dates d ON d.transaction_id=e.id JOIN ledger_entries le ON le.transaction_id=r.id "
            "LEFT JOIN work_claim_refund_lines w ON w.transaction_id=le.transaction_id AND w.line_no=le.line_no "
            "WHERE r.status='POSTED' AND e.status='POSTED' "
            "AND le.category_id IS NOT NULL AND le.effect IN ('INFLOW','OUTFLOW') AND le.owner_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM reimbursement_receipts x WHERE x.receipt_id=rl.refund_id) "
            "AND le.category_id IN (SELECT category_id FROM ledger_entries WHERE transaction_id=rl.expense_id) "
            f"{scope} GROUP BY rl.id,le.category_id ORDER BY rl.id,le.category_id", args)]
        investment, shifts, left = self._investment_ids(), [], {}
        for row in rows:
            category = self.categories.get(int(row["category_id"]))
            if category.movement != Movement.OUTFLOW or category.id in investment:
                continue  # money back recorded as income never reduced spending, so there is nothing to move
            reduced = from_e6(int(row["total_e6"] or 0))  # a receipt line is positive when it takes from spending
            remaining = left.setdefault(row["link_id"], from_e6(int(row["linked_e6"])))
            amount = min(reduced, remaining)
            if amount <= ZERO:
                continue
            left[row["link_id"]] = remaining - amount
            shifts.append({"receipt_id": row["receipt_id"], "category_id": category.id, "amount": amount, "expense_id": int(row["expense_id"]),
                           "receipt_date": row["receipt_date"], "expense_date": row["expense_date"]})
        return shifts

    @request_cached(deep=True)
    def _left_out_lines(self) -> list[dict]:
        """What leaving expenses out takes from the estimate basis (NF-12AK2): per day and spending category, each
        left-out expense's own spending (positive) and the money back linked to it (negative, never more than the
        amount linked), so an expense and its refunds and claim receipts leave the basis together."""
        if not self.left_out_ids():
            return []
        owned = ("le.category_id IS NOT NULL AND le.effect IN ('INFLOW','OUTFLOW') AND le.owner_id IS NULL "
                 "AND le.category_id NOT IN (SELECT id FROM categories WHERE code='EXP.SYSTEM.CUSTODY')")
        expenses = self.db.all(
            "SELECT NULL link_id,0 linked_e6,t.id transaction_id,le.date,le.category_id,SUM(le.amount_base_e6-COALESCE(w.amount_e6,0)) total_e6 "
            "FROM budget_estimate_exclusions x JOIN transactions t ON t.id=x.transaction_id "
            "JOIN ledger_entries le ON le.transaction_id=t.id "
            "LEFT JOIN work_claim_allocations w ON w.transaction_id=le.transaction_id AND w.line_no=le.line_no "
            f"WHERE t.status='POSTED' AND {owned} GROUP BY t.id,le.category_id,le.date")
        back = self.db.all(  # money back: a claim's receipts, and refunds that name the purchase (NF-12AK3), once
            "SELECT 'claim:'||rr.id link_id,rr.amount_e6 linked_e6,NULL transaction_id,le.date,le.category_id,"
            "SUM(le.amount_base_e6) total_e6 FROM budget_estimate_exclusions x "
            "JOIN transactions e ON e.id=x.transaction_id JOIN reimbursement_claims rc ON rc.expense_id=e.id "
            "JOIN reimbursement_receipts rr ON rr.claim_id=rc.id JOIN transactions r ON r.id=rr.receipt_id "
            "JOIN ledger_entries le ON le.transaction_id=r.id "
            f"WHERE rc.paid_for_work=0 AND e.status='POSTED' AND r.status='POSTED' AND {owned} "
            "GROUP BY rr.id,le.category_id,le.date "
            "UNION ALL SELECT 'refund:'||rl.id link_id,"
            "rl.amount_e6-COALESCE((SELECT SUM(work_e6) FROM work_claim_refund_lines WHERE transaction_id=r.id),0) linked_e6,"
            "NULL transaction_id,le.date,le.category_id,"
            "SUM(le.amount_base_e6-COALESCE(w.work_e6,0)) total_e6 FROM budget_estimate_exclusions x "
            "JOIN transactions e ON e.id=x.transaction_id JOIN refund_links rl ON rl.expense_id=e.id "
            "JOIN transactions r ON r.id=rl.refund_id JOIN ledger_entries le ON le.transaction_id=r.id "
            "LEFT JOIN work_claim_refund_lines w ON w.transaction_id=le.transaction_id AND w.line_no=le.line_no "
            f"WHERE e.status='POSTED' AND r.status='POSTED' AND {owned} "
            "AND NOT EXISTS (SELECT 1 FROM reimbursement_receipts y WHERE y.receipt_id=rl.refund_id) "
            "GROUP BY rl.id,le.category_id,le.date ORDER BY 1,5,4")
        investment, lines, left = self._investment_ids(), [], {}
        for row in [*expenses, *back]:
            category = self.categories.get(int(row["category_id"]))
            if category.movement != Movement.OUTFLOW or category.id in investment:
                continue  # never part of the basis: income, or investment money
            amount = -from_e6(int(row["total_e6"] or 0))  # money out is a negative line, money back positive
            if row["link_id"] is not None:  # money back takes off at most what is linked to the expense
                remaining = left.setdefault(row["link_id"], from_e6(int(row["linked_e6"])))
                back_amount = min(-amount, remaining)
                if back_amount <= ZERO:
                    continue
                left[row["link_id"]] = remaining - back_amount
                amount = -back_amount
            if amount:
                lines.append({"date": row["date"], "category_id": category.id, "amount": amount,
                              "transaction_id": row["transaction_id"]})
        return lines

    @request_cached
    def _history_start(self) -> str | None:
        """The day the profile's first categorised money in or out was recorded: where its history begins."""
        row = self.db.one("SELECT MIN(le.date) first FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
                          "WHERE t.status='POSTED' AND le.category_id IS NOT NULL AND le.effect IN ('INFLOW','OUTFLOW') "
                          "AND le.owner_id IS NULL")
        if not row or not row["first"]:
            return None
        return min([row["first"], *(shift["effective_date"] for shift in self._estimate_portions())])

    def _full_window(self, month: str, months: int) -> bool:
        """True when the profile was already recording in the oldest of the `months` completed months before
        `month`: every month in the window is a real month, so one without spending counts as nothing spent."""
        first = self._history_start()
        cursor = parse_month(month)[0]
        for _ in range(months):
            cursor = parse_month(month_of(cursor - timedelta(days=1)))[0]
        return first is not None and first[:7] <= month_of(cursor)

    @staticmethod
    def _tree_average(tree: set[int], spending: list[dict[int, Decimal]], *,
                      full: bool = False) -> tuple[Decimal | None, int]:
        """A category tree's average and how many months had spending in it. With a full window (owner 2026-11-13)
        the average is over every month of it, so one 6,000 purchase in three months is 2,000; otherwise, while
        the profile is newer than the window, it is over the months that had spending."""
        observed = [sum((amounts.get(cid, ZERO) for cid in tree), ZERO)
                    for amounts in spending if any(cid in amounts for cid in tree)]
        if not observed:
            return None, 0
        months = len(spending) if full else len(observed)
        return (sum(observed, ZERO) / months).quantize(Decimal("0.01")), len(observed)

    def _outflow_children(self) -> tuple[dict[int, Category], dict[int, list[int]]]:
        categories = self.categories.tree(Movement.OUTFLOW)
        children: dict[int, list[int]] = {}
        for category in categories:
            if category.parent_id:
                children.setdefault(category.parent_id, []).append(category.id)
        return {category.id: category for category in categories}, children

    def tracked_ids(self, month: str, *, schedule: ScheduleView) -> set[int]:
        """Categories you track in a month: those with a rule of their own, and those you chose to track."""
        view = self.month_view(month, schedule=schedule)
        tracked = {line.category_id for section in view.sections for line in section.lines
                   if line.direct is not None or line.average_months or line.income_percent is not None}
        return tracked | (self._id_list("budget_tracked_categories") or set())

    def category_averages(self, month: str, *, schedule: ScheduleView) -> dict[int, dict]:
        """Each budget line's estimate basis (its subcategories included) averaged over the three and the six
        completed months before `month` (see _tree_average), how many of them had spending, and whether the profile
        covers the whole window (full3, full6: the Budget page's label)."""
        view = self.month_view(month, schedule=schedule)
        _, children = self._outflow_children()
        six = self._completed_months(month, 6)
        full3, full6 = self._full_window(month, 3), self._full_window(month, 6)
        averages = {}
        for section in view.sections:
            for line in section.lines:
                tree = {line.category_id} | self._descendant_ids(line.category_id, children)
                average3, observed3 = self._tree_average(tree, six[:3], full=full3)
                average6, observed6 = self._tree_average(tree, six, full=full6)
                averages[line.category_id] = {"average3": average3, "observed3": observed3, "full3": full3,
                                              "average6": average6, "observed6": observed6, "full6": full6,
                                              "spent6": sum((amounts.get(cid, ZERO) for amounts in six for cid in tree), ZERO)}
        return averages

    def tracking_suggestions(self, month: str, percent: Decimal, *, schedule: ScheduleView) -> list[dict]:
        """Untracked categories whose six-month average is at least `percent` of the month's budgeting
        income, unless one-off or dismissed (for good or for this month)."""
        income = self.budgeting_income(month, schedule=schedule)
        if not income:
            return []
        view = self.month_view(month, schedule=schedule)
        tracked, exclusions = self.tracked_ids(month, schedule=schedule), self.one_off_ids(with_children=False)
        by_id, _ = self._outflow_children()
        try:
            suppressed = json.loads(raw_setting(self.db, "budget_suppressed_categories") or "{}")
        except (ValueError, TypeError):
            suppressed = {}
        if isinstance(suppressed, list):
            suppressed = {str(category_id): "never" for category_id in suppressed}
        averages = self.category_averages(month, schedule=schedule)
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

    def background_estimates(self, month: str, *, schedule: ScheduleView, estimate_month: str | None = None) -> list[dict]:
        """Monthly expectations for untracked spending categories: the average of the last three
        completed months that had spending. They count in the month's plan (owner decision
        2026-10-03); an estimate from one observed month is low confidence and the screens say so.
        Categories that are tracked, one-off, have children, or sit under a parent's own limit
        (covered) are left out, so nothing is counted twice."""
        return [line for line in self.background(month, schedule=schedule, estimate_month=estimate_month) if line["estimate"] is not None]

    def background(self, month: str, tracked: set[int] | None = None, *, schedule: ScheduleView,
                   estimate_month: str | None = None) -> list[dict]:
        """Every untracked category background_estimates considers, with `estimate` None when it had no
        spending in the three completed months. `tracked` replaces the month's own tracked categories."""
        view = self.month_view(month, schedule=schedule)
        tracked = self.tracked_ids(month, schedule=schedule) if tracked is None else tracked
        exclusions = self.one_off_ids(with_children=False)
        by_id, children = self._outflow_children()
        groups = {group.category_id for section in view.sections for group in section.groups}
        basis = estimate_month or month
        months = self._completed_months(basis, 3)
        full = self._full_window(basis, 3)
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
                estimate, observed = self._tree_average({line.category_id}, months, full=full)
                lines.append({"category_id": line.category_id, "name": line.name, "group_id": parent.id,
                              "estimate": estimate, "observed": observed, "low_confidence": observed <= 1})
        return lines

    @request_cached(deep=True)
    def plan_summary(self, month: str, *, schedule: ScheduleView, estimate_month: str | None = None) -> dict:
        """The month's plan as every screen shows it: Planned (limits plus background estimates),
        Spent (owned spending funded by the monthly plan, one-off categories left out) and Left in plan."""
        view = self.month_view(month, schedule=schedule)
        estimates = self.background_estimates(month, schedule=schedule, estimate_month=estimate_month)
        planned = view.available + sum((e["estimate"] for e in estimates), ZERO)
        first, last = parse_month(month)
        one_offs = self.one_off_ids()
        spent = sum((v for cid, v in self.plan_funded_spending(first, last).items() if cid not in one_offs), ZERO)
        return {"planned": planned, "spent": spent, "left": planned - spent, "estimates": estimates,
                "low_confidence": [e for e in estimates if e["low_confidence"]]}

    def preview(self, month: str, *, schedule: ScheduleView) -> dict:
        """NF-12AL4 (owner rule 4, 2026-11-13): a month that has not started, as it will start. Read only: the limits
        that carry forward into it (this-month-only amounts do not), the bills, subscriptions and loan payments
        scheduled in it, and the income the plan will count (a dated basis from an income drop included). Carryover
        is left out: it is only known once the month before has ended."""
        view = self.month_view(month, schedule=schedule)
        names = {category.id: category.name for category in self.categories.tree()}
        groups = []
        for section in view.sections:
            group = None
            for line in section.lines:
                if line.depth == 1:
                    group = {"category_id": line.category_id, "name": line.name, "planned": line.budget or ZERO,
                             "lines": []}
                    if line.budget:
                        groups.append(group)
                elif line.depth == 2 and group is not None and line.budget:
                    group["lines"].append({"category_id": line.category_id, "name": line.name,
                                           "planned": line.budget, "from_bills": line.from_bills,
                                           "from_loans": line.from_loans})
        bills = [{"category_id": cid, "name": names.get(cid, ""), "amount": row["amount"], "items": list(row["items"])}
                 for cid, row in schedule.bills(month).items() if row["amount"]]
        loans = [{"category_id": cid, "name": names.get(cid, ""), "amount": amount}
                 for cid, amount in schedule.loans(month).items() if amount]
        bills.sort(key=lambda row: (-row["amount"], row["name"].casefold()))
        loans.sort(key=lambda row: (-row["amount"], row["name"].casefold()))
        income = self.income_average(month, schedule=schedule)
        planned = sum((group["planned"] for group in groups), ZERO)
        return {"month": month, "starts": parse_month(month)[0], "groups": groups, "planned": planned,
                "bills": bills, "bills_total": sum((row["amount"] for row in bills), ZERO),
                "loans": loans, "loans_total": sum((row["amount"] for row in loans), ZERO),
                "income": income.amount, "income_since": income.since, "income_manual": income.manual,
                "income_scheduled": income.scheduled, "income_first": income.first_month, "income_last": income.last_month,
                "left": None if income.amount is None else income.amount - planned}

    def set_income_percentage(self, category_id: int, month: str, percent: object,
                              only_this_month: bool = False) -> bool:
        parse_month(month); self._budgetable(category_id)
        value = check_places(to_decimal(percent, "percentage"), 2, "percentage")
        if value < ZERO or value > 10000:
            raise ValidationError("Enter an income percentage from 0 to 10,000.", "percentage")
        with self.db.transaction():
            self._write_rule(category_id, month, only_this_month, None, None, value)
        return True

    def reset_carryover(self, category_id: int, month: str, *, schedule: ScheduleView) -> None:
        """Set a dated boundary clearing carryover from this month onward."""
        parse_month(month)
        self._budgetable(category_id)
        if category_id not in self.amounts_for(month, schedule=schedule):
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
