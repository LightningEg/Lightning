"""Cost per purchase: a holding's lots and the pieces of every sale taken from them (NF-5B).

Derived from the ledger lines every time and never stored, so a back-dated edit leaves nothing stale to repair.
Two methods: ``average`` has one lot that absorbs every buy (the cost the portfolio showed before lots existed);
``fifo`` keeps every buy as its own lot and a sale takes the oldest first, cut across lots when it is bigger than the
oldest. A sale's proceeds are shared by units, and the last piece takes the rounding remainder so the pieces add up
to the sale. A pool is one account, asset and owner, so call it once per owner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, NamedTuple

from lightning.core.money import ZERO

METHODS = ("average", "fifo")
SPLIT_MARK = "Bonus or split"  # the description of the document that records one (an ADJ document, like Ownership entries)


def lot_type(doc_type: str, description: str = "") -> str:
    """The type a ledger line goes into the lots as: a bonus or split is SPL, anything else keeps its document type."""
    return "SPL" if doc_type == "ADJ" and description == SPLIT_MARK else doc_type
PLACES = Decimal("0.000001")  # money is kept to six decimals (e6)


def cost_returned(cost: Decimal, paid_back: Decimal) -> tuple[Decimal, Decimal]:
    """(cost removed, realized gain) when a fund pays back ``paid_back`` of a holding whose cost left is ``cost``.
    The one rule behind every average-cost walk: cost never falls below zero and the excess is a gain."""
    removed = min(paid_back, max(cost, ZERO))
    return removed, paid_back - removed


class LotLine(NamedTuple):
    """One ledger line of a holding, in date order: units (negative on a sale) and the money that moved."""
    date: str
    type: str  # BUY, SEL, ... (the document type), or SPL for a bonus or split (units change, cost does not)
    effect: str  # INTERNAL for a cost-only line such as a return of capital
    quantity: Decimal
    amount: Decimal  # cost added on a buy, minus what came back on a sale


def roi(gain: Decimal, cost: Decimal) -> Decimal | None:
    """Gain over what it cost, or None when nothing was paid."""
    return gain / cost if cost > ZERO else None


def cagr(end_value: Decimal, cost: Decimal, days: int) -> Decimal | None:
    """The yearly rate that turns ``cost`` into ``end_value`` over ``days`` (365-day years, as XIRR counts them), or
    None for less than a day, nothing paid or nothing left."""
    if days < 1 or cost <= ZERO or end_value <= ZERO:
        return None
    try:
        return (end_value / cost) ** (Decimal(365) / Decimal(days)) - 1
    except (ArithmeticError, ValueError):
        return None


@dataclass
class Lot:
    """One purchase, or what is left of it. Under ``average`` the single lot is every buy since it was last empty."""
    opened: str
    quantity: Decimal
    cost: Decimal
    owner_id: int | None = None

    def roi(self, price: Decimal) -> Decimal | None:
        """What this lot has made so far over what it cost, at ``price`` a unit."""
        return roi(self.quantity * price - self.cost, self.cost)

    def cagr(self, price: Decimal, as_of: str) -> Decimal | None:
        """The same per year, since it was bought."""
        return cagr(self.quantity * price, self.cost, (date.fromisoformat(as_of) - date.fromisoformat(self.opened)).days)


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

    @property
    def roi(self) -> Decimal | None:
        """What the sold piece made over what it cost; None for a return of capital (no units sold)."""
        return roi(self.gain, self.cost) if self.quantity else None

    @property
    def cagr(self) -> Decimal | None:
        """The same per year, from the purchase to the sale."""
        return cagr(self.proceeds, self.cost, self.days_held) if self.quantity else None


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
    if method == "fifo":
        return _fifo(lines, owner_id)
    book = LotBook()
    lot: Lot | None = None
    for line in lines:
        lot = lot or Lot(line.date, ZERO, ZERO, owner_id)
        quantity, amount = line.quantity, line.amount
        if line.type == "SPL":  # more or fewer units for the same cost
            lot.quantity += quantity
        elif quantity > 0:
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


def _shares(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split ``total`` in proportion to ``weights`` to six decimals; the last share takes the remainder."""
    whole = sum(weights, ZERO)
    parts: list[Decimal] = []
    for weight in weights[:-1]:
        parts.append((total * weight / whole).quantize(PLACES) if whole else ZERO)
    parts.append(total - sum(parts, ZERO))
    return parts


def _fifo(lines: Iterable[LotLine], owner_id: int | None) -> LotBook:
    book = LotBook()
    for line in lines:
        quantity, amount = line.quantity, line.amount
        if line.type == "SPL":  # every open lot gets its share of the new units; no cost moves
            if book.lots:
                for lot, share in zip(book.lots, _shares(quantity, [lot.quantity for lot in book.lots])):
                    lot.quantity += share
            else:
                book.lots.append(Lot(line.date, quantity, ZERO, owner_id))
        elif quantity > 0:
            book.lots.append(Lot(line.date, quantity, amount, owner_id))
            book.invested += amount
        elif quantity == 0:
            if line.effect == "INTERNAL" and amount < 0 and book.lots:  # a return of capital
                removed, _ = cost_returned(book.cost, -amount)
                # Each lot's cost falls in proportion to its cost, so none goes below zero.
                for lot, share in zip(book.lots, _shares(removed, [lot.cost for lot in book.lots])):
                    lot.cost -= share
                book.disposals.append(Disposal(book.lots[0].opened, line.date, ZERO, removed, -amount, owner_id))
            elif line.effect == "INTERNAL" and amount < 0:
                book.disposals.append(Disposal(line.date, line.date, ZERO, ZERO, -amount, owner_id))
        else:
            need = -quantity
            taken: list[tuple[Lot, Decimal, Decimal]] = []  # (lot, units, cost) for each piece
            for lot in list(book.lots):
                if need == ZERO:
                    break
                units = min(need, lot.quantity)
                cost = lot.cost if units == lot.quantity else lot.cost * units / lot.quantity
                taken.append((lot, units, cost))
                lot.quantity -= units
                lot.cost -= cost
                need -= units
            if need:  # more sold than held: the shortfall is a piece with no cost
                taken.append((Lot(line.date, ZERO, ZERO, owner_id), need, ZERO))
            if line.type == "SEL":
                proceeds = _shares(-amount, [units for _, units, _ in taken])
                for (lot, units, cost), got in zip(taken, proceeds):
                    book.disposals.append(Disposal(lot.opened, line.date, units, cost, got, owner_id))
            book.lots = [lot for lot in book.lots if lot.quantity != ZERO]
    return book
