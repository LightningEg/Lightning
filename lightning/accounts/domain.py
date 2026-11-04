"""Accounts — WHERE value is held (a wallet, a bank account, a CD, THNDR).

Lightning tracks what you own; it does not track debts (no liabilities — owner decision 2026-09-25).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lightning.core.codes import slug


class AccountType(StrEnum):
    CASH = "CASH"
    CASH_AT_HAND = "CASH_AT_HAND"  # form-only subtype; stored as CASH with cash_at_hand set
    BANK = "BANK"  # current or savings — the same thing here
    DEPOSIT = "DEPOSIT"  # bank-specific portfolio of non-cash certificates
    BROKERAGE = "BROKERAGE"
    PHYSICAL_ASSET = "PHYSICAL_ASSET"  # offered from M3 (holdings of gold etc.)
    OTHER_ASSET = "OTHER_ASSET"
    GAMEYA = "GAMEYA"  # a rotating savings circle: one account per circle; instalments and payout are transfers


TYPE_LABELS: dict[AccountType, str] = {
    AccountType.CASH: "Cash wallet",
    AccountType.CASH_AT_HAND: "Cash",
    AccountType.BANK: "Bank account (current or savings)",
    AccountType.DEPOSIT: "Certificates of deposit (CD portfolio)",
    AccountType.BROKERAGE: "Brokerage (stocks and funds)",
    AccountType.PHYSICAL_ASSET: "Physical asset (gold and things you own)",
    AccountType.OTHER_ASSET: "Other",
    AccountType.GAMEYA: "Gam'eya (savings circle)",
}

# For lists, where the picker's hints would only repeat (review, 2026-10-06).
TYPE_SHORT: dict[AccountType, str] = {
    AccountType.CASH: "Cash",
    AccountType.CASH_AT_HAND: "Cash",
    AccountType.BANK: "Bank account",
    AccountType.DEPOSIT: "Certificates",
    AccountType.BROKERAGE: "Brokerage",
    AccountType.PHYSICAL_ASSET: "Physical asset",
    AccountType.OTHER_ASSET: "Other",
    AccountType.GAMEYA: "Gam'eya",
}

TYPE_ABBR: dict[AccountType, str] = {
    AccountType.CASH: "CSH",
    AccountType.CASH_AT_HAND: "CSH",
    AccountType.BANK: "CUR",
    AccountType.DEPOSIT: "CD",
    AccountType.BROKERAGE: "BRK",
    AccountType.PHYSICAL_ASSET: "PHY",
    AccountType.OTHER_ASSET: "OTH",
    AccountType.GAMEYA: "GAM",
}

# Cash is one asset (CASH:EGP) wherever it sits; the account type decides where it is reported.
DEFAULT_CASH_CLASS: dict[AccountType, str] = {
    AccountType.CASH: "CASH.PHYSICAL",
    AccountType.CASH_AT_HAND: "CASH.PHYSICAL",
    AccountType.BANK: "CASH.BANK",
    AccountType.DEPOSIT: "DEPOSIT.CD",
    AccountType.BROKERAGE: "CASH.BROKERAGE",
    AccountType.PHYSICAL_ASSET: "OTHER",
    AccountType.OTHER_ASSET: "OTHER",
    AccountType.GAMEYA: "GAMEYA",
}

# Types a user can pick today
OFFERED_TYPES = [
    AccountType.CASH,
    AccountType.CASH_AT_HAND,
    AccountType.BANK,
    AccountType.DEPOSIT,
    AccountType.BROKERAGE,
    AccountType.PHYSICAL_ASSET,
    AccountType.OTHER_ASSET,
    AccountType.GAMEYA,
]

# Cash in these accounts counts as spendable by default (in the profile currency only)
SPENDABLE_BY_DEFAULT = {AccountType.CASH, AccountType.BANK}

# Accounts that can hold investments (stocks, funds, gold)
INVESTMENT_ACCOUNT_TYPES = {AccountType.BROKERAGE, AccountType.PHYSICAL_ASSET, AccountType.OTHER_ASSET}

# How the sidebar groups accounts (the dashboard groups wealth by asset class instead)
SIDEBAR_GROUPS: dict[AccountType, str] = {
    AccountType.CASH: "Cash & bank",
    AccountType.CASH_AT_HAND: "Cash & bank",
    AccountType.BANK: "Cash & bank",
    AccountType.DEPOSIT: "Deposits",
    AccountType.BROKERAGE: "Investments",
    AccountType.PHYSICAL_ASSET: "Investments",
    AccountType.OTHER_ASSET: "Other",
    AccountType.GAMEYA: "Gam'eya",
}


@dataclass
class Account:
    id: int
    code: str
    name: str
    institution: str
    account_type: AccountType
    currency: str
    cash_class_id: int  # follows account_type, with the Cash at hand form subtype preserved separately
    opening_date: str  # yyyy-mm-dd
    is_system: bool
    last4: str | None
    active: bool
    sort_order: int
    notes: str
    cash_at_hand: bool = False
    spendable: bool | None = None  # None follows the default (counts_as_spendable)
    parent_id: int | None = None   # set on a broker's currency pocket: the broker account it belongs to
    cost_method: str = "average"  # which purchases a sale takes its cost from: average, or fifo (NF-5B3)

    def counts_as_spendable(self, profile_currency: str) -> bool:
        """Whether this account's own cash counts in Free cash and Safe to spend. By default wallets and bank
        accounts in the profile currency do; brokerage cash and foreign-currency cash are kept apart, because
        spending them needs a transfer or a conversion first (audit 2026-10-15). The person can override it."""
        if self.spendable is not None:
            return self.spendable
        return self.account_type in SPENDABLE_BY_DEFAULT and self.currency == profile_currency

    @property
    def label(self) -> str:
        """Human-facing account label; the internal code is never shown in the UI."""
        return self.name

    @property
    def type_label(self) -> str:
        return TYPE_LABELS[AccountType.CASH_AT_HAND if self.cash_at_hand else self.account_type]

    @property
    def type_short(self) -> str:
        return TYPE_SHORT[AccountType.CASH_AT_HAND if self.cash_at_hand else self.account_type]


def suggest_code(institution: str, name: str, account_type: AccountType, currency: str) -> str:
    """CIB + Bank + EGP -> CIB-CUR-EGP; a wallet with no institution -> WALLET-CSH-EGP."""
    head = slug(institution, 12) or slug(name, 12) or account_type.value.split("_")[0]
    return f"{head}-{TYPE_ABBR[account_type]}-{currency}"
