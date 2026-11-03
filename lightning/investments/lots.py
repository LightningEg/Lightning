"""Cost per purchase: a holding's lots and the pieces of every sale taken from them (NF-5B).

Derived from the ledger lines every time and never stored, so a back-dated edit leaves nothing stale to repair.
This step knows one method, ``average``: one lot absorbs every buy, which is exactly the cost the portfolio
showed before lots existed. A pool is one account, asset and owner, so call it once per owner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, NamedTuple

from lightning.core.money import ZERO

METHODS = ("average",)


def cost_returned(cost: Decimal, paid_back: Decimal) -> tuple[Decimal, Decimal]:
    """(cost removed, realized gain) when a fund pays back ``paid_back`` of a holding whose cost left is ``cost``.
    The one rule behind every average-cost walk: cost never falls below zero and the excess is a gain."""
    removed = min(paid_back, max(cost, ZERO))
    return removed, paid_back - removed


class LotLine(NamedTuple):
    """One ledger line of a holding, in date order: units (negative on a sale) and the money that moved."""
    date: str
    type: str  # BUY, SEL, ... (the document type)
    effect: str  # INTERNAL for a cost-only line such as a return of capital
    quantity: Decimal
    amount: Decimal  # cost added on a buy, minus what came back on a sale


@dataclass
class Lot:
    """One purchase, or what is left of it. Under ``average`` the single lot is every buy since it was last empty."""
    opened: str
    quantity: Decimal
    cost: Decimal
    owner_id: int | None = None


@dataclass
class Disposal:
    """One piece of a sale (or of a return of capital, with no units) taken from one lot."""
    lot_opened: str
    sold: str
    quantity: Decimal
    cost: Decimal
    proceeds: Decimal
    owner_id: int | None = None

    @property
    def gain(self) -> Decimal:
        return self.proceeds - self.cost

    @property
    def days_held(self) -> int:
        return (date.fromisoformat(self.sold) - date.fromisoformat(self.lot_opened)).days


@dataclass
class LotBook:
    """What a pool's lines add up to."""
    lots: list[Lot] = field(default_factory=list)
    disposals: list[Disposal] = field(default_factory=list)
    invested: Decimal = ZERO  # every purchase, including the cost of units since sold

    @property
    def quantity(self) -> Decimal:
        return sum((lot.quantity for lot in self.lots), ZERO)

    @property
    def cost(self) -> Decimal:
        return sum((lot.cost for lot in self.lots), ZERO)

    @property
    def realized(self) -> Decimal:
        return sum((piece.gain for piece in self.disposals), ZERO)


def build_lots(lines: Iterable[LotLine], method: str = "average", owner_id: int | None = None) -> LotBook:
    """Replay a pool's lines, oldest first, into its open lots and the disposals made so far."""
    if method not in METHODS:
        raise ValueError(f"Unknown cost method: {method}")
    book = LotBook()
    lot: Lot | None = None
    for line in lines:
        lot = lot or Lot(line.date, ZERO, ZERO, owner_id)
        quantity, amount = line.quantity, line.amount
        if quantity > 0:
            lot.quantity += quantity
            lot.cost += amount
            book.invested += amount
        elif quantity == 0:
            if line.effect == "INTERNAL" and amount < 0:  # a return of capital: cost falls, the excess is a gain
                removed, _ = cost_returned(lot.cost, -amount)
                book.disposals.append(Disposal(lot.opened, line.date, ZERO, removed, -amount, owner_id))
                lot.cost -= removed
        else:
            average = lot.cost / lot.quantity if lot.quantity else ZERO
            removed = average * -quantity
            if line.type == "SEL":
                book.disposals.append(Disposal(lot.opened, line.date, -quantity, removed, -amount, owner_id))
            lot.cost -= removed
            lot.quantity += quantity
        if lot.quantity == ZERO:
            lot = None
    if lot is not None:
        book.lots.append(lot)
    return book
