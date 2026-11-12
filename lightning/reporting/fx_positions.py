"""Foreign money you hold: what it cost, what it is worth, what it earned or lost.

Average cost, one pool per currency (Architecture › Foreign currency positions):
- money in adds units at the base value the ledger line carries (a conversion's executed rate, a salary or an
  opening balance at the day's rate);
- money out (spending, a fee, a conversion out) removes units at the average cost, and the gap between what the
  units fetched (the line's base value) and that cost is the *realized* FX gain;
- *unrealized* is today's value of what is still held minus what it cost;
- same-currency transfers and revaluation journals move no cost, and held-for-others lines are not yours.

Every cent is kept: cost and gains are whole cents, so for each currency

    unrealized + realized since the first holding = M - N

where M is the held units at the day's rate and N is the net base value of its non-revaluation ledger lines.
That is also the sum of the currency's FX revaluation journals up to the last month-end plus the change since
(`tests/test_fx_positions.py` checks it against the ledger). Nothing here writes to the database.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, parse_date
from lightning.core.money import ZERO, from_e6
from lightning.fx import Rate, rate_for, spread_cost

CENT = Decimal("0.01")
SIX = Decimal("0.000001")
FOREIGN_ACCOUNTS = (AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE)


@dataclass
class AccountHolding:
    account_id: int
    label: str
    balance: Decimal            # units you hold there, own and others' (what the bank shows)
    owned: Decimal
    value: Decimal | None       # owned, in the profile currency; None without a rate


@dataclass
class SeriesPoint:
    day: str
    value: Decimal | None       # held units at that day's rate
    cost: Decimal               # what the held units cost


@dataclass
class Position:
    currency: str
    units: Decimal = ZERO
    cost: Decimal = ZERO
    rate: Rate | None = None
    realized: Decimal = ZERO            # in the period asked
    realized_total: Decimal = ZERO      # since the first holding
    spread: Decimal = ZERO              # paid on conversions in the period that had a market rate
    conversions: int = 0
    conversions_unpriced: int = 0
    accounts: list[AccountHolding] = field(default_factory=list)
    series: list[SeriesPoint] = field(default_factory=list)
    investments: Decimal | None = None  # foreign investments in this currency at market, in the profile currency
    investments_unpriced: bool = False

    @property
    def average_rate(self) -> Decimal | None:
        return (self.cost / self.units).quantize(SIX) if self.units > 0 else None

    @property
    def value(self) -> Decimal | None:
        """Held units at the day's rate; without a rate, unavailable while an account or any units are there
        (an empty dollar account still asks for a dollar rate), zero once nothing is held anywhere."""
        if self.rate:
            return (self.units * self.rate.rate).quantize(CENT) if self.units > 0 else ZERO
        return ZERO if self.units <= 0 and not self.accounts else None

    @property
    def unrealized(self) -> Decimal | None:
        value = self.value
        return None if value is None else value - self.cost

    @property
    def rate_as_of(self) -> str | None:
        return self.rate.as_of if self.rate else None


@dataclass
class Other:
    """The currencies after the fourth, as one row."""
    currencies: list[str]
    value: Decimal
    unrealized: Decimal
    realized: Decimal
    spread: Decimal
    complete: bool              # every one of them has a rate


def month_ends(first: str, last: str, most: int = 24) -> list[str]:
    """Month-end dates from the month of `first` up to `last` (itself the final point), at most the last `most`."""
    days, year, month = [], int(first[:4]), int(first[5:7])
    while (year, month) < (int(last[:4]), int(last[5:7])):
        days.append(f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return (days + [last])[-most:]


class FxPositions:
    def __init__(self, db, accounts, assets, base_currency: str, balances):
        """`balances(account_id, day) -> (balance, owned)` is the reporting service's own, so what this page
        shows for an account is what its register shows."""
        self.db, self.accounts, self.assets = db, accounts, assets
        self.base, self.balances = base_currency, balances

    # -- the walk ------------------------------------------------------------
    def _lines(self, currency: str, end: str) -> list:
        return self.db.all(
            "SELECT le.date,le.quantity_e6,le.amount_base_e6 FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id JOIN financial_assets a ON a.id=le.asset_id "
            "WHERE a.is_cash=1 AND a.currency=? AND le.owner_id IS NULL AND t.status='POSTED' "
            "AND t.type NOT IN ('VAL','TRF') AND le.date<=? AND le.quantity_e6<>0 "
            "ORDER BY le.date,t.id,le.line_no", (currency, end))

    @staticmethod
    def walk(rows, start: str, end: str, checkpoints: list[str] | None = None):
        """(units, cost, realized in [start, end], realized total, [(checkpoint, units, cost)]) after the rows.

        Rows are (date, units_e6, base_e6) in ledger order. A balance that went below zero is not a position:
        it is held at zero units and zero cost until money comes back in."""
        units = cost = realized = realized_total = ZERO
        marks, pending = [], sorted(checkpoints or [])
        for row in rows:
            while pending and pending[0] < row["date"]:
                marks.append((pending.pop(0), units, cost))
            quantity, base = from_e6(row["quantity_e6"]), from_e6(row["amount_base_e6"])
            if quantity > 0:
                units += quantity
                cost += base
            else:
                out, proceeds = -quantity, -base
                if units <= 0:
                    continue
                if out >= units:
                    removed = cost
                    proceeds = proceeds * units / out if out > units else proceeds
                    units = ZERO
                else:
                    removed = (cost * out / units).quantize(CENT)
                    units -= out
                gain = (proceeds - removed).quantize(CENT)
                cost -= removed
                realized_total += gain
                if start <= row["date"] <= end:
                    realized += gain
        marks += [(day, units, cost) for day in pending]
        return units, cost, realized, realized_total, marks

    # -- one currency --------------------------------------------------------
    def position(self, currency: str, start: date | str, end: date | str) -> Position:
        first, last = fmt_date(parse_date(start)), fmt_date(parse_date(end))
        rows = self._lines(currency, last)
        units, cost, realized, realized_total, marks = self.walk(
            rows, first, last, month_ends(rows[0]["date"], last) if rows else [])
        result = Position(currency, units, cost, rate_for(self.db, currency, self.base, last), realized, realized_total)
        for day, held, spent in marks:
            found = rate_for(self.db, currency, self.base, day)
            result.series.append(SeriesPoint(day, (held * found.rate).quantize(CENT) if found and held > 0
                                             else (ZERO if held <= 0 else None), spent))
        self._conversions(result, first, last)
        self._accounts(result, last)
        return result

    def _conversions(self, result: Position, start: str, end: str) -> None:
        """Spread paid on this currency's conversions in the period (the foreign side of each)."""
        rows = self.db.all(
            "SELECT t.id,t.date,SUM(CASE WHEN le.effect='INTERNAL' AND le.quantity_e6<0 THEN -le.quantity_e6 END) AS sent,"
            "SUM(CASE WHEN le.effect='INTERNAL' AND le.quantity_e6>0 THEN le.quantity_e6 END) AS got,"
            "MAX(CASE WHEN le.effect='INTERNAL' AND le.quantity_e6<0 THEN a.currency END) AS sent_ccy,"
            "MAX(CASE WHEN le.effect='INTERNAL' AND le.quantity_e6>0 THEN a.currency END) AS got_ccy "
            "FROM transactions t JOIN ledger_entries le ON le.transaction_id=t.id "
            "JOIN financial_assets a ON a.id=le.asset_id "
            "WHERE t.type='CNV' AND t.status='POSTED' AND t.date BETWEEN ? AND ? GROUP BY t.id", (start, end))
        for row in rows:
            if result.currency not in (row["sent_ccy"], row["got_ccy"]):
                continue
            if self.base not in (row["sent_ccy"], row["got_ccy"]) and result.currency != row["got_ccy"]:
                continue  # one foreign into another is counted once, on the currency that arrived
            result.conversions += 1
            cost = spread_cost(self.db, self.base, from_e6(row["sent"]), row["sent_ccy"], from_e6(row["got"]),
                               row["got_ccy"], row["date"])
            if cost is None:
                result.conversions_unpriced += 1
            else:
                result.spread += cost

    def _accounts(self, result: Position, end: str) -> None:
        for account in self.accounts.list():
            if account.currency != result.currency or account.account_type not in FOREIGN_ACCOUNTS:
                continue
            balance, owned = self.balances(account.id, end)
            value = (owned * result.rate.rate).quantize(CENT) if result.rate else (ZERO if owned == 0 else None)
            result.accounts.append(AccountHolding(account.id, account.label, balance, owned, value))

    # -- the page ------------------------------------------------------------
    def currencies(self) -> list[str]:
        """Foreign currencies you hold or ever held in cash, or have an account in."""
        rows = self.db.all(
            "SELECT DISTINCT a.currency FROM ledger_entries le JOIN financial_assets a ON a.id=le.asset_id "
            "WHERE a.is_cash=1 AND a.currency<>? AND le.owner_id IS NULL ORDER BY a.currency", (self.base,))
        held = {row["currency"] for row in rows}
        held |= {a.currency for a in self.accounts.list() if a.currency != self.base and a.account_type in FOREIGN_ACCOUNTS}
        return sorted(held)

    def all(self, start: date | str, end: date | str) -> list[Position]:
        """Every foreign currency's position, the biggest value first (a currency without a rate last)."""
        found = [self.position(code, start, end) for code in self.currencies()]
        found = [p for p in found if p.units > 0 or p.accounts or p.realized or p.realized_total or p.conversions]
        return sorted(found, key=lambda p: (p.value is None, -(p.value or ZERO), p.currency))

    @staticmethod
    def totals(positions: list[Position]) -> dict:
        """The page's four headline figures across every currency, in the profile currency."""
        return {"value": sum((p.value or ZERO for p in positions), ZERO),
                "investments": sum((p.investments or ZERO for p in positions), ZERO),
                "unrealized": sum((p.unrealized or ZERO for p in positions), ZERO),
                "cost": sum((p.cost for p in positions if p.unrealized is not None), ZERO),  # what the cash held cost
                "realized": sum((p.realized for p in positions), ZERO),
                "spread": sum((p.spread for p in positions), ZERO),
                "complete": all(p.value is not None and not p.investments_unpriced for p in positions)}

    @staticmethod
    def held(totals: dict) -> Decimal:
        """IT-12AE4: Foreign money: the cash and the investments in totals(), in the profile currency."""
        return totals["value"] + totals["investments"]

    @staticmethod
    def split(positions: list[Position], shown: int = 4) -> tuple[list[Position], Other | None]:
        """Four currencies, then the rest as one *Other* row (guideline A16: five or more names)."""
        head, tail = positions[:shown], positions[shown:]
        if not tail:
            return head, None
        return head, Other([p.currency for p in tail],
                           sum((p.value or ZERO for p in tail), ZERO),
                           sum((p.unrealized or ZERO for p in tail), ZERO),
                           sum((p.realized for p in tail), ZERO),
                           sum((p.spread for p in tail), ZERO),
                           all(p.value is not None for p in tail))
