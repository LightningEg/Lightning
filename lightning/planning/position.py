"""Your position on a date: one calculation for every figure the reporting tabs show.

Base figures are read from the ledger once; every other figure is a formula of them, so a tab
never re-adds balances its own way. The names match ai/GLOSSARY.md and the UI figure registry.

    In your accounts            = What you own + Held for others
    What you own                = Cash you own + Holdings value + Other you own
    Holdings value              = everything that is not cash, Deposits and Gam'eya paid in included
    Cash you own                = Bank and wallet cash + Brokerage cash
    What you owe                = Bills due (other than loan payments) + Loans still to pay + Gam'eya still to pay
    Net worth                   = What you own − What you owe
    Kept apart                  = Cash you own in brokerages, other currencies or accounts set apart
    Free cash                   = Cash you own − Kept apart − Reserves − Bills due
    Portfolio value             = Holdings value + Brokerage cash
    Investments after sale      = Σ (Deposits and Holdings value by class × sale factor)
    If you sold today           = Free cash + Kept apart + Investments after sale

A gam'eya (savings circle) is one GAMEYA account per circle: its positive balance is Gam'eya paid in (a class of
Holdings value, sale factor 100%, not liquid so never in Cash you own or Free cash); its negative balance, the pot
taken early, is Gam'eya still to pay, in What you owe and out of What you own. An instalment or a payout moves cash
between your accounts, so Net worth never changes with either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import NotFoundError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO

from lightning.investments.domain import DEFAULT_SALE_FACTOR

from .domain import WhatYouOwe

GAMEYA_CLASS = "GAMEYA"


@dataclass
class OwnedHolding:
    account_id: int
    account: str
    asset_id: int
    asset: str
    class_code: str
    quantity: Decimal
    value: Decimal | None
    unit: str

    @property
    def locked_until(self) -> str | None:
        return getattr(self, "_locked_until", None)

    def __getitem__(self, key):  # templates and older callers read rows as mappings
        return getattr(self, key)


@dataclass
class ClassValue:
    """Owned value of one asset class, and what it would fetch if sold."""
    id: int
    code: str
    name: str
    value: Decimal
    factor: Decimal
    items: list[OwnedHolding] = field(default_factory=list)

    @property
    def is_deposit(self) -> bool:
        return self.code.split(".")[0] == "DEPOSIT"

    @property
    def after_sale(self) -> Decimal:
        if self.items and any(hasattr(item, "_realization_factor") for item in self.items):
            return sum(((item.value or ZERO)
                        * getattr(item, "_realization_factor", self.factor) / 100
                        for item in self.items), ZERO)
        return self.value * self.factor / 100

    @property
    def locked_until(self) -> str | None:
        """When every item is locked (a certificate in its lock-up), the last day it stays locked."""
        days = [getattr(item, "_locked_until", None) for item in self.items]
        return max(days) if days and all(days) else None

    def __getitem__(self, key):
        return getattr(self, key)


@dataclass(frozen=True)
class Position:
    as_of: str
    what_you_own: Decimal
    held_for_others: Decimal
    unvalued: tuple[str, ...]
    bank_and_wallet_cash: Decimal
    brokerage_cash: Decimal
    classes: tuple[ClassValue, ...]
    reserves: Decimal | None            # None when reserve history cannot be rebuilt for the date
    reserve_rows: tuple[dict, ...] | None
    owe: WhatYouOwe
    gameya_owed: Decimal = ZERO         # Gam'eya still to pay: circles with a negative balance
    kept_apart: Decimal = ZERO          # owned cash that is not spendable (brokerage, foreign, set apart)

    # ------------------------------------------------------------ base parts
    @property
    def deposits(self) -> Decimal:
        return sum((c.value for c in self.classes if c.is_deposit), ZERO)

    @property
    def holdings_value(self) -> Decimal:
        # Owner decision 2026-10-04: everything that is not cash sits under one roof, deposits included.
        return sum((c.value for c in self.classes), ZERO)

    @property
    def gameya_paid_in(self) -> Decimal:
        return sum((c.value for c in self.classes if c.code == GAMEYA_CLASS), ZERO)

    @property
    def gameya_still_to_pay(self) -> Decimal:
        return self.gameya_owed

    @property
    def bills_due(self) -> Decimal:
        return self.owe.bills_due

    @property
    def loans_still_to_pay(self) -> Decimal:
        return self.owe.loans_still_to_pay

    # ------------------------------------------------------------- formulas
    @property
    def in_your_accounts(self) -> Decimal:
        return self.what_you_own + self.held_for_others

    @property
    def cash_you_own(self) -> Decimal:
        return self.bank_and_wallet_cash + self.brokerage_cash

    @property
    def other_you_own(self) -> Decimal:
        return self.what_you_own - self.cash_you_own - self.holdings_value

    @property
    def what_you_owe(self) -> Decimal:
        return self.owe.total + self.gameya_owed

    @property
    def net_worth(self) -> Decimal:
        return self.what_you_own - self.what_you_owe

    @property
    def free_cash(self) -> Decimal | None:
        return None if self.reserves is None else self.spendable_cash - self.reserves - self.bills_due

    @property
    def spendable_cash(self) -> Decimal:
        return self.cash_you_own - self.kept_apart

    @property
    def portfolio_value(self) -> Decimal:
        # Owner decision 2026-10-04: brokerage cash is cash you own, never part of the portfolio.
        return self.holdings_value

    @property
    def holdings_after_sale(self) -> Decimal:
        return sum((c.after_sale for c in self.classes), ZERO)

    @property
    def locked_holdings(self) -> tuple[OwnedHolding, ...]:
        """Owned certificate values excluded from cash available by selling today."""
        return tuple(item for cls in self.classes for item in cls.items if item.locked_until)

    @property
    def deposits_after_sale(self) -> Decimal:
        return sum((c.after_sale for c in self.classes if c.is_deposit), ZERO)

    @property
    def if_you_sold_today(self) -> Decimal | None:
        if self.free_cash is None or self.unvalued:
            return None
        return self.free_cash + self.kept_apart + self.holdings_after_sale

    @property
    def unavailable_reason(self) -> str:
        if self.unvalued:
            return "A required valuation is missing for this date."
        if self.reserves is None:
            return "Reserve history is incomplete for this date."
        return ""


class PositionService:
    def __init__(self, reporting, assets, investments, money_from_others, reserves, planning, deposits=None):
        self.reporting = reporting
        self.assets = assets
        self.investments = investments
        self.money_from_others = money_from_others
        self.reserves = reserves
        self.planning = planning
        self.deposits = deposits

    def owned_holdings(self, as_of: date | str) -> tuple[list[OwnedHolding], list[str]]:
        """Owned units and value per holding (not cash), after money held for others."""
        day = fmt_date(as_of) if isinstance(as_of, date) else str(as_of)
        rows, unvalued = self.reporting.holdings(day)
        custody = {(r["account_id"], r["asset_id"]): r["units"]
                   for r in self.money_from_others.investment_positions(day)}
        result = []
        for row in rows:
            asset = self.assets.get_asset(row.asset_id)
            if asset.is_cash and row.asset_class_code.split(".")[0] == "CASH":
                continue
            held = custody.get((row.account.id, row.asset_id), ZERO)
            if asset.is_cash:
                held = self.money_from_others.cash_total_for_account(row.account.id, day)
            quantity = max(ZERO, row.quantity - held)
            # Part of the holding is someone else's: value only your own units. (This used to value your
            # units and then subtract them from the whole holding, leaving the other owner's share as yours.)
            if held:
                valuation = self.reporting.value_of(row.asset_id, quantity, day)
                value = valuation.value if valuation else None
            else:
                value = row.value
            if row.asset_class_code == GAMEYA_CLASS and (value or ZERO) < ZERO:
                continue  # the pot taken early is Gam'eya still to pay (What you owe), not a negative holding
            result.append(OwnedHolding(row.account.id, row.account.label, row.asset_id, asset.name,
                                       row.asset_class_code, quantity, value, asset.unit))
        return result, unvalued

    def foreign_holdings(self, as_of: date | str, base_currency: str) -> dict[str, tuple[Decimal, bool]]:
        """Owned holdings priced in another currency, by currency: (value in the profile currency, any unpriced)."""
        holdings, _ = self.owned_holdings(as_of)
        out: dict[str, tuple[Decimal, bool]] = {}
        for h in holdings:
            currency = self.assets.get_asset(h.asset_id).currency
            if currency == base_currency or not h.quantity:
                continue
            value, unpriced = out.get(currency, (ZERO, False))
            out[currency] = (value + (h.value or ZERO), unpriced or h.value is None)
        return out

    def portfolio_value_at(self, as_of: date | str) -> Decimal:
        """Portfolio value on a date, as Position.portfolio_value gives it, without the plan reads a whole
        Position needs (for a trend of month ends)."""
        classes, _ = self.class_values(fmt_date(parse_date(as_of)))
        return sum((c.value for c in classes), ZERO)

    @request_cached
    def class_values(self, as_of: date | str) -> tuple[list[ClassValue], list[str]]:
        holdings, unvalued = self.owned_holdings(as_of)
        factors = self.investments.liquidation_factors()
        if self.deposits is not None:
            day = parse_date(as_of)
            for item in holdings:
                if item.class_code != "DEPOSIT.CD":
                    continue
                try:
                    certificate = self.deposits.certificate_for_asset(item.asset_id)
                except NotFoundError:
                    continue
                if certificate is None:
                    try:
                        terms = self.deposits.get(item.account_id)
                    except NotFoundError:
                        continue  # Legacy deposit account: retain its class factor.
                else:
                    terms = certificate.terms
                if day < parse_date(terms.lockup_end_date):
                    item._realization_factor = ZERO
                    item._locked_until = terms.lockup_end_date
                elif day >= parse_date(terms.maturity_date):
                    item._realization_factor = Decimal(100)
        for item in holdings:
            if item.class_code == GAMEYA_CLASS:
                item._realization_factor = Decimal(100)  # a circle cannot be sold early: paid in is paid in
        by_code = {cls.code: cls for cls in self.assets.list_classes()}
        rows: dict[int, ClassValue] = {}
        for item in holdings:
            cls = by_code.get(item.class_code)
            if cls is None:
                continue
            row = rows.setdefault(cls.id, ClassValue(cls.id, cls.code, cls.name, ZERO,
                                                     factors.get(cls.id, DEFAULT_SALE_FACTOR)))
            row.value += item.value or ZERO
            row.items.append(item)
        for cls in self.assets.investment_classes():
            rows.setdefault(cls.id, ClassValue(cls.id, cls.code, cls.name, ZERO,
                                               factors.get(cls.id, DEFAULT_SALE_FACTOR)))
        return sorted(rows.values(), key=lambda r: (-r.value, r.name.casefold())), unvalued

    def reserve_rows(self, as_of: date | str) -> list[dict] | None:
        """Effective reserve assignments on the date; today's are always known."""
        day = fmt_date(as_of) if isinstance(as_of, date) else str(as_of)
        rows = self.reserves.breakdown_at(day)
        if rows is None and day == fmt_date(today()):
            rows = [{"id": r["id"], "name": r["name"], "kind": r["kind"],
                     "effective_allocated": r["effective_allocated"]} for r in self.reserves.list_active()]
        return rows

    def change_in_what_you_own(self, start: date | str, end: date | str,
                               since_first_record: bool = False) -> tuple[Decimal | None, str]:
        """Change in what you own = What you own at the end − What you own the day before the start
        − opening balances recorded in the period (recording what you already had is not a change).

        Returns (change, reason); change is None, with the reason, when a valuation is missing."""
        start_day, end_day = parse_date(start), parse_date(end)
        closing = self.reporting.net_worth(fmt_date(end_day))
        if closing.unvalued:
            return None, "A required valuation is missing from the ending position."
        if since_first_record and not self.reporting.first_activity_date():
            return None, "No recorded position is available for comparison."
        opening = self.reporting.net_worth(fmt_date(start_day - timedelta(days=1)))
        if opening.unvalued:
            return None, ("The first recorded position is missing a required valuation." if since_first_record
                          else "The position immediately before this period is missing a required valuation.")
        # Opening balances recorded inside the period were already yours: not a change.
        return (closing.what_you_own - opening.what_you_own
                - self.reporting.opening_balances_between(start_day, end_day)), ""

    def change_in_net_worth(self, start: date | str, end: date | str,
                            since_first_record: bool = False) -> tuple[Decimal | None, str]:
        """Change in net worth = Net worth at the end − Net worth the day before the start.

        Returns (change, reason) like change_in_what_you_own: None, with the reason, when a
        valuation is missing at either end."""
        start_day, end_day = parse_date(start), parse_date(end)
        closing = self.at(end_day)
        if closing.unvalued:
            return None, "A required valuation is missing from the ending position."
        if since_first_record and not self.reporting.first_activity_date():
            return None, "No recorded position is available for comparison."
        opening = self.at(start_day - timedelta(days=1))
        if opening.unvalued:
            return None, ("The first recorded position is missing a required valuation." if since_first_record
                          else "The position immediately before this period is missing a required valuation.")
        return closing.net_worth - opening.net_worth - self.reporting.opening_balances_between(start_day, end_day), ""

    def at(self, as_of: date | str | None = None, *, match_payments: bool = True) -> Position:
        """Read a position; read-only profiles can skip today's automatic payment matching."""
        return self._at(fmt_date(parse_date(as_of) if as_of is not None else today()), match_payments)

    @request_cached
    def _at(self, text: str, match_payments: bool = True) -> Position:
        day = parse_date(text)
        if match_payments and day == today():
            # Settle bills that a posted transaction already paid before counting what is due.
            self.planning.match_payments(day)
        wealth = self.reporting.net_worth(text)
        classes, unvalued = self.class_values(text)
        brokerage = self.reporting.owned_brokerage_cash(text)
        rows = self.reserve_rows(text)
        return Position(
            as_of=text, what_you_own=wealth.what_you_own,
            held_for_others=self.reporting.money_from_others_total(text),
            unvalued=tuple(dict.fromkeys(wealth.unvalued + unvalued)),
            bank_and_wallet_cash=self.reporting.owned_liquid_cash(text) - brokerage,
            brokerage_cash=brokerage, classes=tuple(classes),
            reserves=None if rows is None else sum((r["effective_allocated"] for r in rows), ZERO),
            reserve_rows=None if rows is None else tuple(rows),
            owe=self.planning.what_you_owe(day), gameya_owed=wealth.gameya_owed,
            kept_apart=self.reporting.owned_cash_kept_apart(text))
