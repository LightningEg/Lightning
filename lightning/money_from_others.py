"""Custody balances: other people's funds held in the user's accounts."""

from __future__ import annotations

from decimal import Decimal

from lightning.accounts.service import AccountService
from lightning.core.dates import parse_date
from lightning.core.errors import ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, check_places, from_e6, to_decimal, to_e6
from lightning.counterparties import CounterpartyService
from lightning.database.connection import Database


class MoneyFromOthersService:
    def __init__(self, db: Database, accounts: AccountService, transactions=None,
                 counterparties: CounterpartyService | None = None):
        self.db, self.accounts, self.transactions = db, accounts, transactions
        self.counterparties = counterparties or CounterpartyService(db)

    def _tag_exact_line(self, transaction_id: int, owner: str | None, account_id: int, asset_id: int,
                        quantity_e6: int) -> None:
        """Mark part or all of a posted line as held for ``owner``; the ledger's owner is the one record (2G3)."""
        if not owner:
            return
        if self.transactions is None:
            raise ValidationError("Ownership changes must be posted through the transaction service.")
        parties = self.counterparties
        party = parties.resolve(owner.strip())
        party_id = party["id"] if party else parties.create(owner.strip())
        self.transactions.mark_line_owner(transaction_id, account_id, asset_id, quantity_e6, party_id)

    def record(self, day: str, owner: str, account_id: int, amount: Decimal, notes: str = "",
               transaction_id: int | None = None) -> None:
        amount = check_places(to_decimal(amount, "amount"), 2, "amount")
        account = self.accounts.require_usable(account_id)
        parsed = parse_date(day).isoformat()
        if not owner.strip():
            raise ValidationError("Enter whose money this is.", "owner")
        if amount == ZERO:
            raise ValidationError("Enter a non-zero amount.", "amount")
        owner = owner.strip()
        if transaction_id is not None:
            self.sync_transaction(transaction_id, parsed, owner, account.id, amount, notes)
            return
        if self.transactions is None:
            raise ValidationError("Ownership changes must be posted through the transaction service.")
        parties = self.counterparties
        party = parties.resolve(owner.strip())
        if party and not party["active"]:
            raise ValidationError("Choose an active saved person.", "owner")
        if not party:
            party = parties.get(parties.create(owner))
        if amount > ZERO:
            self.transactions.change_cash_ownership(parsed, account.id, amount, None, party["id"], notes)
        else:
            self.transactions.change_cash_ownership(parsed, account.id, abs(amount), party["id"], None, notes)

    def sync_transaction(self, transaction_id: int, day: str, owner: str | None, account_id: int,
                         amount: Decimal, notes: str = "") -> None:
        """Keep the exclusion entry in step with a tagged register transaction."""
        amount = check_places(to_decimal(amount, "amount"), 2, "amount")
        self.db.execute("DELETE FROM money_from_others WHERE transaction_id=?", (transaction_id,))
        if not owner or amount == ZERO:
            return
        account = self.accounts.require_usable(account_id)
        # The posted ledger line may already carry this owner (investment buys
        # do). Read that balance once instead of subtracting the payment twice.
        tagged = self.db.scalar(
            "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le "
            "JOIN counterparties p ON p.id=le.owner_id WHERE le.transaction_id=? "
            "AND le.account_id=? AND lower(p.name)=lower(?)",
            (transaction_id, account_id, owner.strip())) or 0
        balance_after = self.cash_balance(owner, account_id, day)
        if not tagged:
            balance_after += amount
        if balance_after < ZERO:
            raise ValidationError(f"This is more than the money currently held for {owner} in this account.", "amount")
        asset = self.accounts.assets.cash_asset(account.currency)
        self._tag_exact_line(transaction_id, owner, account_id, asset.id, to_e6(amount))

    def sync_transfer(self, transaction_id: int, day: str, owner: str | None, source_id: int, target_id: int,
                      amount: Decimal, notes: str = "") -> None:
        """Move custody cash alongside an internal account transfer, without changing its total."""
        self.db.execute("DELETE FROM money_from_others WHERE transaction_id=?", (transaction_id,))
        if not owner or amount <= ZERO:
            return
        self.accounts.require_usable(source_id)
        self.accounts.require_usable(target_id)
        day = parse_date(day).isoformat()
        balance = self.cash_balance(owner, source_id, day)
        moved = min(balance, amount)
        if moved <= ZERO:
            return
        source = self.accounts.require_usable(source_id)
        target = self.accounts.require_usable(target_id)
        self._tag_exact_line(transaction_id, owner, source_id,
                             self.accounts.assets.cash_asset(source.currency).id, -to_e6(moved))
        self._tag_exact_line(transaction_id, owner, target_id,
                             self.accounts.assets.cash_asset(target.currency).id, to_e6(moved))

    @request_cached(deep=True)
    def cash_balance(self, owner: str, account_id: int, as_of: str) -> Decimal:
        day = parse_date(as_of).isoformat()
        total = self.db.scalar("""SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le
                                JOIN transactions t ON t.id=le.transaction_id
                                JOIN counterparties p ON p.id=le.owner_id
                                JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=1
                                WHERE lower(p.name)=lower(?) AND le.account_id=? AND le.date<=?
                                AND t.status='POSTED'""", (owner.strip(), account_id, day)) or 0
        return from_e6(int(total))

    @request_cached(deep=True)
    def cash_total_for_account(self, account_id: int, as_of: str) -> Decimal:
        day = parse_date(as_of).isoformat()
        totals = {row["account_id"]: row["amount_e6"] for row in self.totals_by_account(day)}
        return from_e6(int(totals.get(account_id, 0)))

    def transaction_owners(self, transaction_ids) -> dict[int, str]:
        """Who holds each transaction's money, in two reads (a register page); "" when it is yours."""
        ids = sorted(set(transaction_ids))
        owners = {txn_id: "" for txn_id in ids}
        if not ids:
            return owners
        marks = ",".join("?" * len(ids))
        for row in self.db.all(f"SELECT transaction_id, owner FROM money_from_others WHERE transaction_id IN ({marks})", ids):
            owners[row["transaction_id"]] = row["owner"]
        # The ledger's owner wins over the legacy table.
        for row in self.db.all("SELECT le.transaction_id, MIN(p.name) owner FROM ledger_entries le "
                               "JOIN counterparties p ON p.id=le.owner_id "
                               f"WHERE le.transaction_id IN ({marks}) AND le.owner_id IS NOT NULL "
                               "GROUP BY le.transaction_id", ids):
            owners[row["transaction_id"]] = row["owner"]
        return owners

    def investment_transaction_owner(self, transaction_id: int) -> str:
        row = self.db.one("SELECT p.name owner FROM ledger_entries le JOIN counterparties p ON p.id=le.owner_id JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=0 WHERE le.transaction_id=? AND le.owner_id IS NOT NULL LIMIT 1", (transaction_id,))
        return row["owner"] if row else ""

    def sync_investment(self, transaction_id: int, day: str, owner: str | None, account_id: int,
                        asset_id: int, units: Decimal) -> None:
        """Mark a trade's units as held for ``owner``. The ledger's owner is the one record of who holds what, so
        ``TransactionService._validate_owner_balances`` is the check: nobody sells units they do not hold (2G3)."""
        if not owner or units == ZERO:
            return
        units_e6 = to_e6(units)
        try:
            self._tag_exact_line(transaction_id, owner, account_id, asset_id, units_e6)
        except ValidationError as error:
            if error.field != "quantity":
                raise
            if units_e6 < 0:
                raise ValidationError(f"There are not enough units owned by {owner.strip()} to record this sale.",
                                      "units") from error
            raise ValidationError("The total marked for others cannot exceed the investment units held.",
                                  "units") from error

    @request_cached(deep=True)
    def totals_by_account(self, as_of: str) -> list[dict]:
        day = parse_date(as_of).isoformat()
        totals = {}
        for row in self.db.all("""SELECT le.account_id,SUM(le.quantity_e6) amount_e6 FROM ledger_entries le
                                JOIN transactions t ON t.id=le.transaction_id
                                JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=1
                                WHERE le.owner_id IS NOT NULL AND le.date<=? AND t.status='POSTED'
                                GROUP BY le.account_id""", (day,)):
            totals[row["account_id"]] = int(row["amount_e6"])
        return [{"account_id": account_id, "amount_e6": amount} for account_id, amount in totals.items()]

    @request_cached(deep=True)
    def by_owner(self, as_of: str) -> list[dict]:
        day = parse_date(as_of).isoformat()
        sums = {}
        rows = self.db.all("""SELECT p.name owner,le.account_id,SUM(le.quantity_e6) amount_e6
                             FROM ledger_entries le JOIN counterparties p ON p.id=le.owner_id
                             JOIN transactions t ON t.id=le.transaction_id
                             JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=1
                             WHERE le.date<=? AND t.status='POSTED' GROUP BY p.id,le.account_id""", (day,))
        for row in rows:
            sums[(row["owner"], row["account_id"])] = int(row["amount_e6"])
        return [dict(owner=owner, account_id=account_id,
                     account_name=self.accounts.get(account_id).name,
                     currency=self.accounts.get(account_id).currency, amount_e6=amount_e6,
                     amount=from_e6(amount_e6))
                for (owner, account_id), amount_e6 in sorted(sums.items())]

    def history(self, limit: int = 100) -> list[dict]:
        rows = self.db.all(
            "SELECT t.id,t.date,p.name owner,le.account_id,a.name account_name,a.currency,"
            "SUM(le.quantity_e6) amount_e6,t.notes,t.description,t.ref "
            "FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED' "
            "JOIN counterparties p ON p.id=le.owner_id JOIN accounts a ON a.id=le.account_id "
            "JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=1 "
            "WHERE le.owner_id IS NOT NULL GROUP BY t.id,le.account_id,p.id "
            "HAVING SUM(le.quantity_e6)<>0 ORDER BY t.date DESC,t.id DESC LIMIT ?", (limit,))
        return [dict(row) | {"amount": from_e6(row["amount_e6"])} for row in rows]

    @request_cached(deep=True)
    def investment_positions(self, as_of: str) -> list[dict]:
        day = parse_date(as_of).isoformat()
        rows = self.db.all(
            "SELECT p.name owner,le.account_id,le.asset_id,SUM(le.quantity_e6) AS units_e6 FROM ledger_entries le "
            "JOIN counterparties p ON p.id=le.owner_id JOIN transactions t ON t.id=le.transaction_id "
            "JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=0 "
            "WHERE le.date<=? AND t.status='POSTED' GROUP BY p.id,le.account_id,le.asset_id "
            "HAVING SUM(le.quantity_e6)<>0 ORDER BY owner,account_id,asset_id", (day,))
        return [dict(row) | {"units": from_e6(row["units_e6"])} for row in rows]

    def investment_history(self, limit: int = 100) -> list[dict]:
        """Each posted trade's units held for someone, read from the ledger's owner (2G3)."""
        rows = self.db.all(
            "SELECT t.date,p.name owner,le.account_id,le.asset_id,SUM(le.quantity_e6) units_e6,a.name AS account_name,"
            "f.name AS asset_name,f.unit,t.ref FROM ledger_entries le "
            "JOIN transactions t ON t.id=le.transaction_id AND t.status='POSTED' "
            "JOIN counterparties p ON p.id=le.owner_id JOIN accounts a ON a.id=le.account_id "
            "JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=0 "
            "GROUP BY t.id,le.account_id,le.asset_id,p.id HAVING SUM(le.quantity_e6)<>0 "
            "ORDER BY t.date DESC,t.id DESC LIMIT ?", (limit,))
        return [dict(row) | {"units": from_e6(row["units_e6"])} for row in rows]
