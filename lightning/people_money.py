"""Money lent to people and paid back (NF-12G, owner 2026-11-08).

Each person has one RECEIVABLE "Owed to you" account (``owed_to_you_accounts`` links it to the person). Lending and
repayment are transfers between your bank or wallet and that account, so Net worth never moves with them; forgiving
is spending out of that account. A positive balance is Owed to you (in What you own, under Other you own); a balance
below zero is what you owe that person (in What you owe). Nothing is assumed repaid until the repayment is posted.
"""
from __future__ import annotations

from decimal import Decimal

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, now_iso, parse_date, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.money import ZERO, check_places, fmt, from_e6, to_decimal
from lightning.deposits.repository import DepositRepository

LIQUID = {AccountType.BANK, AccountType.CASH}


class PeopleMoneyService:
    def __init__(self, db, accounts, transactions, counterparties):
        self.db = db
        self.accounts = accounts
        self.transactions = transactions
        self.counterparties = counterparties
        self.repo = DepositRepository(db)  # the owned-cash walk a certificate purchase uses

    # ------------------------------------------------------------ accounts
    def account_id_for(self, person_id: int) -> int | None:
        found = self.db.scalar("SELECT account_id FROM owed_to_you_accounts WHERE counterparty_id=?", (int(person_id),))
        return int(found) if found else None

    def account_for(self, person_id: int, opening_date: str | None = None):
        """The person's Owed to you account, made on first use."""
        person = self._person(person_id)
        found = self.account_id_for(person["id"])
        if found:
            return self.accounts.get(found)
        name = self._unique_name(f"Owed to you · {person['name']}")
        with self.db.transaction():
            account = self.accounts.create(name, AccountType.RECEIVABLE, opening_date or fmt_date(today()),
                                           internal=True)
            self.db.execute("INSERT INTO owed_to_you_accounts(account_id,counterparty_id,created_at) VALUES (?,?,?)",
                            (account.id, person["id"], now_iso()))
        return account

    # ------------------------------------------------------------ actions
    def lend(self, day, person_id: int, from_account_id: int, amount, notes: str = ""):
        """Money you lent: a transfer from your cash to the person's account."""
        when, value = parse_date(day, "day"), self._amount(amount)
        source = self._liquid(from_account_id, "from_account_id")
        self._check_owned_cash(source, when, value)
        with self.db.transaction():
            account = self.account_for(person_id, self._opening(when))
            self._same_currency(source, account)
            return self.transactions.record_transfer(fmt_date(when), source.id, account.id, value,
                                                     f"Lent to {self._person(person_id)['name']}", notes)

    def repay(self, day, person_id: int, to_account_id: int, amount, notes: str = ""):
        """Money paid back to you: a transfer from the person's account to your cash. Never more than is owed."""
        when, value = parse_date(day, "day"), self._amount(amount)
        destination = self._liquid(to_account_id, "to_account_id")
        owed = self.balance(person_id, fmt_date(when))
        if value > owed:
            raise ValidationError(f"{self._person(person_id)['name']} owes you {fmt(owed, 2)}; "
                                  f"a repayment of {fmt(value, 2)} is more than that.", "amount")
        account = self.account_for(person_id, self._opening(when))
        self._same_currency(destination, account)
        return self.transactions.record_transfer(fmt_date(when), account.id, destination.id, value,
                                                 f"Paid back by {self._person(person_id)['name']}", notes)

    def forgive(self, day, person_id: int, amount, category_id: int, notes: str = ""):
        """Money you will not get back becomes spending, out of the person's account. Never more than is owed."""
        when, value = parse_date(day, "day"), self._amount(amount)
        owed = self.balance(person_id, fmt_date(when))
        if value > owed:
            raise ValidationError(f"{self._person(person_id)['name']} owes you {fmt(owed, 2)}; "
                                  f"you cannot forgive {fmt(value, 2)}.", "amount")
        account = self.account_for(person_id, self._opening(when))
        return self.transactions.record_outflow(fmt_date(when), account.id, value, int(category_id),
                                                f"Forgave {self._person(person_id)['name']}",
                                                self._person(person_id)["name"], notes)

    # ------------------------------------------------------------ reading
    def balance(self, person_id: int, as_of=None) -> Decimal:
        """What the person owes you on the day (below zero: what you owe them)."""
        account_id = self.account_id_for(person_id)
        return ZERO if account_id is None else self._account_balance(account_id, as_of)

    def owed_to_you(self, as_of=None) -> Decimal:
        """Owed to you: the sum of the people's balances above zero."""
        return sum((max(ZERO, value) for _, value in self._balances(as_of)), ZERO)

    def you_owe_people(self, as_of=None) -> Decimal:
        """What you owe people: the sum of the balances below zero, as a positive amount."""
        return sum((max(ZERO, -value) for _, value in self._balances(as_of)), ZERO)

    # ------------------------------------------------------------ helpers
    def _balances(self, as_of=None) -> list[tuple[int, Decimal]]:
        return [(int(row["counterparty_id"]), self._account_balance(int(row["account_id"]), as_of))
                for row in self.db.all("SELECT account_id,counterparty_id FROM owed_to_you_accounts")]

    def _account_balance(self, account_id: int, as_of=None) -> Decimal:
        day = fmt_date(parse_date(as_of or today()))
        return from_e6(self.db.scalar(
            "SELECT COALESCE(SUM(le.quantity_e6),0) FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
            "WHERE t.status='POSTED' AND le.account_id=? AND le.date<=?", (account_id, day)) or 0)

    def _person(self, person_id) -> dict:
        try:
            row = self.counterparties.get(int(person_id))
        except (TypeError, ValueError):
            row = None
        if not row:
            raise NotFoundError("Choose a person.")
        return {"id": int(row["id"]), "name": row["name"]}

    def _liquid(self, account_id, field: str):
        try:
            account = self.accounts.require_usable(int(account_id), field)
        except (TypeError, ValueError):
            raise ValidationError("Choose a bank or cash account.", field) from None
        if account.account_type not in LIQUID:
            raise ValidationError("Choose a bank or cash account.", field)
        return account

    @staticmethod
    def _same_currency(cash, account) -> None:
        if cash.currency != account.currency:
            raise ValidationError(f"Lend and repay in {account.currency}, the currency of this person's account.",
                                  "amount")

    @staticmethod
    def _amount(amount) -> Decimal:
        value = check_places(to_decimal(amount, "amount"), 2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter an amount above zero.", "amount")
        return value

    def _opening(self, when) -> str:
        return fmt_date(min(when, today()))

    def _check_owned_cash(self, source, when, value: Decimal) -> None:
        """You cannot lend cash you do not own that day (money held for others stays theirs), nor leave a later day
        short."""
        from lightning.core.money import to_e6
        available = self.repo.owned_balance_e6(source.id, fmt_date(when))
        if available < to_e6(value):
            raise ValidationError(f"{source.name} had {fmt(from_e6(available), 2)} {source.currency} of your cash on "
                                  f"{fmt_date(when)}; lending {fmt(value, 2)} needs more.", "amount")
        remaining = available - to_e6(value)
        for movement in self.repo.owned_cash_deltas_after(source.id, fmt_date(when)):
            remaining += int(movement["delta_e6"] or 0)
            if remaining < 0:
                raise ValidationError(f"After activity dated {movement['date']}, {source.name} would go below zero. "
                                      "Lend a smaller amount or check the later activity.", "amount")

    def _unique_name(self, base: str) -> str:
        name, n = base, 2
        while self.db.scalar("SELECT 1 FROM accounts WHERE lower(name)=lower(?)", (name,)):
            name, n = f"{base} {n}", n + 1
        return name
