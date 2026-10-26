"""Account workflows — actions that span modules, each in ONE database transaction.

- Opening an account also records its opening balance (as an OPN transaction).
- An account can only be deactivated once its balance is zero (no hidden money).
"""

from __future__ import annotations

from decimal import Decimal

from lightning.accounts.domain import Account, INVESTMENT_ACCOUNT_TYPES
from lightning.accounts.service import AccountService
from lightning.core.errors import ConflictError, ValidationError
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.money import ZERO, fmt, to_decimal
from lightning.database.connection import Database
from lightning.reporting.service import ReportingService
from lightning.transactions.service import TransactionService


class AccountWorkflows:
    def __init__(self, db: Database, accounts: AccountService, transactions: TransactionService,
                 reporting: ReportingService):
        self.db = db
        self.accounts = accounts
        self.transactions = transactions
        self.reporting = reporting

    @staticmethod
    def parse_opening(entered: object) -> Decimal:
        """What the person typed ('' means 0). Balances you own cannot start below zero."""
        value = to_decimal(entered if str(entered or "").strip() else "0", "opening_balance")
        if value < ZERO:
            raise ValidationError("An opening balance cannot be negative.", "opening_balance")
        return value

    def opening_of(self, account: Account) -> Decimal:
        return self.transactions.opening_balance(account.id)

    def open_account(self, name: str, account_type: str, opening_date: str, opening_balance: object = "0",
                     institution: str = "", currency: str | None = None, code: str | None = None,
                     last4: str | None = None, notes: str = "",
                     opening_balance_date: str | None = None, owner_id: int | None = None) -> Account:
        with self.db.transaction():
            amount = self.parse_opening(opening_balance)
            if account_type == "DEPOSIT" and amount != ZERO:
                raise ValidationError("A CD portfolio cannot hold cash. Buy CDs from a bank or cash account.",
                                      "opening_balance")
            if account_type == "GAMEYA" and amount != ZERO:
                raise ValidationError("A gam'eya starts empty. Record each instalment you have already paid.",
                                      "opening_balance")
            balance_day = parse_date(opening_balance_date or opening_date, "opening_balance_date")
            if balance_day > today():
                raise ValidationError("The starting balance date cannot be in the future.", "opening_balance_date")
            account = self.accounts.create(name=name, account_type=account_type, opening_date=opening_date,
                                           institution=institution, currency=currency, code=code,
                                           last4=last4, notes=notes)
            self.transactions.set_opening_balance(account.id, amount, fmt_date(balance_day), owner_id)
        return account

    def update_account(self, account_id: int, name: str, account_type: str, opening_date: str,
                       opening_balance: object = "0", institution: str = "", code: str | None = None,
                       last4: str | None = None, notes: str = "", opening_balance_date: str | None = None,
                       owner_id: int | None = None) -> Account:
        balance_day = fmt_date(parse_date(opening_balance_date or opening_date, "opening_balance_date"))
        if parse_date(balance_day) > today():
            raise ValidationError("The starting balance date cannot be in the future.", "opening_balance_date")
        current = self.accounts.get(account_id)
        if account_type == "DEPOSIT" and current.account_type.value != "DEPOSIT":
            if self.reporting.account_value(account_id, "9999-12-31") != ZERO:
                raise ConflictError("Move this account's cash out before turning it into a CD portfolio.",
                                    "account_type")
            if [h for h in self.reporting.holdings("9999-12-31")[0] if h.account.id == account_id]:
                raise ConflictError("Move this account's holdings before turning it into a CD portfolio.",
                                    "account_type")
        if account_type == "GAMEYA" and current.account_type.value != "GAMEYA":
            if self.reporting.account_value(account_id, "9999-12-31") != ZERO or [
                    h for h in self.reporting.holdings("9999-12-31")[0] if h.account.id == account_id]:
                raise ConflictError("Move this account's cash and holdings out before turning it into a gam'eya.",
                                    "account_type")
        if current.account_type.value == "GAMEYA" and account_type != "GAMEYA":
            raise ConflictError("A gam'eya cannot change type. Deactivate it once it is finished.", "account_type")
        if (current.account_type.value == "GAMEYA" and account_type == "GAMEYA"
                and self.parse_opening(opening_balance) != self.opening_of(current)):
            raise ValidationError("A gam'eya starts empty. Record each instalment you have already paid.",
                                  "opening_balance")
        if (current.account_type.value == "DEPOSIT" and account_type == "DEPOSIT"
                and self.parse_opening(opening_balance) != self.opening_of(current)):
            raise ValidationError("A CD portfolio cannot have a cash opening balance.", "opening_balance")
        if current.account_type.value == "DEPOSIT" and account_type != "DEPOSIT":
            if self.reporting.account_value(account_id, "9999-12-31") != ZERO:
                raise ConflictError("Move its legacy cash and redeem its CDs before changing this portfolio's type.",
                                    "account_type")
            if [h for h in self.reporting.holdings("9999-12-31")[0] if h.account.id == account_id]:
                raise ConflictError("Redeem the CDs before changing this portfolio's type.", "account_type")
        if current.account_type in INVESTMENT_ACCOUNT_TYPES and account_type not in {t.value for t in INVESTMENT_ACCOUNT_TYPES}:
            holdings = [h for h in self.reporting.holdings("9999-12-31")[0] if h.account.id == account_id]
            if holdings:
                raise ConflictError(
                    "This account still holds investments. Sell or move them before changing its type.",
                    "account_type",
                )
        with self.db.transaction():
            account, _ = self.accounts.update(account_id, name=name, institution=institution,
                                                    account_type=account_type, opening_date=opening_date,
                                                    code=code, last4=last4, notes=notes)
            self.transactions.set_opening_balance(account.id, self.parse_opening(opening_balance),
                                                  balance_day, owner_id)
        return account

    def deactivate(self, account_id: int) -> Account:
        account = self.accounts.get(account_id)
        balance = self.reporting.account_balance(account_id, "9999-12-31")
        if balance != ZERO:
            raise ConflictError(
                f"{account.label} still holds {fmt(balance)} {account.currency}. "
                "Move the balance to another account first, then deactivate it."
            )
        held = [h for h in self.reporting.holdings("9999-12-31")[0] if h.account.id == account_id]
        if held:
            raise ConflictError(f"{account.label} still holds investments ({', '.join(h.asset_code for h in held)}). "
                                "Sell or move them first, then deactivate it.")
        user = self._still_used_by(account_id)
        if user:
            raise ConflictError(f"{account.label} is still where {user} pays or is paid from. "
                                "Choose another account there first, then deactivate it.")
        return self.accounts.set_active(account_id, False)

    def _still_used_by(self, account_id: int) -> str | None:
        """A live certificate, circle, reserve or plan that would keep sending money to an inactive account
        (audit 2026-10-26)."""
        found = self.db.one(
            "SELECT 'the certificate ' || c.name AS name FROM cd_certificates c "
            "JOIN transactions p ON p.id=c.purchase_transaction_id AND p.status='POSTED' "
            "WHERE c.destination_account_id=:a AND NOT EXISTS (SELECT 1 FROM cd_redemptions r "
            "JOIN transactions t ON t.id=r.transaction_id WHERE r.certificate_id=c.id AND t.status='POSTED') "
            "UNION ALL SELECT 'the circle ' || g.name FROM gameya_terms t JOIN accounts g ON g.id=t.account_id "
            "WHERE g.active=1 AND :a IN (t.funding_account_id, t.payout_account_id) "
            "UNION ALL SELECT 'the reserve ' || name FROM cash_reserves WHERE status='ACTIVE' AND account_id=:a "
            "UNION ALL SELECT 'the plan ' || name FROM planned_items WHERE active=1 AND account_id=:a LIMIT 1",
            {"a": account_id})
        return found["name"] if found else None

    def reactivate(self, account_id: int) -> Account:
        return self.accounts.set_active(account_id, True)
