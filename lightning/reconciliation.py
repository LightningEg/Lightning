"""Check an account against the balance the bank shows, and settle a small difference.

The user types the ending balance from the bank (or wallet app) on a date. Lightning compares it with the
account's own cash balance on that date. A small difference is settled with one balance adjustment, posted as
ordinary Money out (Other Personal) or Money in (Other Income), so it counts in spending and income like any
other row. A confirmed match (or a settled difference) locks the account through that date. A big difference is never adjusted: the user reviews the register or reimports the statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from lightning.core.dates import parse_date
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, from_e6, to_decimal
from lightning.database.connection import Database

SMALL_SHARE = Decimal("0.01")   # a difference up to 1% of the bank balance is small...
SMALL_FLOOR = Decimal("100")    # ...or up to 100 in the account's currency, whichever is larger
ADJUSTMENT = "Balance adjustment"
SHORTFALL_CATEGORY = "EXP.PERSONAL.OTHER"          # Other Personal
EXCESS_CATEGORY = "EXP.PERSONAL.OTHER_INCOME"      # Other Income


@dataclass(frozen=True)
class BalanceCheck:
    through: str
    bank_balance: Decimal
    lightning_balance: Decimal
    difference: Decimal          # bank − Lightning: positive means the bank has more
    limit: Decimal               # the largest difference that is still small

    @property
    def matches(self) -> bool:
        return self.difference == ZERO

    @property
    def small(self) -> bool:
        return not self.matches and abs(self.difference) <= self.limit


class ReconciliationService:
    def __init__(self, db: Database, categories=None, transactions=None):
        self.db, self.categories, self.transactions = db, categories, transactions

    def balance(self, account_id: int, through: str) -> Decimal:
        """The account's cash on ``through``, every owner included: what the bank shows."""
        total = self.db.scalar(
            "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id "
            "WHERE le.account_id=? AND le.date<=? AND t.status='POSTED' "
            "AND le.asset_id IN (SELECT id FROM financial_assets WHERE is_cash=1)",
            (account_id, through))
        return from_e6(total or 0)

    def check(self, account_id: int, through: str, bank_balance: Decimal) -> BalanceCheck:
        mine = self.balance(account_id, through)
        limit = max(SMALL_FLOOR, (abs(bank_balance) * SMALL_SHARE).quantize(Decimal("0.01")))
        return BalanceCheck(through, bank_balance, mine, bank_balance - mine, limit)

    def locked_through(self, account_id: int) -> str:
        """The date this account was last confirmed against the bank ("" when never). Nothing on or before it can change."""
        return self.db.scalar("SELECT date FROM reconciled_through WHERE account_id=?", (account_id,)) or ""

    def lock(self, account_id: int, through: str) -> str:
        """Remember the account is checked through ``through``. The lock only moves forward; unlock clears it."""
        through = self.validate_date(through)
        if through > self.locked_through(account_id):
            with self.db.transaction():
                self.db.execute(
                    "INSERT INTO reconciled_through(account_id, date) VALUES(?, ?) "
                    "ON CONFLICT(account_id) DO UPDATE SET date=excluded.date", (account_id, through))
        return self.locked_through(account_id)

    def confirm(self, account_id: int, through: str, bank_balance: Decimal) -> str:
        """The user confirms the account matches the bank on ``through``: lock it through that day."""
        if not self.check(account_id, through, bank_balance).matches:
            raise ValidationError("The account does not match your bank on that date yet.", "balance")
        return self.lock(account_id, through)

    def unlock(self, account_id: int) -> None:
        with self.db.transaction():
            self.db.execute("DELETE FROM reconciled_through WHERE account_id=?", (account_id,))

    def adjust(self, account_id: int, through: str, bank_balance: Decimal):
        """Post the small difference so the account matches the bank on ``through``."""
        result = self.check(account_id, through, bank_balance)
        if result.matches:
            raise ValidationError("The account already matches your bank; there is nothing to adjust.", "balance")
        if not result.small:
            raise ValidationError("The difference is too big to adjust. Review the register, or delete and "
                                  "reimport the statement.", "balance")
        notes = f"Bank showed {bank_balance:,.2f} on {through}"
        if result.difference > ZERO:
            category = self.categories.get_by_code(EXCESS_CATEGORY)
            txn = self.transactions.record_inflow(through, account_id, result.difference, category.id,
                                                  counterparty=ADJUSTMENT, notes=notes)
        else:
            category = self.categories.get_by_code(SHORTFALL_CATEGORY)
            txn = self.transactions.record_outflow(through, account_id, -result.difference, category.id,
                                                   counterparty=ADJUSTMENT, notes=notes)
        self.lock(account_id, through)   # the adjustment settles the difference: a confirmed match
        return txn

    @staticmethod
    def parse_bank_balance(value: str) -> Decimal:
        if not str(value or "").strip():
            raise ValidationError("Enter the balance your bank shows.", "balance")
        return to_decimal(value, "balance")

    @staticmethod
    def validate_date(value: str) -> str:
        return parse_date(value).isoformat()   # 2026-10-31, 31/10/2026 or 31/10, like every date box
