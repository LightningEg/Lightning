"""The month's payments by day, for the Upcoming tab (NF-7AR).

Every payment of one calendar month: planned bills, subscriptions, loan instalments and income, and each
gam'eya circle's instalments and payout. Each carries one state on the as-of day. The totals the page leads with
(Left to pay, Already paid) are worked out here, in the profile currency, never in a template.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from lightning.core.dates import fmt_date, parse_month
from lightning.core.money import ZERO
from lightning.fx import rate_for

from .domain import Payment, PaymentStatus, PlanKind

GROUPS = ("bills", "instalments", "gameya", "income")  # the page's filter chips, in this order
GROUP_OF = {PlanKind.BILL: "bills", PlanKind.SUBSCRIPTION: "bills", PlanKind.LOAN: "instalments",
            PlanKind.INCOME: "income"}


@dataclass(frozen=True)
class CalendarEntry:
    date: str
    group: str                 # one of GROUPS
    name: str
    amount: Decimal            # what the payment is for, in the profile currency
    left: Decimal              # what is still to pay (or still to come in) of it, in the profile currency
    state: str                 # paid | skipped | late | today | upcoming
    incoming: bool             # money in: income, a gam'eya payout
    number: int | None = None  # its place in a schedule with an end (loan 4 of 12, circle month 3 of 10)
    of: int | None = None
    item_id: int | None = None     # a planned item: its pay sheet
    circle_id: int | None = None   # a gam'eya circle: its page


@dataclass(frozen=True)
class PaymentMonth:
    month: str
    as_of: str
    entries: tuple[CalendarEntry, ...]
    left_to_pay: Decimal       # Left to pay: what the month's outgoing payments still ask, late ones included
    already_paid: Decimal      # Already paid: what of them is settled
    last_month_total: Decimal  # last month's outgoing payments, paid or not (the comparison)
    money_in: Decimal          # income and payouts dated in the month
    paydays: tuple[str, ...]   # dates of scheduled income in the month
    short_on: str | None = None          # the first day scheduled cash goes below zero, when it falls in the month
    short_by: Decimal | None = None
    groups: tuple[str, ...] = field(default=())  # the groups that have at least one entry this month

    @property
    def month_total(self) -> Decimal:
        return self.left_to_pay + self.already_paid

    @property
    def change_from_last_month(self) -> Decimal:
        """This month's outgoing payments against last month's: positive when this month asks more."""
        return self.month_total - self.last_month_total

    @property
    def days_to_pay(self) -> int:
        """How many days of the month still ask for money."""
        return len({e.date for e in self.entries if not e.incoming and e.left > ZERO})

    def on(self, day: str) -> list[CalendarEntry]:
        return [e for e in self.entries if e.date == day]


def _state(status: PaymentStatus, outstanding: bool, due: str, today: str) -> str:
    if status == PaymentStatus.SKIPPED:
        return "skipped"
    if not outstanding:
        return "paid"
    return "late" if due < today else "today" if due == today else "upcoming"


def _payment_entry(planning, p: Payment, day: date) -> CalendarEntry:
    text = fmt_date(day)
    amount = planning.amount_in_base(p, p.amount, day)
    left = planning.amount_in_base(p, p.still_owed, day) if p.outstanding else ZERO
    of = p.item.payment_count if p.item.kind == PlanKind.LOAN else None
    return CalendarEntry(p.due_date, GROUP_OF[p.item.kind], p.item.name, amount, left,
                         _state(p.status, p.outstanding, p.due_date, text), p.item.is_income,
                         p.number if of else None, of, item_id=p.item.id)


def _circle_entries(gameya, db, base: str, first: date, last: date, day: date) -> list[CalendarEntry]:
    if gameya is None:
        return []
    from lightning.deposits.gameya import installment_date, payout_date
    text, out = fmt_date(day), []
    for circle, terms in gameya.circles():
        progress = gameya.progress(circle.id, day)
        rate = Decimal(1)
        if circle.currency != base:
            quote = rate_for(db, circle.currency, base, text)
            if quote is None:
                continue  # unvalued: the circle's own page still shows it
            rate = quote.rate

        def money(value: Decimal) -> Decimal:
            return (value * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        for index in range(1, terms.members + 1):
            due = installment_date(terms, index)
            if first <= due <= last:
                paid = index <= progress.paid
                key = fmt_date(due)
                out.append(CalendarEntry(key, "gameya", circle.label, money(terms.installment),
                                         ZERO if paid else money(terms.installment),
                                         _state(PaymentStatus.PAID if paid else PaymentStatus.DUE, not paid, key, text),
                                         False, index, terms.members, circle_id=circle.id))
        turn = payout_date(terms)
        if first <= turn <= last:
            got = progress.payouts >= 1
            key = fmt_date(turn)
            out.append(CalendarEntry(key, "gameya", circle.label, money(terms.payout), ZERO if got else money(terms.payout),
                                     _state(PaymentStatus.PAID if got else PaymentStatus.DUE, not got, key, text),
                                     True, terms.my_turn, terms.members, circle_id=circle.id))
    return out


def _out_total(planning, month: str, day: date) -> Decimal:
    first, last = parse_month(month)
    return sum((planning.amount_in_base(p, p.amount, day) for p in planning.all_payments(last, day)
                if p.due_date >= fmt_date(first) and not p.item.is_income and p.status != PaymentStatus.SKIPPED), ZERO)


def month_calendar(planning, gameya, month: str, day: date, forecaster=None) -> PaymentMonth:
    """The month's payments and totals as they stand on ``day``. ``forecaster`` adds the first scheduled
    shortfall when it falls in the month (the forecast looks ahead only, so a past month never has one)."""
    first, last = parse_month(month)
    start = fmt_date(first)
    entries = [_payment_entry(planning, p, day) for p in planning.all_payments(last, day) if p.due_date >= start]
    base = planning.transactions.base_currency
    entries += _circle_entries(gameya, planning.db, base, first, last, day)
    entries.sort(key=lambda e: (e.date, e.incoming, e.name.casefold()))
    outgoing = [e for e in entries if not e.incoming and e.state != "skipped"]
    left = sum((e.left for e in outgoing), ZERO)
    paid = sum((e.amount - e.left for e in outgoing), ZERO)
    money_in = sum((e.amount for e in entries if e.incoming and e.state != "skipped"), ZERO)
    paydays = tuple(sorted({e.date for e in entries if e.group == "income"}))
    previous = fmt_date(first - timedelta(days=1))[:7]
    short_on = short_by = None
    if forecaster is not None and last >= day:
        dated = forecaster.forecast(day).dated
        shortfall = dated.first_shortfall if dated else None
        if shortfall and start <= shortfall.date <= fmt_date(last):
            short_on, short_by = shortfall.date, -shortfall.balance
    groups = tuple(g for g in GROUPS if any(e.group == g for e in entries))
    return PaymentMonth(month, fmt_date(day), tuple(entries), left, paid, _out_total(planning, previous, day),
                        money_in, paydays, short_on, short_by, groups)


@dataclass(frozen=True)
class WindowDay:
    date: str
    entries: tuple[CalendarEntry, ...]
    payday: bool
    short: bool                # the first day scheduled cash goes below zero

    @property
    def open(self) -> bool:
        """The day still asks for money."""
        return any(not e.incoming and e.left > ZERO for e in self.entries)


@dataclass(frozen=True)
class PaymentWindow:
    """``days`` days from ``start``, across a month end when they reach it (the Overview's week, the phone's two
    weeks). Late payments are dated before the window and are not in it: Needs you and the late list carry them."""
    start: str
    days: tuple[WindowDay, ...]
    left_to_pay: Decimal       # what the window's outgoing payments still ask
    to_pay: int                # how many outgoing payments in the window are still to pay
    month: PaymentMonth        # the start's month, for its Left to pay and its late payments

    @property
    def empty(self) -> bool:
        return not any(d.entries for d in self.days)

    @property
    def next_after(self) -> CalendarEntry | None:
        """The first payment still to pay after the window, in the start's month (the quiet week's one line)."""
        end = self.days[-1].date
        return next((e for e in self.month.entries if e.date > end and not e.incoming and e.left > ZERO), None)

    def on(self, day: str) -> tuple[CalendarEntry, ...]:
        found = next((d for d in self.days if d.date == day), None)
        return found.entries if found else tuple(self.month.on(day))


def payment_window(planning, gameya, start: date, days: int, forecaster=None, forecast=None) -> PaymentWindow:
    """``forecast`` is a CashForecast the caller already has (the Overview's); else ``forecaster`` makes one."""
    end = start + timedelta(days=days - 1)
    months = {}
    cursor = start.replace(day=1)
    while cursor <= end:
        key = fmt_date(cursor)[:7]
        months[key] = month_calendar(planning, gameya, key, start)
        cursor = parse_month(key)[1] + timedelta(days=1)
    short_on = None
    if forecast is None and forecaster is not None:
        forecast = forecaster.forecast(start)
    if forecast is not None:
        dated = forecast.dated
        short_on = dated.first_shortfall.date if dated and dated.first_shortfall else None
    rows = []
    for offset in range(days):
        key = fmt_date(start + timedelta(days=offset))
        month = months[key[:7]]
        rows.append(WindowDay(key, tuple(month.on(key)), key in month.paydays, key == short_on))
    outgoing = [e for d in rows for e in d.entries if not e.incoming and e.left > ZERO]
    return PaymentWindow(fmt_date(start), tuple(rows), sum((e.left for e in outgoing), ZERO), len(outgoing),
                         months[fmt_date(start)[:7]])
