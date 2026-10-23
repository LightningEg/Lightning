"""Investments — holdings of stocks, funds and gold inside accounts, and how they performed.

How the numbers work (average cost, the way THNDR shows it):
- Buy:   cost basis += what you paid (price × units + fees); units += bought.
- Sell:  cost removed = average cost × units sold; realized gain = what you received (after fees) − cost removed.
- Value: units × latest price (a price you entered, else the last buy/sell price, else your cost).
- Unrealized gain = value − cost basis still held.   Total return = unrealized + realized + dividends (after any tax withheld).
Nothing here is stored — it is all recalculated from the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from lightning.core.money import ZERO

from .returns import DisplayReturn

# Sale factor (percent of value a class would fetch if sold today) when none is set in Settings.
DEFAULT_SALE_FACTOR = Decimal(95)


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
