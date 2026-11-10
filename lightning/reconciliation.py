"""Check an account against the balance the bank shows, and settle a small difference.

The user types the ending balance from the bank (or wallet app) on a date. Lightning compares it with the
account's own cash balance on that date. A small difference is settled with one balance adjustment, posted as
ordinary Money out (Other Personal) or Money in (Other Income), so it counts in spending and income like any
other row. A big difference on a bank account is never adjusted (a cash wallet has no statement, so any size is): the user reviews the register or reimports the statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from lightning.core.dates import now_iso, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, from_e6, to_decimal, to_e6
from lightning.database.connection import Database

SMALL_SHARE = Decimal("0.01")   # a difference up to 1% of the bank balance is small...
SMALL_FLOOR = Decimal("100")    # ...or up to 100 in the account's currency, whichever is larger
ADJUSTMENT = "Balance adjustment"
SHORTFALL_CATEGORY = "EXP.PERSONAL.OTHER"          # Other Personal
UNACCOUNTED_SPENT = "EXP.UNACCOUNTED"               # Unaccounted Spending (cash and wallets)
UNACCOUNTED_FOUND = "INC.UNACCOUNTED"               # Unaccounted Money Found
EXCESS_CATEGORY = "EXP.PERSONAL.OTHER_INCOME"      # Other Income


@dataclass(frozen=True)
class BalanceCheck:
    through: str
    bank_balance: Decimal
    lightning_balance: Decimal
    difference: Decimal          # bank − Lightning: positive means the bank has more
    limit: Decimal               # the largest difference that is still small
    cash: bool = False           # a cash or wallet account has no statement: any difference can be adjusted (IV-12V)

    @property
    def matches(self) -> bool:
        return self.difference == ZERO

    @property
    def small(self) -> bool:
        return not self.matches and (self.cash or abs(self.difference) <= self.limit)


class ReconciliationService:
    def __init__(self, db: Database, categories=None, transactions=None):
        self.db, self.categories, self.transactions = db, categories, transactions

    def checked_through(self, account_id: int):
        return self.db.scalar("SELECT date FROM reconciled_through WHERE account_id=?", (account_id,))

    def close(self, account_id: int, through: str, bank_balance):
        day = parse_date(through)
        if day > today():
            raise ValidationError("Choose a date on or before today.", "date")
        self.transactions.accounts.get(account_id)
        with self.db.transaction(undo_label="Check account history"):
            result = self.check(account_id, day.isoformat(), to_decimal(bank_balance, "balance"))
            if not result.matches:
                raise ValidationError("The balance changed. Check it against the bank again before closing.")
            prior = self.checked_through(account_id)
            if prior and prior >= day.isoformat():
                raise ValidationError("This account is already checked through that date.")
            self.db.execute("UPDATE ledger_entries SET cleared=1 WHERE account_id=? AND date<=? AND cleared=0 "
                            "AND transaction_id IN (SELECT id FROM transactions WHERE status='POSTED')",
                            (account_id, day.isoformat()))
            self.db.execute("INSERT INTO reconciled_through(account_id,date,bank_balance_e6,checked_at) VALUES(?,?,?,?) "
                            "ON CONFLICT(account_id) DO UPDATE SET date=excluded.date,bank_balance_e6=excluded.bank_balance_e6,checked_at=excluded.checked_at",
                            (account_id, day.isoformat(), to_e6(result.bank_balance), now_iso()))
            return result

    def unlock(self, account_id: int):
        with self.db.transaction(undo_label="Unlock account history"):
            self.db.execute("DELETE FROM reconciled_through WHERE account_id=?", (account_id,))

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
        cash = self.db.scalar("SELECT account_type FROM accounts WHERE id=?", (account_id,)) == "CASH"
        return BalanceCheck(through, bank_balance, mine, bank_balance - mine, limit, cash)

    def adjust(self, account_id: int, through: str, bank_balance: Decimal):
        """Post the small difference so the account matches the bank on ``through``."""
        result = self.check(account_id, through, bank_balance)
        if result.matches:
            raise ValidationError("The account already matches your bank; there is nothing to adjust.", "balance")
        if not result.small:
            raise ValidationError("The difference is too big to adjust. Review the register, or delete and "
                                  "reimport the statement.", "balance")
        notes = f"Bank showed {bank_balance:,.2f} on {through}"
        if result.cash:  # money that cannot be traced is filed as such, outside the budget (IV-12V)
            category = self.categories.get_by_code(UNACCOUNTED_FOUND if result.difference > ZERO else UNACCOUNTED_SPENT)
            if result.difference > ZERO:
                return self.transactions.record_inflow(through, account_id, result.difference, category.id,
                                                       counterparty=ADJUSTMENT, notes=notes, allow_system_category=True)
            return self.transactions.record_outflow(through, account_id, -result.difference, category.id,
                                                    counterparty=ADJUSTMENT, notes=notes, allow_system_category=True)
        if result.difference > ZERO:
            category = self.categories.get_by_code(EXCESS_CATEGORY)
            return self.transactions.record_inflow(through, account_id, result.difference, category.id,
                                                   counterparty=ADJUSTMENT, notes=notes)
        category = self.categories.get_by_code(SHORTFALL_CATEGORY)
        return self.transactions.record_outflow(through, account_id, -result.difference, category.id,
                                                counterparty=ADJUSTMENT, notes=notes)

    @staticmethod
    def parse_bank_balance(value: str) -> Decimal:
        if not str(value or "").strip():
            raise ValidationError("Enter the balance your bank shows.", "balance")
        return to_decimal(value, "balance")

    @staticmethod
    def validate_date(value: str) -> str:
        return parse_date(value).isoformat()   # 2026-10-31, 31/10/2026 or 31/10, like every date box
