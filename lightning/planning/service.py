"""Planned items, their payments, and what you owe."""
from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from lightning.core.dates import fmt_date, parse_date, parse_month, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, check_places, from_e6, to_decimal
from lightning.core.refs import parse_row_id
from lightning.database.connection import Database
from lightning.database.currencies import minor_units
from lightning.database.settings import SettingsStore
from lightning.fx import rate_for

from .domain import (Frequency, Payment, PaymentStatus, PlanKind, PlannedItem, WeekendMove, WhatYouOwe, per_year)
from .repository import PlanningRepository
from .schedule import payment_dates, previous_due, scheduled_dates

# New planned items start with the existing matching policy.
MATCH_WINDOW_DAYS = 7
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

    def create_purchase(self, *, name, price, fee, months, first_date, account_id=None, counterparty_id=None):
        """Create an instalment purchase as one journalable service action."""
        from .loan_actions import create_purchase
        return create_purchase(self, name=name, price=price, fee=fee, months=months, first_date=first_date,
                               account_id=account_id, counterparty_id=counterparty_id)

    def record_early_payment(self, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date=None):
        """Record an early payment and revise its schedule as one journalable action."""
        from .loan_actions import record_early_payment
        return record_early_payment(self, item_id, principal, fee, date_paid, account_id, expected_remaining, due_date)

    def _currency_of(self, account_id: int | None) -> str:
        return self.accounts.get(account_id).currency if account_id else self.transactions.base_currency

    def amount_in_base(self, payment_or_item: Payment | PlannedItem, amount: Decimal,
                       day: date | str) -> Decimal:
        """Value a native scheduled amount in profile currency at the rate known on ``day``."""
        item = payment_or_item.item if isinstance(payment_or_item, Payment) else payment_or_item
        base_currency = self.transactions.base_currency
        currency = (self.accounts.get(item.account_id).currency if item.account_id is not None
                    else base_currency)
        requested_day = day if isinstance(day, date) else parse_date(day)
        # A future schedule may use the latest rate we know today, never a rate added later.
        on = fmt_date(min(requested_day, today()))
        if currency == base_currency:
            return to_decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rate = rate_for(self.db, currency, base_currency, on)
        if rate is None:
            raise ValidationError(
                f"No {currency} exchange rate to {base_currency} is available on {on}. "
                "Add a rate before using this scheduled amount."
            )
        return (to_decimal(amount) * rate.rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def still_owed_in_base(self, payments, day: date | str) -> Decimal:
        """What is still owed on these payments, in the profile currency: the one total behind Bills due, Due
        before payday and the late payments (7N), never full amounts or a sum across currencies."""
        return sum((self.amount_in_base(p, p.still_owed, day) for p in payments), ZERO)

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

    def from_transaction(self, transaction_id: int) -> dict:
        """Prefill a monthly plan from one posted cash transaction, using its account currency."""
        txn = self.transactions.get(transaction_id)
        if txn.is_void or txn.type.value not in {"IN", "OUT"}:
            raise ValidationError("Only a posted cash income or expense can be turned into a plan.")
        receipt_link = self.db.one(
            "SELECT 1 FROM cd_interest_receipt_links WHERE transaction_id=? LIMIT 1", (transaction_id,))
        if receipt_link:
            raise ValidationError("A certificate interest receipt cannot be turned into a recurring plan.")
        from lightning.core.ledger import Effect
        expected_effect = Effect.INFLOW if txn.type.value == "IN" else Effect.OUTFLOW
        lines = [line for line in txn.lines if line.owner_id is None and line.effect == expected_effect
                 and self.accounts.get(line.account_id).account_type.value in {"BANK", "CASH", "BROKERAGE"}]
        account_ids = {line.account_id for line in lines}
        category_ids = {line.category_id for line in lines}
        if not lines or len(account_ids) != 1 or len(category_ids) != 1:
            raise ValidationError("Choose a single-account, single-category cash transaction to make a plan.")
        source = lines[0]
        account = self.accounts.get(source.account_id)
        kind = PlanKind.INCOME if txn.type.value == "IN" else PlanKind.BILL
        amount = sum((abs(line.quantity) for line in lines), ZERO)
        name = (txn.counterparty or txn.description or ("Income" if kind == PlanKind.INCOME else "Bill")).strip()
        source_day = parse_date(txn.date)
        today_day = today()
        month_day = source_day.day
        year, month = today_day.year, today_day.month
        while True:
            candidate = date(year, month, min(month_day, calendar.monthrange(year, month)[1]))
            if candidate > today_day:
                break
            month += 1
            if month > 12:
                year, month = year + 1, 1
        values = {"kind": kind.value, "name": name, "amount": f"{amount:.2f}", "frequency": "MONTHLY",
                  "interval_count": "1", "start_date": fmt_date(candidate), "end_date": "", "payment_count": "",
                  "account_id": str(account.id), "category_id": str(source.category_id or ""),
                  "counterparty": txn.counterparty or "", "principal": "", "notes": txn.notes,
                  "weekend_move": "none", "month_day": str(month_day),
                  "match_window_days": str(MATCH_WINDOW_DAYS),
                  "match_tolerance_pct": "10"}
        return {"values": values, "transaction": txn, "currency": account.currency}

    def is_installment_purchase(self, item_id: int) -> bool:
        return item_id in self.repo.installment_terms()

    def update(self, item_id: int, **values) -> None:
        old = self.get(item_id)
        values.setdefault("match_window_days", old.match_window_days)
        values.setdefault("match_tolerance_pct", old.match_tolerance_pct)
        clean = self._validate(values)
        if item_id in self.repo.installment_terms() and any(
                clean[key] != getattr(old, key) for key in ("amount", "payment_count", "frequency", "interval_count")):
            raise ValidationError("This purchase's payment amount and count come from its price and fee.")
        if clean["start_date"] == old.start_date and clean["frequency"] == Frequency.MONTHLY and "month_day" not in values:
            clean["month_day"] = old.month_day
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
        later = [d for _, d in payment_dates(item, fmt_date(day + timedelta(days=400))) if d > fmt_date(day)]
        if not later:
            return None
        with self.db.transaction():
            self.repo.set_start(item_id, later[0])
            if item.payment_count:
                # The payments before the new start are behind you: they still count toward a fixed
                # number of payments, so the plan does not grow (audit 2026-10-05 #10: 6 became 8).
                passed = sum(1 for _, d in payment_dates(item, later[0]) if d < later[0])
                self.repo.set_payment_count(item_id, item.payment_count - passed)
        return later[0]

    def set_amount(self, item_id: int, amount) -> None:
        """Plan every later payment at a new amount (for example after paying a higher rent)."""
        value = to_decimal(amount, "amount")
        if value <= ZERO:
            raise ValidationError("Enter an amount above zero.", "amount")
        item = self.get(item_id)
        check_places(value, minor_units(self._currency_of(item.account_id)))  # never rounded silently (2E6)
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
        terms = self.repo.installment_terms().get(item.id) if item.kind == PlanKind.LOAN else None
        extras = [row for row in self.repo.extra_payments(fmt_date(day)) if row["planned_item_id"] == item.id] if item.kind == PlanKind.LOAN else []
        out = []
        for number, calendar_day, due in scheduled_dates(item, "2999-12-31" if terms or extras else until):
            # A payment settled before its weekend move changed stays settled under its old date.
            row = settled.get((item.id, due)) or settled.get((item.id, calendar_day))
            # A cash receipt dated later cannot clear debt in an earlier historical balance.
            if (item.kind == PlanKind.LOAN and row and row["status"] == PaymentStatus.PAID.value
                    and row["transaction_date"] > fmt_date(day)):
                row = None
            if row:
                status = PaymentStatus(row["status"])
            else:
                status = PaymentStatus.DUE if due <= fmt_date(day) else PaymentStatus.UPCOMING
            paid = from_e6(row["amount_e6"]) if row and status == PaymentStatus.PAID and row["amount_e6"] else None
            out.append(Payment(original, due, number, status, row["transaction_id"] if row else None, paid))
        if terms or extras:
            from .loan_actions import adjusted_payments
            out = adjusted_payments(out, terms, extras)
        end = until if isinstance(until, str) else fmt_date(until)
        return [p for p in out if p.due_date <= end]

    def all_payments(self, until: str | date, as_of: date | None = None,
                     kinds: tuple[PlanKind, ...] | None = None) -> list[Payment]:
        payments = [p for item in self.items(kinds) for p in self.payments(item, until, as_of)]
        return sorted(payments, key=lambda p: (p.due_date, p.item.name.casefold()))

    def match_payments(self, as_of: date | None = None) -> int:
        """Link only unambiguous one-to-one candidates under each item's saved policy."""
        if self.db.read_only:
            return 0  # a read-only copy shows payments as its home last settled them
        day = as_of or today()
        linked = self.repo.linked_transaction_ids()
        possible: dict[tuple[int, str], tuple[PlannedItem, Payment, dict[int, dict]]] = {}
        transaction_to_payments: dict[int, set[tuple[int, str]]] = {}
        for item in self.items():
            if not (item.category_id or item.counterparty_id):
                continue
            horizon = day + timedelta(days=item.match_window_days)
            for payment in self.payments(item, horizon, day):
                if payment.status not in (PaymentStatus.DUE, PaymentStatus.UPCOMING):
                    continue
                found = {c["id"]: c for c in self.candidates(payment, day) if c["id"] not in linked}
                key = (item.id, payment.due_date)
                possible[key] = (item, payment, found)
                for txn_id in found:
                    transaction_to_payments.setdefault(txn_id, set()).add(key)
        settled = [(key, item, payment, next(iter(found.values())))
                   for key, (item, payment, found) in possible.items()
                   if len(found) == 1 and len(transaction_to_payments.get(next(iter(found)), ())) == 1]
        if not settled:
            return 0
        count = 0
        with self.db.transaction():
            for _, item, payment, candidate in settled:
                if (self.repo.is_settled(item.id, payment.due_date) or
                        candidate["id"] in self.repo.linked_transaction_ids()):
                    continue  # a confirmation committed since the candidate read
                self.repo.settle(item.id, payment.due_date, "PAID", candidate["id"], candidate["amount"])
                linked.add(candidate["id"])
                count += 1
        return count

    def candidates(self, payment: Payment, as_of: date | None = None, loose: bool = False,
                   any_account: bool = False) -> list[dict]:
        """Candidates inside the planned item's saved date, amount, account, and currency policy.

        ``any_account`` is for a person's review (the pay popup, a transaction's page): money moved through
        another cash account in the item's currency counts. Automatic matching never sets it (7K)."""
        item, day = payment.item, as_of or today()
        if not (item.category_id or item.counterparty_id):
            return []
        expected = payment.still_owed if payment.outstanding else payment.amount
        due = date.fromisoformat(payment.due_date)
        window = item.match_window_days
        currency = self.accounts.get(item.account_id).currency if item.account_id else self.transactions.base_currency
        rows = self.repo.candidates(item.is_income, None if any_account else item.account_id,
                                    None if loose else item.category_id,
                                    None if loose else item.counterparty_id,
                                    fmt_date(due - timedelta(days=window)),
                                    fmt_date(min(due + timedelta(days=window), day)), currency,
                                    require_all_identity=not loose)
        tolerance = Decimal(item.match_tolerance_pct) / Decimal(100)
        return [r for r in rows if abs(r["amount"] - expected) <= expected * tolerance]

    def plausible_candidates(self, payment: Payment, as_of: date | None = None) -> list[dict]:
        """Read-only wider suggestions; a user must explicitly choose one to link it.

        From any of the owner's cash accounts in the item's currency. Leaves out a transaction that already
        settles a payment, and one nearer the previous due date than this one: that is last period's (7K)."""
        item, day = payment.item, as_of or today()
        expected = payment.still_owed if payment.outstanding else payment.amount
        if not (item.counterparty_id or item.category_id):
            return []
        due = date.fromisoformat(payment.due_date)
        window = max(item.match_window_days, 45)
        currency = self.accounts.get(item.account_id).currency if item.account_id else self.transactions.base_currency
        rows = self.repo.candidates(
            item.is_income, None, item.category_id, item.counterparty_id,
            fmt_date(due - timedelta(days=window)),
            fmt_date(min(due + timedelta(days=window), day)), currency)
        strict = {row["id"] for row in self.candidates(payment, day, any_account=True)}
        linked = self.repo.linked_transaction_ids()
        previous = previous_due(item, payment.due_date)
        before = date.fromisoformat(previous) if previous else None
        tolerance = Decimal(max(item.match_tolerance_pct, 50)) / Decimal(100)
        return [row for row in rows if row["id"] not in strict and row["id"] not in linked
                and not (before and abs((date.fromisoformat(row["date"]) - before).days)
                         < abs((date.fromisoformat(row["date"]) - due).days))
                and abs(row["amount"] - expected) <= expected * tolerance]

    @request_cached
    def early_payments(self, as_of: date | None = None) -> list[dict]:
        """Next payments whose money has already moved: pay that arrived (or a bill that went out) before its due date.

        An unlinked, posted transaction from the same counterparty and category, within the item's amount
        tolerance, dated after the middle of the period before the due date (so nearer this payment than the
        last one). Only when it is the one candidate and no payment is already late. Nothing is linked: the
        forecast stops counting that payment a second time, and Needs you offers the link (7K)."""
        day = as_of or today()
        linked = self.repo.linked_transaction_ids()
        found: list[dict] = []
        for item in self.items((PlanKind.INCOME, PlanKind.BILL, PlanKind.SUBSCRIPTION)):
            if not (item.counterparty_id and item.category_id) or item.frequency == Frequency.ONCE:
                continue
            reach = 7 * item.interval_count + 7 if item.frequency == Frequency.WEEKLY else 31 * item.interval_count * (
                {Frequency.MONTHLY: 1, Frequency.QUARTERLY: 3, Frequency.YEARLY: 12}[item.frequency]) + 7
            open_ = [p for p in self.payments(item, day + timedelta(days=reach), day) if p.outstanding]
            if not open_ or open_[0].status != PaymentStatus.UPCOMING:
                continue  # nothing is open, or an earlier payment is late and the normal matching comes first
            payment = open_[0]
            due = date.fromisoformat(payment.due_date)
            previous = date.fromisoformat(previous_due(item, payment.due_date))
            first = previous + (due - previous) / 2 + timedelta(days=1)
            if first > day:
                continue
            currency = self.accounts.get(item.account_id).currency if item.account_id else self.transactions.base_currency
            tolerance = Decimal(item.match_tolerance_pct) / Decimal(100)
            rows = [r for r in self.repo.candidates(item.is_income, None, item.category_id, item.counterparty_id,
                                                    fmt_date(first), fmt_date(day), currency, require_all_identity=True)
                    if r["id"] not in linked and abs(r["amount"] - payment.still_owed) <= payment.still_owed * tolerance]
            if len(rows) == 1:
                found.append({"item": item, "payment": payment, "transaction": rows[0]})
        taken: dict[int, int] = {}
        for row in found:
            taken[row["transaction"]["id"]] = taken.get(row["transaction"]["id"], 0) + 1
        return sorted((r for r in found if taken[r["transaction"]["id"]] == 1),
                      key=lambda r: (r["payment"].due_date, r["item"].name.casefold()))

    def linked_transaction_ids(self) -> set[int]:
        return self.repo.linked_transaction_ids()

    def mark_paid(self, item_id: int, due_date: str, transaction_id: int) -> None:
        # The current occurrence and source link are read under the same writer lock as the save.
        with self.db.transaction():
            self._mark_paid(item_id, due_date, transaction_id)

    def _mark_paid(self, item_id: int, due_date: str, transaction_id: int) -> None:
        item = self.get(item_id)
        try:
            due = date.fromisoformat(due_date)
        except (TypeError, ValueError):
            raise ValidationError("Choose a scheduled payment date.") from None
        scheduled = next((payment for payment in self.payments(item, due) if payment.due_date == due_date), None)
        if not scheduled:
            raise ValidationError("That date is not on this payment schedule.")
        if (scheduled.status == PaymentStatus.PAID and scheduled.transaction_id == transaction_id or
                self.db.scalar("SELECT 1 FROM loan_extra_payments WHERE planned_item_id=? "
                               "AND transaction_id=? AND due_date=?", (item_id, transaction_id, due_date))):
            return  # retry of this exact confirmation
        if (self.repo.is_settled(item_id, due_date) and
                not (item.kind == PlanKind.LOAN and scheduled.status == PaymentStatus.PAID and scheduled.outstanding)):
            raise ValidationError("This payment is already settled. Reopen it before linking a different transaction.")
        if transaction_id in self.repo.linked_transaction_ids():
            raise ValidationError("That transaction already settles another payment.")
        currency = self.accounts.get(item.account_id).currency if item.account_id else self.transactions.base_currency
        txn = self.repo.payment_transaction(transaction_id, item.is_income, None,  # a person may pick any cash account
                                           item.category_id, item.counterparty_id, currency)
        if not txn:
            raise ValidationError("Choose a posted, owned transaction for this account and payment.")
        if abs((date.fromisoformat(txn["date"]) - due).days) > max(item.match_window_days, 45):
            raise ValidationError("That transaction is too far from the scheduled payment date.")
        expected = scheduled.still_owed if scheduled.outstanding else scheduled.amount
        tolerance = Decimal(max(item.match_tolerance_pct, 50)) / Decimal(100)
        if abs(txn["amount"] - expected) > expected * tolerance:
            raise ValidationError("That transaction amount is too far from the planned payment.")
        with self.db.transaction():
            if item.kind == PlanKind.LOAN and scheduled.status == PaymentStatus.PAID and scheduled.outstanding:
                if txn["amount"] > scheduled.still_owed:
                    raise ValidationError("Pay no more than this instalment's remaining amount.")
                self.repo.add_extra_payment(item.id, transaction_id, txn["amount"], ZERO, due_date)
            else:
                self.repo.settle(item.id, due_date, "PAID", transaction_id, txn["amount"])

    def record_payment(self, item_id: int, due_date: str, date_paid: str, amount, account_id: int | None) -> int:
        """Post the payment as a normal transaction and link it."""
        item = self.get(item_id)
        try:
            due = fmt_date(parse_date(due_date, "due_date"))
        except ValidationError:
            raise ValidationError("Choose a scheduled payment date.", "due_date") from None
        selected_account = (account_id if account_id is not None and str(account_id).strip() else item.account_id)
        if not selected_account:
            raise ValidationError("Choose the account the money moved through.", "account_id")
        try:
            selected_account_id = int(selected_account)
            account = self.accounts.get(selected_account_id)
        except (TypeError, ValueError, OverflowError, NotFoundError):
            raise ValidationError("Choose a valid cash account.", "account_id") from None
        if account.account_type.value not in {"BANK", "CASH", "BROKERAGE"}:
            raise ValidationError("Choose a cash account.", "account_id")
        item_currency = (self.accounts.get(item.account_id).currency if item.account_id
                         else self.transactions.base_currency)
        if account.currency != item_currency:
            raise ValidationError(f"Choose an account in {item_currency} to pay this planned item.", "account_id")
        if item.kind == PlanKind.LOAN and account.currency != self.transactions.base_currency:
            raise ValidationError("Choose a cash account in your profile currency.", "account_id")
        if item.kind == PlanKind.LOAN:
            payment = next((p for p in self.payments(item, "2999-12-31") if p.due_date == due), None)
            if payment and payment.status == PaymentStatus.PAID and payment.outstanding:
                from .loan_actions import record_early_payment
                value = to_decimal(amount, "amount")
                if value > payment.still_owed:
                    raise ValidationError("Pay no more than this instalment's remaining amount.", "amount")
                remaining = self.loan_progress(item)["still_to_pay"]
                return record_early_payment(self, item.id, value, "0", date_paid, selected_account_id,
                                            remaining, due_date=due)
        scheduled = next((payment for payment in self.payments(item, due)
                          if payment.due_date == due), None)
        if scheduled is None:
            raise ValidationError("That date is not on this payment schedule.", "due_date")
        if not item.category_id:
            raise ValidationError(f"Give {item.name} a category first, so its payments land in the right place.",
                                  "category_id")
        value = to_decimal(amount, "amount")
        if value <= ZERO:
            raise ValidationError("Enter the amount paid.", "amount")
        implicit_plan = self.is_installment_purchase(item.id) or item.month_day is not None
        party = self.counterparties.get(item.counterparty_id)["name"] if item.counterparty_id else ("" if implicit_plan else item.name)
        with self.db.transaction():
            if self.repo.is_settled(item.id, due):  # a second press or tab must not pay it twice
                raise ValidationError(f"{item.name} · {due} is already settled. Open it again first to change it.")
            record = self.transactions.record_inflow if item.is_income else self.transactions.record_outflow
            txn = record(fmt_date(parse_date(date_paid)), selected_account_id, value, item.category_id,
                         counterparty=party, description=item.name if implicit_plan else "",
                         notes=f"{item.kind_label} · {item.name}")
            self.repo.settle(item.id, due, "PAID", txn.id, value)
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
        due = [p for p in self.all_payments(day, day, outgoing) if p.outstanding]
        loans_left = ZERO
        for item in self.items((PlanKind.LOAN,)):
            # The schedule bounds itself (count or last date, extended by skips).
            loans_left += sum((self.amount_in_base(p, p.still_owed, day)
                               for p in self.payments(item, "2999-12-31", day)), ZERO)
        loans_due = sum((self.amount_in_base(p, p.still_owed, day)
                         for p in due if p.item.kind == PlanKind.LOAN), ZERO)
        return WhatYouOwe(bills_due=self.still_owed_in_base(due, day), loans_still_to_pay=loans_left,
                          bills_due_items=due, loans_due_in_base=loans_due)

    @request_cached  # read by every budget line since bills plan their category too (2026-10-05)
    def income_a_month(self, regular_only: bool = False) -> Decimal | None:
        """Recurring income a month: what Cash planning › Recurring expects to come in. None without any.

        ``regular_only`` leaves out the lumps (quarterly and yearly items, and anything in the Bonus
        category): the pay that arrives every month, which is what a raise changes (7L1)."""
        day = today()
        items = self.items((PlanKind.INCOME,))
        if regular_only:
            items = [i for i in items if i.frequency in (Frequency.MONTHLY, Frequency.WEEKLY) and not self._is_bonus(i)]
        monthly = ((item, per_year(item) / 12) for item in items)
        total = sum((self.amount_in_base(item, amount, day) for item, amount in monthly if amount), ZERO)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total > 0 else None

    def _is_bonus(self, item) -> bool:
        if item.category_id is None:
            return False
        code = self.categories.get(item.category_id).code
        return code == "EXP.WORK.BONUS" or code.startswith("EXP.WORK.BONUS.")

    def loan_payments_by_category(self, month: str) -> dict[int, Decimal]:
        """Loan payments scheduled in a month (paid, due or upcoming; not skipped), by category."""
        first, last = parse_month(month)
        out: dict[int, Decimal] = {}
        for item in self.items((PlanKind.LOAN,)):
            if item.category_id is None:
                continue
            for p in self.payments(item, last):
                if p.due_date >= fmt_date(first) and p.status != PaymentStatus.SKIPPED:
                    out[item.category_id] = out.get(item.category_id, ZERO) + self.amount_in_base(
                        p, p.amount, p.due_date)
        loans = {item.id: item for item in self.items((PlanKind.LOAN,))}
        for row in self.repo.extra_payments(fmt_date(today())):
            item = loans.get(row["planned_item_id"])
            if item and item.category_id and not row["due_date"] and row["date"].startswith(month):
                out[item.category_id] = out.get(item.category_id, ZERO) + from_e6(row["principal_e6"] + row["fee_e6"])
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
                row["amount"] += self.amount_in_base(payment, payment.amount, payment.due_date)
                row["items"].append(item.name)
        return out

    def loan_progress(self, item: PlannedItem, as_of: date | None = None) -> dict:
        payments = self.payments(item, "2999-12-31", as_of)
        paid = [p for p in payments if p.status == PaymentStatus.PAID]
        left = [p for p in payments if p.outstanding]
        skipped = [p for p in payments if p.status == PaymentStatus.SKIPPED]
        extras = [row for row in self.repo.extra_payments(fmt_date(as_of or today()))
                  if row["planned_item_id"] == item.id and not row["due_date"]]
        extras = [{**row, "principal": from_e6(row["principal_e6"]), "fee": from_e6(row["fee_e6"])} for row in extras]
        extra_paid = sum((row["principal"] for row in extras), ZERO)
        return {"total": len(payments) - len(skipped), "paid": len(paid), "left": len(left), "skipped": skipped,
                "still_to_pay": sum((p.still_owed for p in payments), ZERO),
                # What was actually paid: a partial instalment counts at its paid amount.
                "paid_amount": sum((p.amount - p.still_owed for p in paid), ZERO) + extra_paid,
                "total_amount": sum((p.amount for p in payments if p.status != PaymentStatus.SKIPPED), ZERO) + extra_paid,
                "extra_paid": extra_paid, "extra_payments": extras,
                "next": next((p for p in payments if p.outstanding), None),
                "due": [p for p in payments if p.outstanding and p.due_date <= fmt_date(as_of or today())],
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
        interval_raw = values.get("interval_count")
        try:
            interval = int(str(1 if interval_raw in (None, "") else interval_raw))
        except (TypeError, ValueError, OverflowError):
            raise ValidationError("Repeat every 1 to 52 periods.", "interval_count") from None
        if not 1 <= interval <= 52:
            raise ValidationError("Repeat every 1 to 52 periods.", "interval_count")
        start = fmt_date(parse_date(values.get("start_date"), "start_date"))
        end_raw = str(values.get("end_date") or "").strip()
        end = fmt_date(parse_date(end_raw, "end_date")) if end_raw else None
        if end and end < start:
            raise ValidationError("The last date must be on or after the first date.", "end_date")
        count_raw = str(values.get("payment_count") or "").strip()
        try:
            count = int(count_raw) if count_raw else None
        except (TypeError, ValueError, OverflowError):
            raise ValidationError("Enter 1 to 600 payments.", "payment_count") from None
        if count is not None and not 1 <= count <= 600:
            raise ValidationError("Enter 1 to 600 payments.", "payment_count")
        if kind == PlanKind.LOAN and count is None and end is None:
            raise ValidationError("Enter how many payments are left, or the last payment date.", "payment_count")
        principal_raw = str(values.get("principal") or "").strip()
        principal = to_decimal(principal_raw, "principal") if principal_raw else None
        account_id = self._id(values.get("account_id"), "account_id")
        if account_id:
            try:
                account = self.accounts.get(account_id)
            except NotFoundError:
                raise ValidationError("Choose a valid funding account.", "account_id") from None
            if kind == PlanKind.LOAN and account.currency != self.transactions.base_currency:
                raise ValidationError("Choose a cash account in your profile currency for a loan.", "account_id")
        check_places(amount, minor_units(self._currency_of(account_id)))  # never rounded silently (2E6)
        category_id = self._id(values.get("category_id"), "category_id")
        if category_id:
            try:
                self.categories.get(category_id)
            except NotFoundError:
                raise ValidationError("Choose a valid category.", "category_id") from None
        elif kind == PlanKind.LOAN:
            # Loan payments count as spending; without a choice they land in Loan payments.
            try:
                category_id = self.categories.get_by_code(LOAN_CATEGORY).id
            except NotFoundError:
                category_id = None
        counterparty_id = self._id(values.get("counterparty_id"), "counterparty_id")
        if counterparty_id:
            if self.counterparties.get(counterparty_id) is None:
                raise ValidationError("Choose a valid counterparty.", "counterparty_id")
        try:
            weekend_move = WeekendMove(str(values.get("weekend_move") or "none").lower())
        except ValueError:
            raise ValidationError("Choose what happens when a payment falls on a weekend.", "weekend_move") from None
        if frequency == Frequency.ONCE:
            weekend_move = WeekendMove.NONE  # a one-off payment keeps the date you chose
        try:
            raw_window = values.get("match_window_days")
            match_window_days = int(str(MATCH_WINDOW_DAYS if raw_window in (None, "") else raw_window))
        except (ValueError, TypeError):
            raise ValidationError("Choose a matching window from 0 to 31 days.", "match_window_days") from None
        if not 0 <= match_window_days <= 31:
            raise ValidationError("Choose a matching window from 0 to 31 days.", "match_window_days")
        default_tolerance = 1 if kind == PlanKind.LOAN else 10
        try:
            raw_tolerance = values.get("match_tolerance_pct")
            match_tolerance_pct = int(str(default_tolerance if raw_tolerance in (None, "") else raw_tolerance))
        except (ValueError, TypeError):
            raise ValidationError("Choose an amount tolerance from 0 to 25 percent.", "match_tolerance_pct") from None
        if not 0 <= match_tolerance_pct <= 25:
            raise ValidationError("Choose an amount tolerance from 0 to 25 percent.", "match_tolerance_pct")
        return {"kind": kind.value, "name": name, "amount": amount, "frequency": frequency.value,
                "interval_count": interval, "start_date": start, "end_date": end, "payment_count": count,
                "account_id": account_id, "category_id": category_id, "counterparty_id": counterparty_id,
                "principal": principal, "notes": str(values.get("notes") or "").strip(),
                "weekend_move": weekend_move.value, "month_day": self._month_day(values.get("month_day"), frequency),
                "match_window_days": match_window_days, "match_tolerance_pct": match_tolerance_pct}

    @staticmethod
    def _month_day(raw, frequency):
        if raw in (None, ""):
            return None
        try:
            day = int(str(raw))
        except ValueError:
            raise ValidationError("Choose a payday from 1 to 31.", "month_day") from None
        if not 1 <= day <= 31 or frequency != Frequency.MONTHLY:
            raise ValidationError("Choose a payday from 1 to 31 for monthly income.", "month_day")
        return day

    @staticmethod
    def _id(value, field: str = "id") -> int | None:
        return parse_row_id(value, field, "Choose a valid option.", blank=True)
