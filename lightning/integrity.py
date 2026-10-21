"""Read-only reconciliations between ledger detail, ownership subledgers, and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, month_of, parse_date, parse_month
from lightning.core.money import ZERO
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

    def __init__(self, reporting: ReportingService, reserves, budgets, planning=None):
        self.reporting = reporting
        self.reserves = reserves
        self.budgets = budgets
        self.planning = planning

    def checks(self, as_of: date | str) -> list[IntegrityCheck]:
        day = fmt_date(parse_date(as_of))
        nw = self.reporting.net_worth(day)
        gross = sum((value for _, value in nw.by_account), ZERO)
        held = self.reporting.money_from_others_total(day)
        account_split = sum((value for _, value in nw.by_account), ZERO)
        owned_and_held = nw.total + held
        complete = not nw.unvalued
        checks = [
            self._check("Account balances equal asset classes",
                        gross, sum((group.value for group in nw.by_class if group.code != "CUSTODY"), ZERO),
                        "Gross account values should equal the asset-class breakdown."),
            self._check("What I own plus money held for others equals account balances",
                        account_split, owned_and_held,
                        "Account balances = what you own + money you hold for others.", complete),
            self._check("Asset-class report adds to owned net worth",
                        sum((group.value for group in nw.by_class), ZERO), nw.total,
                        "Money held for others is taken out of what you own.", complete),
        ]

        custody_by_account = self.reporting.custody_value_by_account(day)
        account_differences = []
        account_failure_labels = []
        for account, gross_value in nw.by_account:
            owned_value = self.reporting.owned_account_value(account.id, day)
            held_value = custody_by_account.get(account.id, ZERO)
            difference = gross_value - owned_value - held_value
            account_differences.append(abs(difference))
            if difference != ZERO:
                account_failure_labels.append(f"{account.label}: {difference}")
        account_difference = sum(account_differences, ZERO)
        checks.append(self._check("Ownership split by account", account_difference, ZERO,
                                  "For each account: gross value = owned value + money held for others. "
                                  + ("; ".join(account_failure_labels) if account_failure_labels else ""), complete))

        below_zero = [(account, value) for account, value in nw.by_account
                      if account.account_type in {AccountType.CASH, AccountType.BANK} and value < ZERO]
        checks.append(self._check("No cash account is below zero", sum((-value for _, value in below_zero), ZERO), ZERO,
                                  "Wallets and bank accounts hold money you have."
                                  + "".join(f" {account.label}: {value}." for account, value in below_zero)))

        month = month_of(parse_date(day))
        first, last = parse_month(month)
        flow = self.reporting.cash_flow(first, last)
        categorized_outflows = sum(self.reporting.money_out_by_category(first, last).values(), ZERO)
        checks.append(self._check("Categorized expenses equal reported spending", categorized_outflows,
                                  flow.outflows,
                                  "Refunds reduce their original category; transfers are excluded."))

        budget = self.budgets.month_view(month)
        checks.append(self._check("Budget actual equals categorized spending", budget.actual,
                                  categorized_outflows,
                                  "Budget actuals should reconcile to posted money-out categories."))

        cash = self.reporting.owned_spendable_cash(day)
        bills_due = self.planning.what_you_owe(parse_date(day)).bills_due if self.planning else ZERO
        reserve = self.reserves.cash_summary(cash, bills_due)
        checks.append(self._check("Free cash plus reserves and bills due equals spendable cash",
                                  reserve["free_cash"] + reserve["allocated"] + reserve["bills_due"], cash,
                                  "Budget limits are intentionally excluded; reserves assign real cash and bills due are owed now."))

        bridge = self.reporting.bridge(first, parse_date(day))
        checks.append(self._check("Month-to-date net-worth bridge", bridge.expected_closing, bridge.closing,
                                  "Opening + income − spending + valuation changes + new balances + custody changes.",
                                  complete))
        return checks

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
