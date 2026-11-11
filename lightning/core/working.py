"""How a figure adds up (NF-12AB2): one shape for every headline figure's working.

The service that owns a figure returns its working as rows (name, signed amount, the row's own home), so the
"How it adds up" panel on the PC and the sheet on the phone draw the same rows, and no screen adds anything up.
For a money figure the rows sum to it; a ratio (savings rate, months covered) names its numerator and denominator.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import ZERO


@dataclass(frozen=True)
class WorkingRow:
    name: str
    amount: Decimal           # signed: what it adds to the figure (a deduction is negative)
    href: str = ""            # the row's own home, when it has one


@dataclass(frozen=True)
class Working:
    figure: str               # the registry key of the figure it explains
    total: Decimal | None     # the figure itself (a ratio's value for a ratio)
    rows: tuple[WorkingRow, ...]
    home: str = ""            # "Open <its home page>": the one link (A09.2)
    ratio_of: tuple[Decimal, Decimal] | None = None  # numerator and denominator, for a ratio

    @property
    def sum(self) -> Decimal:
        return sum((row.amount for row in self.rows), ZERO)

    @property
    def adds_up(self) -> bool:
        if self.ratio_of is not None:
            top, bottom = self.ratio_of
            return self.sum == top and (self.total is None or not bottom or abs(self.total - top / bottom * (100 if self.figure.endswith("rate") else 1)) < Decimal("0.05"))
        return self.total is not None and self.sum == self.total
