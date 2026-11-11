"""Transaction balance and certificate policies, separate from posting orchestration.

All checks are reads. The transaction facade still owns posting and save scopes.
Daily owner/cash checks retain their distinct validation windows and messages.
"""
from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.accounts.service import AccountService
from lightning.assets.service import AssetService
from lightning.core.balances import running_balances
from lightning.core.errors import ValidationError
from lightning.core.ledger import Effect
from lightning.core.money import ZERO, fmt
from lightning.core.refs import DocType
from lightning.database.connection import Database

from .domain import Transaction, TxnSource


class BalanceChecks:
    def __init__(self, db: Database, accounts: AccountService, assets: AssetService):
        self.db, self.accounts, self.assets = db, accounts, assets

    def _validate_owner_balances(self, lines, day, exclude_txn_id=None, force_brokerage_cash=False,
                                 validate_all_cash=False, extra_keys=(), ignore_before_day=False,
                                 validate_from=None):
        """An owner's dated account/asset position may never become negative."""
        keys = set(extra_keys)
        for line in lines:
            asset = self.assets.get_asset(line.asset_id)
            account = self.accounts.get(line.account_id)
            if line.owner_id is not None:
                owner = self.db.one("SELECT id FROM counterparties WHERE id=? AND active=1", (line.owner_id,))
                if not owner:
                    raise ValidationError("Choose an active saved owner.", "owner_id")
            if ((line.owner_id is not None and line.quantity != ZERO) or not asset.is_cash or
                    (validate_all_cash and asset.is_cash and line.quantity != ZERO) or
                    (force_brokerage_cash and line.effect == Effect.INTERNAL and
                     account.account_type == AccountType.BROKERAGE)):
                keys.add((line.account_id, line.asset_id, line.owner_id))
        for account_id, asset_id, owner_id in keys:
            params = [account_id, asset_id, owner_id]
            sql = ("SELECT le.date, SUM(le.quantity_e6) q FROM ledger_entries le "
                   "JOIN transactions t ON t.id=le.transaction_id "
                   "WHERE t.status='POSTED' AND le.account_id=? AND le.asset_id=? AND le.owner_id IS ?")
            if exclude_txn_id is not None:
                sql += " AND t.id<>?"
                params.append(exclude_txn_id)
            sql += " GROUP BY le.date ORDER BY le.date"
            proposed = sum(int(line.quantity * 1_000_000) for line in lines
                           if (line.account_id, line.asset_id, line.owner_id) == (account_id, asset_id, owner_id))
            by_day = {}
            for row in self.db.all(sql, tuple(params)):
                by_day[row["date"]] = int(row["q"])
            by_day[str(day)] = by_day.get(str(day), 0) + proposed
            for step in running_balances(sorted(by_day.items())):
                on, before_day, running = step.day, step.before, step.after
                if running < 0 and (not ignore_before_day or on >= str(validate_from or day)):
                    asset = self.assets.get_asset(asset_id)
                    if not asset.is_cash:
                        raise ValidationError(
                            f"{self.accounts.get(account_id).label} would hold less than zero {asset.name} on {on}.",
                            "quantity")
                    owner_label = "the user's" if owner_id is None else "the selected owner's"
                    after = Decimal(running).scaleb(-6)
                    before = Decimal(before_day).scaleb(-6)
                    account = self.accounts.get(account_id)
                    context = (f"This purchase is dated {day}; check whether later payments still fit."
                               if on > str(day) else
                               "Only cash available on the purchase date can fund it.")
                    raise ValidationError(
                        f"This would leave {owner_label} balance at {fmt(after, 2, True)} {account.currency} "
                        f"in {account.label} on {on}; the balance before that date's transactions was "
                        f"{fmt(before, 2)} {account.currency}. {context}",
                        "owner")

    def _refuse_cash_below_zero(self, lines, day, current: Transaction | None = None, *, removed=(), added=()) -> None:
        """Compare every affected cash history before/after the whole action (2G/2H).

        Snapshots of removed postings make this work before or after SQL changes,
        including multi-delete and restoring a void document. Imported/system
        posting history may contain deficits; unchanged or improved days remain editable.
        """
        previous = [txn for txn in (([current] if current else []) + list(removed)) if not txn.is_void]
        following = [(str(day), lines)] + [(txn.date, txn.lines) for txn in added if not txn.is_void]
        old_lines = [line for txn in previous for line in txn.lines]
        new_lines = [line for _, posting in following for line in posting]
        keys = {(line.account_id, line.asset_id) for line in new_lines + old_lines
                if line.quantity != ZERO and self.assets.get_asset(line.asset_id).is_cash}
        excluded = {txn.id for txn in previous} | {txn.id for txn in added}
        if current:
            excluded.add(current.id)
        first = min([str(day)] + [txn.date for txn in previous] + [on for on, _ in following])
        for account_id, asset_id in keys:
            account = self.accounts.get(account_id)
            if account.account_type not in {AccountType.CASH, AccountType.BANK, AccountType.BROKERAGE}:
                continue
            start = max(first, account.opening_date)
            # Aggregate the opening balance once, then walk affected days on the account index.
            exclusion = " AND le.transaction_id NOT IN (" + ",".join("?" for _ in excluded) + ")" if excluded else ""
            opening = self.db.scalar(
                "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le "
                "JOIN transactions t ON t.id=le.transaction_id "
                "WHERE t.status='POSTED' AND le.account_id=? AND le.date<? AND +le.asset_id=?" + exclusion,
                (account_id, start, asset_id, *excluded))
            base = {"": int(opening)}
            for row in self.db.all(
                "SELECT le.date, SUM(le.quantity_e6) q FROM ledger_entries le "
                "JOIN transactions t ON t.id=le.transaction_id "
                "WHERE t.status='POSTED' AND le.account_id=? AND le.date>=? AND +le.asset_id=?" + exclusion +
                " GROUP BY le.date",
                (account_id, start, asset_id, *excluded)):
                base[row["date"]] = int(row["q"])
            before, after = dict(base), dict(base)
            for txn in previous:
                for line in txn.lines:
                    if (line.account_id, line.asset_id) == (account_id, asset_id):
                        before[txn.date] = before.get(txn.date, 0) + int(line.quantity * 1_000_000)
            for on, posting in following:
                for line in posting:
                    if (line.account_id, line.asset_id) == (account_id, asset_id):
                        after[on] = after.get(on, 0) + int(line.quantity * 1_000_000)
            days = sorted(set(before) | set(after) | {start})
            previous_steps = running_balances((on, before.get(on, 0)) for on in days)
            following_steps = running_balances((on, after.get(on, 0)) for on in days)
            for old, new in zip(previous_steps, following_steps, strict=True):
                on, old_balance, new_balance = new.day, old.after, new.after
                if on >= start and new_balance < min(0, old_balance):
                    raise ValidationError(
                        f"This would leave {account.label} at {fmt(Decimal(new_balance).scaleb(-6), 2, True)} "
                        f"{account.currency} on {on}. Move money in first, or record the smaller amount.", "amount")

    def _validate_deposit_lines(self, lines, doc_type: DocType, source: TxnSource) -> None:
        """CD portfolios hold certificate assets only; cash stays in bank and wallet accounts."""
        for line in lines:
            account = self.accounts.get(line.account_id)
            asset = self.assets.get_asset(line.asset_id)
            is_certificate = self.assets.get_class(asset.asset_class_id).code == "DEPOSIT.CD"
            if account.account_type == AccountType.DEPOSIT:
                if asset.is_cash:
                    raise ValidationError("A CD portfolio cannot hold cash. Use the CD purchase or redemption action.")
                if (doc_type == DocType.VAL and source == TxnSource.SYSTEM and
                        line.effect == Effect.REVALUATION and line.quantity == ZERO and not line.is_cash and
                        is_certificate):
                    continue
                # NF-12I: a certificate already owned when tracking began is an opening unit line.
                owned_opening = doc_type == DocType.OPN and line.effect == Effect.OPENING and not line.is_cash
                if not is_certificate or (doc_type not in {DocType.BUY, DocType.SEL} and not owned_opening):
                    raise ValidationError("Only CD certificates can be traded in a CD portfolio.", "asset")
            elif is_certificate:
                raise ValidationError("Certificates must be held in a bank-specific CD portfolio.", "account")
