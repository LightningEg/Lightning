"""Custody balances: other people's funds held in the user's accounts."""

from __future__ import annotations

from decimal import Decimal

from lightning.accounts.service import AccountService
from lightning.core.dates import now_iso, parse_date
from lightning.core.errors import ValidationError
from lightning.core.memo import request_cached
from lightning.core.money import ZERO, check_places, from_e6, to_decimal, to_e6
from lightning.counterparties import CounterpartyService
from lightning.database.connection import Database


class MoneyFromOthersService:
    def __init__(self, db: Database, accounts: AccountService, transactions=None):
        self.db, self.accounts, self.transactions = db, accounts, transactions

    def _tag_exact_line(self, transaction_id: int, owner: str | None, account_id: int, asset_id: int,
                        quantity_e6: int) -> None:
        if not owner:
            return
        party = CounterpartyService(self.db).resolve(owner.strip())
        if not party:
            party_id = CounterpartyService(self.db).create(owner.strip())
            party = {"id": party_id}
        if not party:
            return
        line = self.db.one("SELECT * FROM ledger_entries WHERE transaction_id=? AND account_id=? AND asset_id=? "
                           "AND quantity_e6*?>0 AND owner_id IS NULL ORDER BY line_no LIMIT 1",
                           (transaction_id, account_id, asset_id, quantity_e6))
        if not line:
            return
        take = min(abs(quantity_e6), abs(line["quantity_e6"]))
        if take == abs(line["quantity_e6"]):
            self.db.execute("UPDATE ledger_entries SET owner_id=? WHERE id=?", (party["id"], line["id"]))
            self._validate_owner_partition(account_id, asset_id, party["id"])
            return
        total = abs(line["quantity_e6"])
        def proportional(value):
            sign = -1 if value < 0 else 1
            return sign * (abs(value) * take // total)
        owned_amount, owned_base = proportional(line["amount_e6"]), proportional(line["amount_base_e6"])
        sign = -1 if line["quantity_e6"] < 0 else 1
        self.db.execute("UPDATE ledger_entries SET quantity_e6=?,amount_e6=?,amount_base_e6=? WHERE id=?",
                        (line["quantity_e6"]-sign*take, line["amount_e6"]-owned_amount,
                         line["amount_base_e6"]-owned_base, line["id"]))
        self.db.execute("""INSERT INTO ledger_entries(transaction_id,line_no,date,account_id,asset_id,
                     quantity_e6,unit_price_e6,amount_e6,fx_rate_e6,amount_base_e6,effect,category_id,memo,
                     cleared,owner_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (line["transaction_id"], line["line_no"]+10000, line["date"], line["account_id"],
                         line["asset_id"], sign*take, line["unit_price_e6"], owned_amount,
                         line["fx_rate_e6"], owned_base, line["effect"], line["category_id"], line["memo"],
                         line["cleared"], party["id"]))
        self._validate_owner_partition(account_id, asset_id, party["id"])

    def _validate_owner_partition(self, account_id: int, asset_id: int, owner_id: int) -> None:
        for balance_owner in (owner_id, None):
            rows = self.db.all("""SELECT le.date,SUM(le.quantity_e6) quantity FROM ledger_entries le
                                 JOIN transactions t ON t.id=le.transaction_id
                                 WHERE t.status='POSTED' AND le.account_id=? AND le.asset_id=? AND le.owner_id IS ?
                                 GROUP BY le.date ORDER BY le.date""",
                               (account_id, asset_id, balance_owner))
            running = 0
            for row in rows:
                running += int(row["quantity"])
                if running < 0:
                    label = "selected owner" if balance_owner is not None else "user"
                    raise ValidationError(f"The {label}'s balance would become negative on {row['date']}.", "owner")

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
        parties = CounterpartyService(self.db)
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
        legacy = self.db.scalar("""SELECT COALESCE(SUM(amount_e6),0) FROM money_from_others
                                WHERE lower(owner)=lower(?) AND account_id=? AND date<=? AND transaction_id IS NULL""",
                                (owner.strip(), account_id, day)) or 0
        return from_e6(int(total) + int(legacy))

    @request_cached(deep=True)
    def cash_total_for_account(self, account_id: int, as_of: str) -> Decimal:
        day = parse_date(as_of).isoformat()
        ledger = self.db.scalar("""SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le
                                JOIN transactions t ON t.id=le.transaction_id
                                JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=1
                                WHERE le.account_id=? AND le.owner_id IS NOT NULL AND le.date<=? AND t.status='POSTED'""",
                                (account_id, day)) or 0
        legacy = self.db.scalar("SELECT COALESCE(SUM(amount_e6),0) FROM money_from_others WHERE account_id=? AND date<=? AND transaction_id IS NULL",
                                (account_id, day)) or 0
        return from_e6(int(ledger) + int(legacy))

    def transaction_owner(self, transaction_id: int) -> str:
        row = self.db.one("SELECT p.name owner FROM ledger_entries le JOIN counterparties p ON p.id=le.owner_id WHERE le.transaction_id=? AND le.owner_id IS NOT NULL LIMIT 1", (transaction_id,))
        if row:
            return row["owner"]
        row = self.db.one("SELECT owner FROM money_from_others WHERE transaction_id=?", (transaction_id,))
        return row["owner"] if row else ""

    def transaction_owners(self, transaction_ids) -> dict[int, str]:
        """transaction_owner for many transactions in two reads (a register page), "" when it is yours."""
        ids = sorted(set(transaction_ids))
        owners = {txn_id: "" for txn_id in ids}
        if not ids:
            return owners
        marks = ",".join("?" * len(ids))
        for row in self.db.all(f"SELECT transaction_id, owner FROM money_from_others WHERE transaction_id IN ({marks})", ids):
            owners[row["transaction_id"]] = row["owner"]
        # The ledger's owner wins over the legacy table, as in transaction_owner.
        for row in self.db.all("SELECT le.transaction_id, MIN(p.name) owner FROM ledger_entries le "
                               "JOIN counterparties p ON p.id=le.owner_id "
                               f"WHERE le.transaction_id IN ({marks}) AND le.owner_id IS NOT NULL "
                               "GROUP BY le.transaction_id", ids):
            owners[row["transaction_id"]] = row["owner"]
        return owners

    def investment_transaction_owner(self, transaction_id: int) -> str:
        row = self.db.one("SELECT p.name owner FROM ledger_entries le JOIN counterparties p ON p.id=le.owner_id JOIN financial_assets f ON f.id=le.asset_id AND f.is_cash=0 WHERE le.transaction_id=? AND le.owner_id IS NOT NULL LIMIT 1", (transaction_id,))
        if row:
            return row["owner"]
        row = self.db.one("SELECT owner FROM investment_custody_events WHERE transaction_id=?", (transaction_id,))
        return row["owner"] if row else ""

    def sync_investment(self, transaction_id: int, day: str, owner: str | None, account_id: int,
                        asset_id: int, units: Decimal) -> None:
        if not owner or units == ZERO:
            self.db.execute("DELETE FROM investment_custody_events WHERE transaction_id=?", (transaction_id,))
            return
        units_e6 = to_e6(units)
        existing = self.db.one("SELECT owner,account_id,asset_id,units_e6 FROM investment_custody_events WHERE transaction_id=?",
                               (transaction_id,))
        current = self.db.scalar(
            "SELECT COALESCE(SUM(units_e6),0) FROM investment_custody_events "
            "WHERE owner=? AND account_id=? AND asset_id=? AND date<=? AND transaction_id<>?",
            (owner.strip(), account_id, asset_id, parse_date(day).isoformat(), transaction_id))
        if int(current or 0) + units_e6 < 0:
            raise ValidationError(f"There are not enough units owned by {owner} to record this sale.", "units")
        custody_units = self.db.scalar(
            "SELECT COALESCE(SUM(e.units_e6),0) FROM investment_custody_events e "
            "JOIN transactions t ON t.id=e.transaction_id WHERE e.account_id=? AND e.asset_id=? "
            "AND e.date<=? AND t.status='POSTED' AND e.transaction_id<>?",
            (account_id, asset_id, parse_date(day).isoformat(), transaction_id))
        total_units = self.db.scalar(
            "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le JOIN transactions t "
            "ON t.id=le.transaction_id WHERE le.account_id=? AND le.asset_id=? AND le.date<=? "
            "AND t.status='POSTED'",
            (account_id, asset_id, parse_date(day).isoformat()))
        if int(custody_units or 0) + units_e6 > int(total_units or 0):
            raise ValidationError("The total marked for others cannot exceed the investment units held.", "units")
        self.db.execute(
            "INSERT INTO investment_custody_events(transaction_id,date,owner,account_id,asset_id,units_e6,created_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(transaction_id) DO UPDATE SET date=excluded.date,owner=excluded.owner,"
            "account_id=excluded.account_id,asset_id=excluded.asset_id,units_e6=excluded.units_e6",
            (transaction_id, parse_date(day).isoformat(), owner.strip(), account_id, asset_id, units_e6, now_iso()))
        self._tag_exact_line(transaction_id, owner, account_id, asset_id, units_e6)

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
        for row in self.db.all("""SELECT account_id,SUM(amount_e6) amount_e6 FROM money_from_others
                                WHERE date<=? AND transaction_id IS NULL GROUP BY account_id""", (day,)):
            totals[row["account_id"]] = totals.get(row["account_id"], 0) + int(row["amount_e6"])
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
        for row in self.db.all("""SELECT owner,account_id,SUM(amount_e6) amount_e6 FROM money_from_others
                                 WHERE date<=? AND transaction_id IS NULL GROUP BY owner,account_id""", (day,)):
            key = (row["owner"], row["account_id"])
            sums[key] = sums.get(key, 0) + int(row["amount_e6"])
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
        result = [dict(row) | {"amount": from_e6(row["amount_e6"])} for row in rows]
        remaining = max(0, limit - len(result))
        if remaining:
            legacy = self.db.all(
                "SELECT m.*,a.name AS account_name,a.currency FROM money_from_others m "
                "JOIN accounts a ON a.id=m.account_id WHERE m.transaction_id IS NULL "
                "ORDER BY m.date DESC,m.id DESC LIMIT ?", (remaining,))
            result.extend(dict(row) | {"amount": from_e6(row["amount_e6"])} for row in legacy)
        return sorted(result, key=lambda row: (row["date"], row.get("id", 0)), reverse=True)[:limit]

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
        rows = self.db.all(
            "SELECT e.date,e.owner,e.account_id,e.asset_id,e.units_e6,a.name AS account_name,"
            "f.name AS asset_name,f.unit,t.ref FROM investment_custody_events e "
            "JOIN transactions t ON t.id=e.transaction_id JOIN accounts a ON a.id=e.account_id "
            "JOIN financial_assets f ON f.id=e.asset_id WHERE t.status='POSTED' "
            "ORDER BY e.date DESC,e.id DESC LIMIT ?", (limit,))
        return [dict(row) | {"units": from_e6(row["units_e6"])} for row in rows]
