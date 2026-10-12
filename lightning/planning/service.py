"""Planned items, their payments, and what you owe."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, parse_date, parse_month, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, from_e6, to_decimal
from lightning.database.connection import Database
from lightning.database.settings import SettingsStore

from .domain import (Frequency, Payment, PaymentStatus, PlanKind, PlannedItem, WeekendMove, WhatYouOwe, per_year)
from .repository import PlanningRepository
from .schedule import payment_dates, scheduled_dates

# A posted transaction settles a scheduled payment when it lands within this many days of the
# due date and its amount is within the tolerance (loans are fixed instalments).
MATCH_WINDOW_DAYS = 7
SUGGESTION_WINDOW_DAYS = 45
MATCH_TOLERANCE = {PlanKind.LOAN: Decimal("0.01")}
DEFAULT_TOLERANCE = Decimal("0.10")
SUGGESTION_TOLERANCE = Decimal("0.50")
SUGGESTION_MINIMUM = Decimal("50")  # recurring amounts below this are not suggested
LOAN_CATEGORY = "EXP.SYSTEM.LOANS"
# Everyday spending repeats but belongs in the budget, not in Recurring (owner's UX plan, 2026-10-06).
EVERYDAY_CATEGORIES = ("EXP.PERSONAL.FOOD", "EXP.PERSONAL.DINING", "EXP.PERSONAL.SHOPPING",
                       "EXP.PERSONAL.TRANSPORT", "EXP.PERSONAL.ENTERTAINMENT")
NOT_RECURRING = "recurring_not_suggested"  # counterparty ids the user said are not recurring


class PlanningService:
    def __init__(self, db: Database, accounts, categories, counterparties, transactions):
        self.db = db
        self.repo = PlanningRepository(db)
        self.accounts = accounts
        self.categories = categories
        self.counterparties = counterparties
        self.transactions = transactions

    # ------------------------------------------------------------------ items
    def items(self, kinds: tuple[PlanKind, ...] | None = None, active_only: bool = True) -> list[PlannedItem]:
        items = self.repo.items(active_only)
        return [i for i in items if kinds is None or i.kind in kinds]

    def get(self, item_id: int) -> PlannedItem:
        item = self.repo.item(item_id)
        if not item:
            raise NotFoundError("That planned item was not found.")
        return item

    def create(self, **values) -> int:
        clean = self._validate(values)
        with self.db.transaction():
            return self.repo.insert(clean)

    def update(self, item_id: int, **values) -> None:
        self.get(item_id)
        clean = self._validate(values)
        with self.db.transaction():
            self.repo.update(item_id, clean)

    def start_after_paid(self, item_id: int, as_of: date | None = None) -> str | None:
        """The user says payments dated up to today are already paid: link any posted transaction
        that matches, and start the schedule at the next date instead of showing the rest as due.
        Returns the new first due date, or None when nothing changed. Not for loans."""
        day = as_of or today()
        self.match_payments(day)
        item = self.get(item_id)
        if item.kind == PlanKind.LOAN:
            return None
        payments = self.payments(item, fmt_date(day), day)
        if any(p.status == PaymentStatus.PAID for p in payments) or not any(
                p.status == PaymentStatus.DUE for p in payments):
            return None
        # The next date is read from the calendar date, not the due date: a weekend move must not
        # change the day the schedule keeps (the start is the anchor every later date counts from).
        later = [(cal, d) for _, cal, d in scheduled_dates(item, fmt_date(day + timedelta(days=400)))
                 if d > fmt_date(day)]
        if not later:
            return None
        next_calendar, next_due = later[0]
        anchor_day = date.fromisoformat(item.start_date).day
        clamped = (item.frequency in (Frequency.MONTHLY, Frequency.QUARTERLY, Frequency.YEARLY)
                   and date.fromisoformat(next_calendar).day != anchor_day)
        with self.db.transaction():
            if clamped:
                # A short month (the 31st on the 28th) cannot be an anchor: starting there would keep
                # the payment on the 28th for good. Keep the start and set the earlier dates aside.
                for payment in payments:
                    if payment.status == PaymentStatus.DUE:
                        self.repo.settle(item.id, payment.due_date, "SKIPPED", None, ZERO)
                return next_due
            self.repo.set_start(item_id, next_calendar)
            if item.payment_count:
                # The payments before the new start are behind you: they still count toward a fixed
                # number of payments, so the plan does not grow (audit 2026-10-05 #10: 6 became 8).
                passed = sum(1 for _, d in payment_dates(item, next_calendar) if d < next_calendar)
                self.repo.set_payment_count(item_id, item.payment_count - passed)
        return next_due

    def set_amount(self, item_id: int, amount) -> None:
        """Plan every later payment at a new amount (for example after paying a higher rent)."""
        value = to_decimal(amount, "amount")
        if value <= ZERO:
            raise ValidationError("Enter an amount above zero.", "amount")
        self.get(item_id)
        with self.db.transaction():
            self.repo.set_amount(item_id, value)

    def has_history(self, item_id: int) -> bool:
        return self.repo.has_payments(item_id)

    def remove(self, item_id: int) -> str:
        """Delete an item nobody paid yet; otherwise stop it and keep its history."""
        item = self.get(item_id)
        with self.db.transaction():
            if self.repo.has_payments(item_id):
                self.repo.set_active(item_id, False)
                return f"{item.name} stopped. Its paid history is kept."
            self.repo.delete(item_id)
        return f"{item.name} deleted."

    # --------------------------------------------------------------- payments
    def payments(self, item: PlannedItem, until: str | date, as_of: date | None = None) -> list[Payment]:
        day = as_of or today()
        settled = self.repo.settled()
        original = item
        if item.kind == PlanKind.LOAN:
            # A skipped loan payment is still owed: it moves to the end of the loan. A loan set by its
            # last date counts its payments up to that date first, so the skip is not cut off by it.
            skipped = sum(1 for (item_id, _), row in settled.items()
                          if item_id == item.id and row["status"] == PaymentStatus.SKIPPED.value)
            if skipped:
                count = item.payment_count or len(payment_dates(item, "2999-12-31"))
                item = replace(item, payment_count=count + skipped, end_date=None)
        out = []
        for number, calendar_day, due in scheduled_dates(item, until):
            # A payment settled before its weekend move changed stays settled under its old date.
            row = settled.get((item.id, due)) or settled.get((item.id, calendar_day))
            if row:
                status = PaymentStatus(row["status"])
            else:
                status = PaymentStatus.DUE if due <= fmt_date(day) else PaymentStatus.UPCOMING
            paid = from_e6(row["amount_e6"]) if row and status == PaymentStatus.PAID and row["amount_e6"] else None
            out.append(Payment(original, due, number, status, row["transaction_id"] if row else None, paid))
        return out

    def all_payments(self, until: str | date, as_of: date | None = None,
                     kinds: tuple[PlanKind, ...] | None = None) -> list[Payment]:
        payments = [p for item in self.items(kinds) for p in self.payments(item, until, as_of)]
        return sorted(payments, key=lambda p: (p.due_date, p.item.name.casefold()))

    def match_payments(self, as_of: date | None = None) -> int:
        """Link each due or near-due payment to the one posted transaction that clearly settles it."""
        if self.db.read_only:
            return 0  # a read-only copy shows payments as its home last settled them
        day = as_of or today()
        linked = self.repo.linked_transaction_ids()
        count = 0
        with self.db.transaction():
            for item in self.items():
                if not (item.category_id or item.counterparty_id):
                    continue  # nothing to recognise a payment by; the user marks it paid
                horizon = day + timedelta(days=MATCH_WINDOW_DAYS)
                for payment in self.payments(item, horizon, day):
                    if payment.status not in (PaymentStatus.DUE, PaymentStatus.UPCOMING):
                        continue
                    found = [c for c in self.candidates(payment, day) if c["id"] not in linked]
                    if len(found) == 1:
                        self.repo.settle(item.id, payment.due_date, "PAID", found[0]["id"], found[0]["amount"])
                        linked.add(found[0]["id"])
                        count += 1
        return count

    def candidates(self, payment: Payment, as_of: date | None = None, loose: bool = False) -> list[dict]:
        """Transactions that could settle ``payment``; ``loose`` widens the search for manual linking."""
        item, day = payment.item, as_of or today()
        due = date.fromisoformat(payment.due_date)
        window = 31 if loose else MATCH_WINDOW_DAYS
        rows = self.repo.candidates(item.is_income, item.account_id,
                                    None if loose else item.category_id,
                                    None if loose else item.counterparty_id,
                                    fmt_date(due - timedelta(days=window)),
                                    fmt_date(min(due + timedelta(days=window), day)))
        if loose:
            # Wider window for manual linking, but only plausible rows: the same counterparty
            # or category, or an amount within 10%. A 2,000 gift is not a 2,500 loan payment.
            return [r for r in rows if abs(r["amount"] - item.amount) <= item.amount * DEFAULT_TOLERANCE
                    or (item.counterparty_id and r["counterparty_id"] == item.counterparty_id)
                    or (item.category_id and item.category_id in r["category_ids"])]
        tolerance = MATCH_TOLERANCE.get(item.kind, DEFAULT_TOLERANCE)
        return [r for r in rows if abs(r["amount"] - item.amount) <= item.amount * tolerance]

    def plausible_candidates(self, payment: Payment, as_of: date | None = None) -> list[dict]:
        """Read-only wider suggestions; a user must explicitly choose one to link it."""
        item, day = payment.item, as_of or today()
        if not (item.counterparty_id or item.category_id):
            return []
        due = date.fromisoformat(payment.due_date)
        rows = self.repo.candidates(
            item.is_income, item.account_id, item.category_id, item.counterparty_id,
            fmt_date(due - timedelta(days=SUGGESTION_WINDOW_DAYS)),
            fmt_date(min(due + timedelta(days=SUGGESTION_WINDOW_DAYS), day)))
        strict = {row["id"] for row in self.candidates(payment, day)}
        return [row for row in rows if row["id"] not in strict
                and abs(row["amount"] - item.amount) <= item.amount * SUGGESTION_TOLERANCE]

    def linked_transaction_ids(self) -> set[int]:
        return self.repo.linked_transaction_ids()

    def mark_paid(self, item_id: int, due_date: str, transaction_id: int) -> None:
        item = self.get(item_id)
        try:
            due = date.fromisoformat(due_date)
        except (TypeError, ValueError):
            raise ValidationError("Choose a scheduled payment date.") from None
        if not any(payment.due_date == due_date for payment in self.payments(item, due)):
            raise ValidationError("That date is not on this payment schedule.")
        if transaction_id in self.repo.linked_transaction_ids():
            raise ValidationError("That transaction already settles another payment.")
        txn = self.repo.payment_transaction(transaction_id, item.is_income, item.account_id,
                                           item.category_id, item.counterparty_id)
        if not txn:
            raise ValidationError("Choose a posted, owned transaction for this account and payment.")
        if abs((date.fromisoformat(txn["date"]) - due).days) > SUGGESTION_WINDOW_DAYS:
            raise ValidationError("That transaction is too far from the scheduled payment date.")
        if abs(txn["amount"] - item.amount) > item.amount * SUGGESTION_TOLERANCE:
            raise ValidationError("That transaction amount is too far from the planned payment.")
        with self.db.transaction():
            self.repo.settle(item.id, due_date, "PAID", transaction_id, txn["amount"])

    def record_payment(self, item_id: int, due_date: str, date_paid: str, amount, account_id: int | None) -> int:
        """Post the payment as a normal transaction and link it."""
        item = self.get(item_id)
        account = account_id or item.account_id
        if not account:
            raise ValidationError("Choose the account the money moved through.", "account_id")
        if not item.category_id:
            raise ValidationError(f"Give {item.name} a category first, so its payments land in the right place.",
                                  "category_id")
        value = to_decimal(amount, "amount")
        if value <= ZERO:
            raise ValidationError("Enter the amount paid.", "amount")
        party = self.counterparties.get(item.counterparty_id)["name"] if item.counterparty_id else item.name
        with self.db.transaction():
            record = self.transactions.record_inflow if item.is_income else self.transactions.record_outflow
            txn = record(fmt_date(parse_date(date_paid)), int(account), value, item.category_id,
                         counterparty=party, notes=f"{item.kind_label} · {item.name}")
            self.repo.settle(item.id, due_date, "PAID", txn.id, value)
        return txn.id

    def skip(self, item_id: int, due_date: str) -> None:
        item = self.get(item_id)
        with self.db.transaction():
            self.repo.settle(item.id, due_date, "SKIPPED", None, ZERO)

    def reopen(self, item_id: int, due_date: str) -> None:
        self.get(item_id)
        with self.db.transaction():
            self.repo.unsettle(item_id, due_date)

    def suggestions(self, as_of: date | None = None) -> list[dict]:
        """Payments that look monthly in the last six months and aren't planned yet.

        Suggestions only: nothing is added until the user chooses to track it.
        """
        from statistics import median
        day = as_of or today()
        start = date(day.year - (1 if day.month <= 6 else 0), (day.month - 7) % 12 + 1, 1)
        groups: dict[tuple, list[dict]] = {}
        for row in self.repo.history(fmt_date(start), fmt_date(day)):
            groups.setdefault((row["counterparty_id"], row["effect"]), []).append(row)
        planned = {i.counterparty_id for i in self.items()} | {
            i.counterparty_id for i in self.items(active_only=False) if not i.active} | self._not_recurring()
        out = []
        for (party, effect), rows in groups.items():
            if party in planned or not self._may_recur(rows[-1]["category_id"]):
                continue
            months = {r["date"][:7] for r in rows}
            if len(months) < 3 or len(rows) > len(months) + 1:
                continue  # repeats monthly, not several times a month
            amounts = [r["amount"] for r in rows]
            typical = median(amounts)
            if typical < SUGGESTION_MINIMUM or any(abs(a - typical) > typical * Decimal("0.2") for a in amounts):
                continue  # too small to plan around (bank fees), or the amount varies too much
            latest = rows[-1]
            out.append({"counterparty_id": party, "name": latest["counterparty"],
                        "kind": "INCOME" if effect == "INFLOW" else "BILL", "amount": Decimal(typical).quantize(Decimal("0.01")),
                        "day": int(median(int(r["date"][8:]) for r in rows)), "months": len(months),
                        "account_id": latest["account_id"], "category_id": latest["category_id"],
                        "last_date": latest["date"]})
        return sorted(out, key=lambda s: (-s["months"], -s["amount"]))

    def _may_recur(self, category_id: int | None) -> bool:
        """Everyday spending is the budget's; investment income (certificate interest, dividends) is
        already in the forecast, so tracking it would count it twice."""
        if category_id is None:
            return True
        category = self.categories.get(category_id)
        if category.family == "INVESTMENT":
            return False
        return not any(category.code == code or category.code.startswith(code + ".") for code in EVERYDAY_CATEGORIES)

    def _not_recurring(self) -> set[int]:
        saved = SettingsStore(self.db).get(NOT_RECURRING)
        return {int(x) for x in saved.split(",") if x.strip().isdigit()} if saved else set()

    def not_recurring(self, counterparty_id: int) -> str:
        """Stop suggesting a counterparty in Looks recurring. Returns its name."""
        party = self.counterparties.get(counterparty_id)
        if party is None:
            raise NotFoundError("That counterparty no longer exists.")
        name = party["name"]
        SettingsStore(self.db).set(NOT_RECURRING, ",".join(str(i) for i in sorted(self._not_recurring() | {counterparty_id})))
        return name

    # -------------------------------------------------------------- what you owe
    def what_you_owe(self, as_of: date | None = None) -> WhatYouOwe:
        """Certain obligations only: unpaid payments already due, and loans still to pay."""
        day = as_of or today()
        outgoing = tuple(k for k in PlanKind if k != PlanKind.INCOME)
        due = [p for p in self.all_payments(day, day, outgoing) if p.status == PaymentStatus.DUE]
        loans_left = ZERO
        for item in self.items((PlanKind.LOAN,)):
            # The schedule bounds itself (count or last date, extended by skips).
            loans_left += sum((p.still_owed for p in self.payments(item, "2999-12-31", day)), ZERO)
        return WhatYouOwe(bills_due=sum((p.amount for p in due), ZERO), loans_still_to_pay=loans_left,
                          bills_due_items=due)

    @request_cached  # read by every budget line since bills plan their category too (2026-10-05)
    def income_a_month(self) -> Decimal | None:
        """Recurring income a month: what Cash planning › Recurring expects to come in. None without any."""
        total = sum((per_year(item) / 12 for item in self.items((PlanKind.INCOME,))), ZERO)
        return total.quantize(Decimal("0.01")) if total > 0 else None

    def loan_payments_by_category(self, month: str) -> dict[int, Decimal]:
        """Loan payments scheduled in a month (paid, due or upcoming; not skipped), by category."""
        first, last = parse_month(month)
        out: dict[int, Decimal] = {}
        for item in self.items((PlanKind.LOAN,)):
            if item.category_id is None:
                continue
            for p in self.payments(item, last):
                if p.due_date >= fmt_date(first) and p.status != PaymentStatus.SKIPPED:
                    out[item.category_id] = out.get(item.category_id, ZERO) + p.amount
        return out

    @request_cached(deep=True)  # rows hold lists of item names
    def budget_fill_schedule(self, month: str) -> dict[int, dict]:
        """Bill and subscription amounts due in a month, grouped by spending category.

        Loans are deliberately left to ``loan_payments_by_category``; budget rules already add
        those automatically when a category has no explicit rule.
        """
        first, last = parse_month(month)
        out: dict[int, dict] = {}
        for item in self.items((PlanKind.BILL, PlanKind.SUBSCRIPTION)):
            if item.category_id is None:
                continue
            for payment in self.payments(item, last):
                if payment.due_date < fmt_date(first) or payment.status == PaymentStatus.SKIPPED:
                    continue
                row = out.setdefault(item.category_id, {"amount": ZERO, "items": []})
                row["amount"] += payment.amount
                row["items"].append(item.name)
        return out

    def loan_progress(self, item: PlannedItem, as_of: date | None = None) -> dict:
        payments = self.payments(item, "2999-12-31", as_of)
        paid = [p for p in payments if p.status == PaymentStatus.PAID]
        left = [p for p in payments if p.outstanding]
        skipped = [p for p in payments if p.status == PaymentStatus.SKIPPED]
        return {"total": len(payments) - len(skipped), "paid": len(paid), "left": len(left), "skipped": skipped,
                "still_to_pay": sum((p.still_owed for p in payments), ZERO),
                # What was actually paid: a partial instalment counts at its paid amount.
                "paid_amount": sum((p.amount - p.still_owed for p in paid), ZERO),
                "total_amount": sum((p.amount for p in paid + left), ZERO),  # paid + still to pay
                "next": next((p for p in payments if p.outstanding), None),
                "due": [p for p in payments if p.status == PaymentStatus.DUE],
                "last_date": payments[-1].due_date if payments else None}

    # --------------------------------------------------------------- validation
    def _validate(self, values: dict) -> dict:
        try:
            kind = PlanKind(str(values.get("kind", "")).upper())
        except ValueError:
            raise ValidationError("Choose bill, subscription, income or loan.", "kind") from None
        name = str(values.get("name", "")).strip()
        if not name:
            raise ValidationError("Give it a name, like Rent or Car loan.", "name")
        amount = to_decimal(values.get("amount"), "amount")
        if amount <= ZERO:
            raise ValidationError("Enter the amount of each payment.", "amount")
        try:
            frequency = Frequency(str(values.get("frequency", "MONTHLY")).upper())
        except ValueError:
            raise ValidationError("Choose how often it repeats.", "frequency") from None
        interval = int(str(values.get("interval_count") or 1))
        if not 1 <= interval <= 52:
            raise ValidationError("Repeat every 1 to 52 periods.", "interval_count")
        start = fmt_date(parse_date(values.get("start_date"), "start_date"))
        end_raw = str(values.get("end_date") or "").strip()
        end = fmt_date(parse_date(end_raw, "end_date")) if end_raw else None
        if end and end < start:
            raise ValidationError("The last date must be on or after the first date.", "end_date")
        count_raw = str(values.get("payment_count") or "").strip()
        count = int(count_raw) if count_raw else None
        if count is not None and not 1 <= count <= 600:
            raise ValidationError("Enter 1 to 600 payments.", "payment_count")
        if kind == PlanKind.LOAN and count is None and end is None:
            raise ValidationError("Enter how many payments are left, or the last payment date.", "payment_count")
        principal_raw = str(values.get("principal") or "").strip()
        principal = to_decimal(principal_raw, "principal") if principal_raw else None
        account_id = self._id(values.get("account_id"))
        if account_id:
            self.accounts.get(account_id)
        category_id = self._id(values.get("category_id"))
        if category_id:
            self.categories.get(category_id)
        elif kind == PlanKind.LOAN:
            # Loan payments count as spending; without a choice they land in Loan payments.
            try:
                category_id = self.categories.get_by_code(LOAN_CATEGORY).id
            except NotFoundError:
                category_id = None
        counterparty_id = self._id(values.get("counterparty_id"))
        if counterparty_id:
            self.counterparties.get(counterparty_id)
        try:
            weekend_move = WeekendMove(str(values.get("weekend_move") or "none").lower())
        except ValueError:
            raise ValidationError("Choose what happens when a payment falls on a weekend.", "weekend_move") from None
        if frequency == Frequency.ONCE:
            weekend_move = WeekendMove.NONE  # a one-off payment keeps the date you chose
        return {"kind": kind.value, "name": name, "amount": amount, "frequency": frequency.value,
                "interval_count": interval, "start_date": start, "end_date": end, "payment_count": count,
                "account_id": account_id, "category_id": category_id, "counterparty_id": counterparty_id,
                "principal": principal, "notes": str(values.get("notes") or "").strip(),
                "weekend_move": weekend_move.value}

    @staticmethod
    def _id(value) -> int | None:
        text = str(value or "").strip()
        return int(text) if text.isdigit() else None
