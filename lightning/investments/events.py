"""The table of investment events: what each kind of event does to units, cash, fees and income.

Adding an event kind is one row in ``EVENTS``. ``validate`` and ``lines_for`` are the only validator and the
only line builder for the kinds in the table; ``InvestmentService`` resolves accounts, assets, categories and
rates (it owns the database) and hands the result here as ``EventValues``. Nothing here reads the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect, PostingLine
from lightning.core.money import ZERO, check_places, fmt, to_decimal
from lightning.core.refs import DocType

DIVIDEND_CATEGORY = "EXP.INVEST.DIVIDEND"
TAX_CATEGORY = "EXP.INVEST.TAX"  # tax a broker withheld from a dividend
CENT = Decimal("0.01")


class Sign(Enum):
    """Which way a figure moves in the holding account (units) or the cash account (cash)."""
    IN = "in"
    OUT = "out"
    NONE = "none"
    NEW_BALANCE = "new_balance"  # units set by the event (bonus shares, splits): used from 5E


@dataclass(frozen=True)
class EventSpec:
    doc_type: DocType
    units: Sign
    cash: Sign
    fees: str  # "cost" (added to cost), "proceeds" (taken from proceeds), "none"
    income_category: str | None
    lowers_cost: bool = False


EVENTS: dict[str, EventSpec] = {
    "buy": EventSpec(DocType.BUY, Sign.IN, Sign.OUT, "cost", None),
    "sell": EventSpec(DocType.SEL, Sign.OUT, Sign.IN, "proceeds", None),
    "dividend": EventSpec(DocType.DIV, Sign.NONE, Sign.IN, "none", DIVIDEND_CATEGORY),
}


@dataclass
class EventValues:
    """What the service resolved (accounts, asset, ids, rates) plus what the person typed (raw text)."""
    asset: object  # FinancialAsset: id, code, quantity_decimals, unit
    account: object  # the holding account (the broker, for a dividend)
    cash_account: object | None = None  # where the cash moves; the holding account itself when None
    cash_asset_id: int = 0
    holding_rate: Decimal = Decimal(1)
    cash_rate: Decimal = Decimal(1)
    category_ids: dict | None = None  # category code -> id, for the spec's income and tax lines
    quantity: object = None
    price: object = None
    fees: object = "0"
    total: object = None
    total_fees: object = "0"
    fees_included: bool = True
    amount: object = None
    tax: object = "0"


@dataclass(frozen=True)
class _Figures:
    units: Decimal = ZERO
    unit_price: Decimal = ZERO
    gross: Decimal = ZERO
    fee: Decimal = ZERO
    entered: Decimal | None = None
    amount: Decimal = ZERO
    withheld: Decimal = ZERO


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _num(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _spec(event: str) -> EventSpec:
    try:
        return EVENTS[event]
    except KeyError:
        raise ValidationError(f"Unknown investment event: {event}.", "event") from None


def _figures(spec: EventSpec, v: EventValues) -> _Figures:
    """Parse and check every number the event needs; the one place their rules live."""
    if spec.units in (Sign.IN, Sign.OUT):
        units = check_places(to_decimal(v.quantity, "quantity"), v.asset.quantity_decimals, "quantity")
        if units <= ZERO:
            raise ValidationError(f"Enter how many {v.asset.unit}s.", "quantity")
        fee = check_places(to_decimal(v.total_fees if str(v.total_fees or "").strip() else "0", "fees"), 2, "fees")
        if fee < ZERO:
            raise ValidationError("Fees cannot be negative.", "fees")
        entered = None
        if v.total is not None:
            entered = check_places(to_decimal(v.total, "total"), 2, "total")
            if entered <= ZERO:
                raise ValidationError("Enter the total amount.", "total")
            if v.fees_included:
                gross = entered - fee if spec.fees == "cost" else entered + fee
            else:
                gross = entered
            unit_price = (gross / units).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            if gross <= ZERO:
                raise ValidationError("Fees must be lower than the total paid.", "fees")
        else:
            unit_price = check_places(to_decimal(v.price, "price"), 6, "price")
            if unit_price <= ZERO:
                raise ValidationError("Enter the price per unit.", "price")
            fee = check_places(to_decimal(v.fees if str(v.fees or "").strip() else "0", "fees"), 2, "fees")
            if fee < ZERO:
                raise ValidationError("Fees cannot be negative.", "fees")
            gross = _money(units * unit_price)
        if spec.fees == "proceeds" and gross - fee <= ZERO:
            raise ValidationError("After fees nothing would be received — check the price and fees.", "fees")
        return _Figures(units=units, unit_price=unit_price, gross=gross, fee=fee, entered=entered)
    value = check_places(to_decimal(v.amount, "amount"), 2, "amount")
    if value <= ZERO:
        raise ValidationError("Enter the dividend you received.", "amount")
    withheld = check_places(to_decimal(v.tax if str(v.tax or "").strip() else "0", "tax"), 2, "tax")
    if withheld < ZERO:
        raise ValidationError("Tax withheld cannot be negative.", "tax")
    if withheld >= value:
        raise ValidationError("Tax withheld must be less than the dividend.", "tax")
    return _Figures(amount=value, withheld=withheld)


def validate(event: str, values: EventValues) -> None:
    """Raise ValidationError when the typed numbers do not make a valid event of this kind."""
    _figures(_spec(event), values)


def lines_for(event: str, values: EventValues) -> list[PostingLine]:
    """The balanced ledger lines for an event: the only builder for the kinds in ``EVENTS``."""
    spec = _spec(event)
    f = _figures(spec, values)
    v = values
    if spec.units == Sign.NONE:  # income: cash in, tax out
        category = v.category_ids[spec.income_category]
        # Asset attribution is stored in investment_dividend_assets; memo remains descriptive only.
        lines = [PostingLine.cash(v.account.id, v.cash_asset_id, f.amount, Effect.INFLOW, category,
                                  memo=v.asset.code, fx_rate=v.holding_rate)]
        if f.withheld:
            lines.append(PostingLine.cash(v.account.id, v.cash_asset_id, -f.withheld, Effect.OUTFLOW,
                                          v.category_ids[TAX_CATEGORY], memo=f"Tax withheld · {v.asset.code}",
                                          fx_rate=v.holding_rate))
        return lines
    word = "Buy" if spec.units == Sign.IN else "Sell"
    fee_sign = "+" if spec.fees == "cost" else "−"
    fee_text = f" {fee_sign} fee {fmt(f.fee)}" if f.fee else ""
    memo = (f"{word} {_num(f.units)} × {v.asset.code} @ {_num(f.unit_price)}"
            + (fee_text if f.entered is None else
               f" · {'cash total' if v.fees_included else 'trade total'} {fmt(f.entered)}"))
    cash_account = v.cash_account or v.account
    if spec.units == Sign.IN:
        cost = f.gross + f.fee
        return [PostingLine.cash(cash_account.id, v.cash_asset_id, -cost, Effect.INTERNAL, memo=memo,
                                 fx_rate=v.cash_rate),
                PostingLine.units(v.account.id, v.asset.id, f.units, cost, Effect.INTERNAL, f.unit_price, memo,
                                  fx_rate=v.holding_rate)]
    proceeds = f.gross - f.fee
    return [PostingLine.units(v.account.id, v.asset.id, -f.units, -proceeds, Effect.INTERNAL, f.unit_price, memo,
                              fx_rate=v.holding_rate),
            PostingLine.cash(cash_account.id, v.cash_asset_id, proceeds, Effect.INTERNAL, memo=memo,
                             fx_rate=v.cash_rate)]
