"""An account on the phone (IV-3AY14, report: *An account*): its balance, the one question "Does CIB say 84,393?" with
*Yes* and *Fix it*, then the month's rows. Cash and bank accounts only; other kinds keep their own pages. Services
calculate; this module only picks and orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.core.dates import month_of, parse_month
from lightning.transactions.domain import DocType

ROWS = 60
KINDS = {AccountType.CASH, AccountType.BANK}


@dataclass(frozen=True)
class AccountScreen:
    id: int
    name: str
    currency: str
    balance: Decimal            # what the bank would show today, every owner included
    checked_through: str        # "" when never checked
    check_today: bool           # the question is open: not yet checked today
    month: str
    prev_month: str
    next_month: str             # "" for the current month
    rows: tuple                 # the month's register rows, newest first
    more_rows: bool
    active: bool = True
    owned: Decimal = Decimal(0)  # what is yours of it; the rest is held for others
    held: Decimal = Decimal(0)
    uses: int = 0               # plans, circles, certificates or reserves still using it (a Deactivate warning)


def is_cash_or_bank(c, account_id: int) -> bool:
    try:
        return c.accounts.get(account_id).account_type in KINDS
    except Exception:  # no such account: the older route says so
        return False


def _shift(month: str, step: int) -> str:
    first, _ = parse_month(month)
    return month_of(first + timedelta(days=32) if step > 0 else first - timedelta(days=1))


def build(c, account_id: int, day: date, month: str = "") -> AccountScreen:
    account = c.accounts.get(account_id)
    this = month_of(day)
    try:
        start, end = parse_month(month or this)
    except Exception:
        start, end = parse_month(this)
    shown = month_of(start)
    rows, total, _ = c.reporting.register_page(account_id, start, min(end, day), 1, ROWS)
    balance = c.reconciliation.balance(account_id, day.isoformat())
    owned = c.reporting.owned_account_value(account_id, day)
    checked = c.reconciliation.checked_through(account_id) or ""
    return AccountScreen(
        id=account.id, name=account.label, currency=account.currency,
        balance=balance, checked_through=checked,
        check_today=checked < day.isoformat(), month=shown, prev_month=_shift(shown, -1),
        next_month="" if shown >= this else _shift(shown, 1),
        rows=tuple(r for r in rows if r.type != DocType.VAL), more_rows=total > ROWS,
        active=account.active, owned=owned, held=balance - owned if owned != balance else Decimal(0), uses=int(c.linked.account(account_id)["count"]))
