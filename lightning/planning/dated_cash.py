"""Day-end cash from dated commitments, separate from the monthly free-cash estimate.

No assumed payday, flexible spending date, account transfer or reserve withdrawal is
invented. Amounts on scheduled items and deposit events are in their cash account's
currency, just as when a payment is recorded. Unassigned items use profile currency.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.core.money import ZERO


@dataclass(frozen=True)
class CashShortfall:
    date: str
    balance: Decimal
    currency: str
    account_id: int | None = None
    account_name: str | None = None


@dataclass(frozen=True)
class DatedCashBalance:
    date: str
    balance: Decimal | None


@dataclass(frozen=True)
class DatedCashForecast:
    through: str
    balances: tuple[DatedCashBalance, ...]
    first_shortfall: CashShortfall | None
    account_shortfalls: tuple[CashShortfall, ...]
    unassigned_payments: int
    unvalued_currencies: tuple[str, ...]


def dated_cash_forecast(reporting, payments, events, as_of: date, end: date) -> DatedCashForecast:
    """Project scheduled cash using today's owned cash and today's FX throughout.

    Overdue outgoings count today; overdue income has no reliable receipt date and
    is excluded. All movements on a day net together: there is no intraday claim.
    A missing FX rate suppresses the combined projection, never native warnings.
    Reserves remain in owned cash here; monthly free cash handles their protection.
    """
    day, through = as_of.isoformat(), end.isoformat()
    base = reporting.base_currency
    liquid = {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE}
    all_accounts = {a.id: a for a in reporting.accounts.list()}
    accounts = {key: a for key, a in all_accounts.items() if a.account_type in liquid}
    movements = defaultdict(lambda: defaultdict(lambda: ZERO))
    unassigned = 0
    missing = set()
    currency_rates = {base: Decimal(1)}

    def rate(currency):
        if currency not in currency_rates:
            quote = reporting.valuer.fx(currency, day)
            currency_rates[currency] = quote.rate if quote else None
        value = currency_rates[currency]
        if value is None:
            missing.add(currency)
        return value

    def add_movement(on, account_id, amount):
        nonlocal unassigned
        if account_id not in accounts:
            unassigned += 1
            # A legacy plan can point at a non-liquid foreign account. Retain
            # its denomination, but never imply that account can fund a bill.
            account = all_accounts.get(account_id)
            conversion = rate(account.currency if account else base)
            amount = amount * conversion if conversion is not None else ZERO
            account_id = None
        movements[on][account_id] += amount

    for payment in payments:
        if not payment.outstanding or payment.due_date > through:
            continue
        if payment.item.is_income and payment.due_date < day:
            continue
        amount = payment.still_owed if payment.item.is_income else -payment.still_owed
        add_movement(max(day, payment.due_date), payment.item.account_id, amount)
    for event in events:
        if day <= event.date <= through:
            account_id = getattr(event, "destination_account_id", getattr(event, "account_id", None))
            add_movement(event.date, account_id, event.amount)

    # Only cash quantities count, never a brokerage's securities or money held
    # for someone else. Native balances also work when an FX quote is unavailable.
    balances = {}
    rates = {None: Decimal(1)}
    used = {key for changes in movements.values() for key in changes}
    for account_id, account in accounts.items():
        owned = (reporting.account_balance(account_id, day)
                 - reporting.money_from_others.cash_total_for_account(account_id, day))
        if not owned and account_id not in used:
            continue
        balances[account_id] = owned
        rates[account_id] = rate(account.currency)
    balances[None] = ZERO

    def total():
        if missing:
            return None
        return sum(((value * rates[key]).quantize(Decimal("0.000001"))
                    for key, value in balances.items()), ZERO)

    def shortage(on, value, account_id=None):
        account = accounts.get(account_id)
        return CashShortfall(on, value, account.currency if account else base,
                             account_id, account.label if account else None)

    first = None
    account_shortfalls = {}
    points = []
    # Include the starting day even without future commitments. Today's overdue
    # payments are applied once, alongside any income actually due today.
    for on in sorted({day, *movements}):
        for account_id, amount in movements[on].items():
            balances[account_id] += amount
        combined = total()
        points.append(DatedCashBalance(on, combined))
        if first is None and combined is not None and combined < ZERO:
            first = shortage(on, combined)
        for account_id, value in balances.items():
            if account_id is not None and value < ZERO and account_id not in account_shortfalls:
                account_shortfalls[account_id] = shortage(on, value, account_id)
    return DatedCashForecast(through, tuple(points), first,
                            tuple(sorted(account_shortfalls.values(), key=lambda s: (s.date, s.account_id))),
                            unassigned, tuple(sorted(missing)))


def lowest_scheduled_balance(projection):
    """Earliest lowest day-end combined balance; unavailable when FX prevents projection."""
    known = [row for row in projection.balances if row.balance is not None]
    return min(known, key=lambda row: row.balance) if known else None
