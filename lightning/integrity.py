"""Read-only reconciliations between ledger detail, ownership subledgers, and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.categories.domain import CategoryFamily
from lightning.core.dates import fmt_date, month_of, parse_date, parse_month, today
from lightning.core.money import ZERO, from_e6
from lightning.reporting.service import ReportingService


@dataclass
class IntegrityCheck:
    name: str
    status: str
    actual: Decimal
    expected: Decimal
    difference: Decimal
    detail: str


class IntegrityService:
    """Cross-check independently derived totals without changing ledger data."""

    def __init__(self, reporting: ReportingService, reserves, budgets, planning=None, position=None):
        self.reporting = reporting
        self.reserves = reserves
        self.budgets = budgets
        self.planning = planning
        self.position = position

    def checks(self, as_of: date | str) -> list[IntegrityCheck]:
        # Each check compares two separate computations. Checks that rebuilt a figure from the very parts they then
        # compared against (gross vs asset classes, classes vs owned net worth, owned + held vs gross, the
        # per-account split) could never fail and were removed (2K).
        day = fmt_date(parse_date(as_of))
        nw = self.reporting.net_worth(day)
        complete = not nw.unvalued
        checks = []
        below_zero = [(account, value) for account, value in nw.by_account
                      if account.account_type in {AccountType.CASH, AccountType.BANK} and value < ZERO]
        checks.append(self._check("No cash account is below zero", sum((-value for _, value in below_zero), ZERO), ZERO,
                                  "Wallets and bank accounts hold money you have."
                                  + "".join(f" {account.label}: {value}." for account, value in below_zero)))

        month = month_of(parse_date(day))
        first, last = parse_month(month)
        # Rebuilt from the ledger lines themselves, not from the per-category totals the screens add up
        # (audit 2026-10-26: comparing those totals with their own sum could never fail).
        checks.append(self._base_cash_check())

        by_category = self.reporting.money_out_by_category(first, last)
        investment = {category.id for category in self.reporting.categories.tree()
                      if category.family == CategoryFamily.INVESTMENT}
        budget = self.budgets.month_view(month)
        checks.append(self._check("Budget actual equals categorized spending", budget.actual,
                                  sum((value for cid, value in by_category.items() if cid not in investment), ZERO),
                                  "Budget actuals should reconcile to posted money-out categories, "
                                  "leaving out investment fees and taxes as the budget does."))

        if self.position is not None:
            checks.append(self._free_cash_check(day))

        bridge = self.reporting.bridge(first, parse_date(day))
        checks.append(self._check("Month-to-date net-worth bridge", bridge.expected_closing, bridge.closing,
                                  "Opening + income − spending + valuation changes + new balances + custody changes.",
                                  complete))
        return checks

    def _base_cash_check(self) -> IntegrityCheck:
        """Profile-currency cash is worth its face value: each such line's base amount equals its quantity."""
        gap = self.reporting.q.db.scalar(
            "SELECT COALESCE(SUM(ABS(le.amount_base_e6 - le.quantity_e6)),0) FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED' "
            "JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=1 AND f.currency=? "
            "WHERE le.effect<>'REVALUATION'", (self.reporting.base_currency,))
        return self._check("Profile-currency cash moves at face value", from_e6(gap or 0), ZERO,
                           "Every cash line in the profile currency is valued at exactly its amount.")

    def _free_cash_check(self, day: str) -> IntegrityCheck:
        """Free cash as every screen shows it (`Position.free_cash`, built from valued holdings) against free cash
        rebuilt from ledger sums: each spendable account's cash quantity less the cash it holds for others."""
        name = "Free cash matches the ledger"
        detail = "Free cash = spendable cash you own − reserves − bills due, rebuilt from each account's ledger lines."
        shown = self.position.at(day, match_payments=False)
        reserves = self.reserves.allocation_at(day)
        if reserves is None and day == fmt_date(today()):
            reserves = sum((row["effective_allocated"] for row in self.reserves.list_active()), ZERO)
        if shown.free_cash is None or reserves is None:
            return self._check(name, ZERO, ZERO, detail, complete=False)
        base, complete, ledger_cash = self.reporting.base_currency, True, ZERO
        for account in self.reporting.accounts.list():
            if (account.account_type not in {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE}
                    or not account.counts_as_spendable(base)):
                continue
            owned = (from_e6(self.reporting.q.account_quantity(account.id, as_of=day))
                     - self.reporting.money_from_others.cash_total_for_account(account.id, day))
            if account.account_type == AccountType.BROKERAGE:
                owned = max(ZERO, owned)
            if account.currency != base and owned:
                owned = self.reporting.valuer.value(self.reporting.assets.cash_asset(account.currency), owned, day).value
                if owned is None:
                    complete, owned = False, ZERO
            ledger_cash += owned
        expected = ledger_cash - reserves - shown.bills_due
        return self._check(name, shown.free_cash, expected, detail, complete)

    @staticmethod
    def _check(name: str, actual: Decimal, expected: Decimal, detail: str,
               complete: bool = True) -> IntegrityCheck:
        difference = actual - expected
        status = "ISSUE" if difference != ZERO else ("INCOMPLETE" if not complete else "PASS")
        if not complete:
            detail += " Some valuations are unavailable; resolve them before treating this as final."
        if difference != ZERO:
            detail += f" Difference: {difference}."
        return IntegrityCheck(name, status, actual, expected, difference, detail)
