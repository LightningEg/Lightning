"""Investments — holdings of stocks, funds and gold inside accounts, and how they performed.

How the numbers work (average cost, the way THNDR shows it):
- Buy:   cost basis += what you paid (price × units + fees); units += bought.
- Sell:  cost removed = average cost × units sold; realized gain = what you received (after fees) − cost removed.
- Return of capital: no units move; cost removed = the amount paid back, but never more than the cost left; what is
  paid back beyond the cost left is a realized gain (NF-5A4, owner decision 2026-11-02).
- Value: units × latest price (a price you entered, else the last buy/sell price, else your cost).
- Unrealized gain = value − cost basis still held.   Total return = unrealized + realized + dividends (after any tax withheld).
Each holding's lots and sale pieces come from lots.py (NF-5B).
Nothing here is stored — it is all recalculated from the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal

from lightning.core.money import ZERO

from .lots import Disposal, Lot
from .returns import DisplayReturn

# Sale factor (percent of value a class would fetch if sold today) when none is set in Settings.
DEFAULT_SALE_FACTOR = Decimal(95)
# Real estate cannot be sold at short notice (NF-12M1): it counts nothing in Holdings after sale unless you set a factor.
SLOW_TO_SELL = {"REAL_ESTATE": ZERO}


def default_sale_factor(class_code: str) -> Decimal:
    """The sale factor a class uses when neither it nor a parent has one set."""
    return SLOW_TO_SELL.get(class_code, DEFAULT_SALE_FACTOR)


@dataclass
class Position:
    account_id: int
    account_label: str
    asset_id: int
    asset_code: str
    asset_name: str
    asset_class: str  # plain name, e.g. "Funds › Gold Fund"
    exposure: str
    unit: str
    quantity: Decimal
    cost_basis: Decimal  # cost of the units still held
    realized: Decimal  # gains/losses already locked in by sells
    dividends: Decimal
    price: Decimal | None
    price_date: str | None
    price_source: str  # MANUAL · TRADE · COST
    value: Decimal | None
    xirr: Decimal | None = None
    # Your own units and what they cost, apart from units held for someone else. Each owner's units keep
    # their own average cost, so your cost never blends in another owner's purchase prices.
    owned_quantity: Decimal | None = None
    owned_cost_basis: Decimal | None = None
    owned_realized: Decimal | None = None
    display_return: DisplayReturn | None = None
    invested: Decimal = ZERO  # all purchases, including the cost of units since sold
    owned_invested: Decimal = ZERO
    dividend_tax: Decimal = ZERO  # tax withheld from the dividends above (they are gross)
    owned_dividends: Decimal = ZERO
    owned_dividend_tax: Decimal = ZERO
    has_other_owners: bool = False
    lots: list[Lot] = field(default_factory=list)  # the purchases still held (NF-5B), every owner
    disposals: list[Disposal] = field(default_factory=list)  # the pieces of every sale so far
    flows: tuple = ()  # this holding's dated cash flows, money in negative, as XIRR reads them (NF-9E)

    @property
    def owned_net_dividends(self) -> Decimal:
        return self.owned_dividends - self.owned_dividend_tax

    @property
    def short_name(self) -> str:
        """What the holdings table calls it: a share by its ticker (COMI), anything else by its name."""
        return self.asset_code.split(":", 1)[1] if self.asset_code.startswith("STK:") else self.asset_name

    @property
    def net_dividends(self) -> Decimal:
        """What the dividends paid after tax withheld: the part that counts as return."""
        return self.dividends - self.dividend_tax

    def owned_result(self, units: Decimal, value: Decimal | None, cost: Decimal) -> dict:
        """Owned lifetime gain and plain return, using the original purchases as denominator.

        Cost pools and distributions keep the actual ledger owner, including after a sale.
        """
        gain = None if value is None else value - cost + (self.owned_realized or ZERO) + self.owned_net_dividends
        invested = self.owned_invested
        return {"gain": gain, "invested": invested,
                "gain_pct": gain / invested * 100 if gain is not None and invested else None}

    @property
    def average_cost(self) -> Decimal | None:
        return None if not self.quantity else (self.cost_basis / self.quantity)

    @property
    def unrealized(self) -> Decimal | None:
        return None if self.value is None else self.value - self.cost_basis

    @property
    def total_return(self) -> Decimal:
        return (self.unrealized or ZERO) + self.realized + self.net_dividends

    @property
    def is_open(self) -> bool:
        return self.quantity != ZERO

    def owned_only(self) -> Position:
        """This holding with your own units only: their cost, gains, dividends and share of the value. Its
        return and XIRR stay only when nobody else owns part of it."""
        factor = (self.owned_quantity or ZERO)/self.quantity if self.quantity else ZERO
        return replace(self, quantity=self.owned_quantity or ZERO, cost_basis=self.owned_cost_basis,
                       realized=self.owned_realized, dividends=self.owned_dividends,
                       dividend_tax=self.owned_dividend_tax,
                       value=(self.value*factor if self.value is not None else None),
                       xirr=None if self.has_other_owners else self.xirr,
                       display_return=None if self.has_other_owners else self.display_return)

    @property
    def gain_pct(self) -> Decimal | None:
        """Unrealized gain as a percent of the cost still held."""
        return self.unrealized / self.cost_basis * 100 if self.unrealized is not None and self.cost_basis else None

    @property
    def value_plus_paid(self) -> Decimal:
        """What you paid plus the total return: the value and everything it paid you."""
        return self.cost_basis + self.total_return

    @property
    def xirr_pct(self) -> Decimal | None:
        return self.xirr * 100 if self.xirr is not None else None

    def realized_since(self, previous: Position | None) -> Decimal:
        """Gain from sales since ``previous`` (this holding on an earlier day; None when it did not exist)."""
        return self.realized-(previous.realized if previous else ZERO)

    def dividends_since(self, previous: Position | None) -> Decimal:
        return self.dividends-(previous.dividends if previous else ZERO)


@dataclass
class Portfolio:
    as_of: str
    positions: list[Position] = field(default_factory=list)  # open and closed
    xirr: Decimal | None = None
    display_return: DisplayReturn | None = None

    @property
    def owned_realized(self) -> Decimal:
        return sum((p.owned_realized or ZERO for p in self.positions), ZERO)

    @property
    def owned_dividends(self) -> Decimal:
        return sum((p.owned_dividends for p in self.positions), ZERO)

    @property
    def has_other_owners(self) -> bool:
        return any(p.has_other_owners for p in self.positions)

    @property
    def open(self) -> list[Position]:
        return [p for p in self.positions if p.is_open]

    @property
    def closed(self) -> list[Position]:
        return [p for p in self.positions if not p.is_open]

    @property
    def cost_basis(self) -> Decimal:
        return sum((p.cost_basis for p in self.open), ZERO)

    @property
    def value(self) -> Decimal:
        return sum((p.value or ZERO for p in self.open), ZERO)

    @property
    def unrealized(self) -> Decimal:
        return sum((p.unrealized or ZERO for p in self.open), ZERO)

    @property
    def realized(self) -> Decimal:
        return sum((p.realized for p in self.positions), ZERO)

    @property
    def dividends(self) -> Decimal:
        return sum((p.dividends for p in self.positions), ZERO)

    @property
    def dividend_tax(self) -> Decimal:
        return sum((p.dividend_tax for p in self.positions), ZERO)

    @property
    def total_return(self) -> Decimal:
        return self.unrealized + self.realized + self.dividends - self.dividend_tax

    def allocation(self, by: str = "asset_class") -> list[tuple[str, Decimal, Decimal]]:
        """(group, value, share %) of the open positions, largest first. by = asset_class | exposure."""
        totals: dict[str, Decimal] = {}
        for p in self.open:
            key = getattr(p, by)
            totals[key] = totals.get(key, ZERO) + (p.value or ZERO)
        whole = sum(totals.values(), ZERO)
        rows = [(k, v, (v / whole * 100) if whole else ZERO) for k, v in totals.items()]
        return sorted(rows, key=lambda r: r[1], reverse=True)
