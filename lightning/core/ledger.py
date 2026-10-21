"""Posting rules — the heart of the financial core. Pure Python, no database.

Every transaction (the document the user sees) is stored as one or more ledger lines.
All balances and reports are derived from ledger lines only.

Effects:
- INFLOW    value entering your finances (salary, interest)       -> needs an INFLOW category
- OUTFLOW   value leaving your finances (groceries, fees)         -> needs an OUTFLOW category
- INTERNAL  value moving inside your finances (transfers, buys)   -> must net to zero
- OPENING   balance that existed before you started tracking      -> no category
- REVALUATION system-generated value change                       -> zero units, amount is the account's return

Net-worth equation (per period):
    closing = opening + inflows - outflows + revaluation + new balances added

Cash lines vs investment lines:
- cash:        quantity == amount, unit price 1
- investment:  quantity = units (shares, fund units, grams); unit_price = the trade price;
               amount = what the units cost (buy, incl. fees) or fetched (sell, net of fees).
               So a buy or sell always nets to zero against its cash line; gains show as revaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from .errors import ValidationError
from .money import ONE, ZERO, decimal_places


class Effect(StrEnum):
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"
    INTERNAL = "INTERNAL"
    OPENING = "OPENING"
    REVALUATION = "REVALUATION"


@dataclass(frozen=True)
class PostingLine:
    account_id: int
    asset_id: int
    quantity: Decimal  # signed units (cash amount); REVALUATION deliberately has zero units
    effect: Effect
    unit_price: Decimal = ONE  # price or cost per unit, in the asset's currency
    fx_rate: Decimal = ONE  # asset currency -> base currency, fixed at transaction date
    category_id: int | None = None
    memo: str = ""
    amount: Decimal = field(default=ZERO)  # cash: = quantity; investment: cost or proceeds (asset currency)
    amount_base: Decimal = field(default=ZERO)  # amount x fx_rate (base currency, EGP)
    is_cash: bool = True  # not stored; tells the rules which kind of line this is
    owner_id: int | None = None

    @staticmethod
    def cash(
        account_id: int,
        asset_id: int,
        amount: Decimal,
        effect: Effect,
        category_id: int | None = None,
        memo: str = "",
        fx_rate: Decimal = ONE,
        owner_id: int | None = None,
    ) -> "PostingLine":
        """A cash line: quantity == amount, unit price 1."""
        return PostingLine(
            account_id=account_id,
            asset_id=asset_id,
            quantity=amount,
            unit_price=ONE,
            fx_rate=fx_rate,
            effect=effect,
            category_id=category_id,
            memo=memo,
            amount=amount,
            amount_base=_round2(amount * fx_rate),
            owner_id=owner_id,
        )

    @staticmethod
    def units(
        account_id: int,
        asset_id: int,
        quantity: Decimal,
        amount: Decimal,
        effect: Effect,
        trade_price: Decimal,
        memo: str = "",
        fx_rate: Decimal = ONE,
        owner_id: int | None = None,
    ) -> "PostingLine":
        """An investment line: units of a non-cash asset and what they cost / fetched."""
        return PostingLine(
            account_id=account_id,
            asset_id=asset_id,
            quantity=quantity,
            unit_price=trade_price,
            fx_rate=fx_rate,
            effect=effect,
            memo=memo,
            amount=amount,
            amount_base=_round2(amount * fx_rate),
            is_cash=False,
            owner_id=owner_id,
        )

    @staticmethod
    def revaluation(account_id: int, asset_id: int, amount: Decimal, fx_rate: Decimal = ONE,
                    memo: str = "Investment revaluation", owner_id: int | None = None,
                    is_cash: bool = True) -> "PostingLine":
        """Value-only adjustment: no cash movement and no units added or removed."""
        return PostingLine(account_id, asset_id, ZERO, Effect.REVALUATION, ONE, fx_rate,
                           memo=memo, amount=amount, amount_base=_round2(amount * fx_rate), is_cash=is_cash,
                           owner_id=owner_id)

def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def split_line_e6(amount_e6: int, rate_e6: int, take: int, total: int) -> tuple[int, int, int, int]:
    """Split a stored line (micro-units) into the part ``take/total`` and the rest, as ``validate_posting`` accepts
    them: each amount at whole cents (half up) and each base amount its own amount x rate. The two base amounts can
    differ by a cent from the line's, as two separate entries would (2G)."""
    cents, rest = divmod(abs(amount_e6) * take, total * 10_000)
    part = (-1 if amount_e6 < 0 else 1) * (cents + (rest * 2 >= total * 10_000)) * 10_000
    rate = Decimal(rate_e6) / Decimal(1_000_000)

    def base(value_e6: int) -> int:
        return int(_round2(Decimal(value_e6) / Decimal(1_000_000) * rate) * 1_000_000)

    return part, base(part), amount_e6 - part, base(amount_e6 - part)


def validate_posting(lines: list[PostingLine]) -> None:
    """Raise ValidationError unless the lines form a valid posting."""
    if not lines:
        raise ValidationError("A transaction needs at least one line.")
    internal_total = ZERO
    for i, line in enumerate(lines, start=1):
        if line.quantity == ZERO and line.effect != Effect.REVALUATION:
            raise ValidationError(f"Line {i}: amount cannot be zero.", "amount")
        for name in ("quantity", "unit_price", "fx_rate", "amount", "amount_base"):
            places = 2 if name == "amount_base" or (name == "amount" and line.effect != Effect.REVALUATION) else 6
            if decimal_places(getattr(line, name)) > places:
                raise ValidationError(f"Line {i}: {name} has more than {places} decimal places.")
        if line.unit_price < ZERO or line.fx_rate <= ZERO:
            raise ValidationError(f"Line {i}: price and exchange rate must be positive.")
        if line.is_cash and line.effect != Effect.REVALUATION and (line.unit_price != ONE or line.amount != line.quantity):
            raise ValidationError(f"Line {i}: a cash line's amount must equal its quantity.")
        if (not line.is_cash and line.effect != Effect.REVALUATION and line.amount != ZERO and
                (line.amount > ZERO) != (line.quantity > ZERO)):
            raise ValidationError(f"Line {i}: units in must cost money; units out must return money.")
        if line.amount_base != _round2(line.amount * line.fx_rate):
            raise ValidationError(f"Line {i}: base amount must equal amount x exchange rate.")
        if line.effect in (Effect.INFLOW, Effect.OUTFLOW) and line.category_id is None:
            raise ValidationError(f"Line {i}: money in and money out need a category.", "category")
        if line.effect == Effect.OPENING and line.category_id is not None:
            raise ValidationError(f"Line {i}: opening balances do not take a category.")
        if line.effect == Effect.INTERNAL:
            internal_total += line.amount_base
    if internal_total != ZERO:
        raise ValidationError(
            f"Internal movements must net to zero (they net to {internal_total})."
        )
