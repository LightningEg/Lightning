"""Public API of the accounts module.

Opening balances are NOT stored here — the workflow layer records them as an
opening transaction, so every balance comes from the ledger.
"""

from __future__ import annotations

from dataclasses import replace

from lightning.assets.service import AssetService
from lightning.core.codes import validate_account_code
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import ConflictError, NotFoundError, ValidationError
from lightning.core.memo import in_request, request_cached
from lightning.database.connection import Database

from .domain import DEFAULT_CASH_CLASS, OFFERED_TYPES, TYPE_LABELS, Account, AccountType, suggest_code
from .repository import AccountRepository
from .valuations import OtherAssetValuationRepository


class AccountService:
    def __init__(self, db: Database, assets: AssetService, base_currency: str):
        self.db = db
        self.repo = AccountRepository(db)
        self.assets = assets
        self.base_currency = base_currency

    # -- reading -----------------------------------------------------------
    @request_cached
    def list(self, active_only: bool = False) -> list[Account]:
        return self.repo.list(active_only)

    @request_cached
    def _by_id(self) -> dict[int, Account]:
        return {item.id: item for item in self.repo.list(False)}

    def get(self, account_id: int) -> Account:
        found = self._by_id().get(account_id) if in_request() else self.repo.get(account_id)
        if not found:
            raise NotFoundError("Account not found.")
        return found

    def manual_value(self, account_id: int, as_of: str) -> dict | None:
        """An Other asset account's latest value you entered on or before `as_of`: date, value and notes."""
        return OtherAssetValuationRepository(self.db).latest(account_id, as_of)

    def find_by_text(self, text: str) -> Account | None:
        """An active account matching what was typed: its label ('CIB-CUR-EGP · CIB Current'), code or name."""
        wanted = " ".join((text or "").split()).casefold()
        if not wanted:
            return None
        matches = []
        for account in self.repo.list(active_only=True):
            if wanted in (account.label.casefold(), account.code.casefold(), account.name.casefold(),
                          f"{account.code} · {account.name}".casefold()):
                matches.append(account)
        if len(matches) > 1:
            raise ValidationError("More than one account has that name. Choose its code from the account picker.",
                                  "counterparty")
        return matches[0] if matches else None

    def require_usable(self, account_id: int | None, field: str = "account") -> Account:
        if account_id is None:
            raise ValidationError("Choose an account.", field)
        account = self.get(account_id)
        if not account.active:
            raise ValidationError(f"{account.label} is inactive.", field)
        return account

    def unique_code(self, institution: str, name: str, account_type: AccountType, currency: str) -> str:
        base = suggest_code(institution, name, account_type, currency)
        code, n = base, 1
        while self.repo.code_exists(code):
            n += 1
            code = f"{base}-{n}"
        return code

    # -- writing -----------------------------------------------------------
    def create(
        self,
        name: str,
        account_type: AccountType | str,
        opening_date: str,
        institution: str = "",
        currency: str | None = None,
        code: str | None = None,
        last4: str | None = None,
        notes: str = "",
    ) -> Account:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter an account name.", "name")
        self._ensure_unique_name(name)
        selected_type = self._type(account_type)
        cash_at_hand = selected_type == AccountType.CASH_AT_HAND
        account_type = AccountType.CASH if cash_at_hand else selected_type
        currency = (currency or self.base_currency).strip().upper()
        if not self.db.scalar("SELECT 1 FROM registered_currencies WHERE code=?", (currency,)):
            raise ValidationError(f"Currency {currency} is not registered. Add it in Settings first.", "currency")
        self.assets.cash_asset(currency)  # currency must exist
        institution = (institution or "").strip()
        code = validate_account_code(code) if code and code.strip() else self.unique_code(
            institution, name, account_type, currency
        )
        if self.repo.code_exists(code):
            raise ConflictError(f"The code {code} is already used by another account.", "code")
        account = Account(
            id=0,
            code=code,
            name=name,
            institution=institution,
            account_type=account_type,
            currency=currency,
            cash_class_id=self._cash_class_id(account_type),
            opening_date=self._start(opening_date),
            is_system=False,
            last4=self._last4(last4),
            active=True,
            sort_order=self.repo.next_sort_order(),
            notes=(notes or "").strip(),
            cash_at_hand=cash_at_hand,
        )
        with self.db.transaction():
            new_id = self.repo.insert(account)
        return self.get(new_id)

    def update(
        self,
        account_id: int,
        name: str,
        institution: str,
        account_type: AccountType | str,
        opening_date: str,
        code: str | None = None,
        last4: str | None = None,
        notes: str = "",
    ) -> tuple[Account, bool]:
        """Returns (updated account, whether code or name changed)."""
        current = self.get(account_id)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter an account name.", "name")
        self._ensure_unique_name(name, exclude_id=account_id)
        selected_type = self._type(account_type)
        cash_at_hand = selected_type == AccountType.CASH_AT_HAND
        account_type = AccountType.CASH if cash_at_hand else selected_type
        new_code = validate_account_code(code) if code and code.strip() else current.code
        if self.repo.code_exists(new_code, exclude_id=current.id):
            raise ConflictError(f"The code {new_code} is already used by another account.", "code")
        updated = replace(
            current,
            code=new_code,
            name=name,
            institution=(institution or "").strip(),
            account_type=account_type,
            cash_class_id=self._cash_class_id(account_type),
            cash_at_hand=cash_at_hand,
            opening_date=self._start(opening_date),
            last4=self._last4(last4),
            notes=(notes or "").strip(),
        )
        with self.db.transaction():
            self.repo.update(updated)
        return self.get(account_id), (new_code != current.code or name != current.name)

    # ------------------------------------------------------------------ broker currency pockets
    def pockets(self, broker_id: int) -> list[Account]:
        """A broker's pockets in other currencies (its own currency is the broker account itself)."""
        return [a for a in self.list() if a.parent_id == broker_id]

    def broker_of(self, account: Account) -> Account:
        """The broker account a pocket belongs to; any other account is its own broker."""
        return self.get(account.parent_id) if account.parent_id else account

    def pocket_for(self, account: Account, currency: str, create: bool = False) -> Account | None:
        """The account of this broker that holds ``currency``: the broker itself in its own currency, else a pocket
        (made on demand when ``create``). None when it has none and ``create`` is off."""
        broker = self.broker_of(account)
        currency = (currency or "").strip().upper()
        if broker.currency == currency:
            return broker
        found = next((p for p in self.pockets(broker.id) if p.currency == currency), None)
        if found or not create:
            return found
        return self.add_pocket(broker.id, currency)

    def add_pocket(self, broker_id: int, currency: str) -> Account:
        """Add a currency to a broker: a child brokerage account named "<broker> · <CUR>", one row per broker on
        screen (owner decision 2026-10-16). No margin: a pocket never goes below zero (ledger rules)."""
        broker = self.get(broker_id)
        currency = (currency or "").strip().upper()
        if broker.account_type != AccountType.BROKERAGE or broker.parent_id:
            raise ValidationError("Only a brokerage account can hold other currencies.", "currency")
        if currency == broker.currency or any(p.currency == currency for p in self.pockets(broker.id)):
            raise ConflictError(f"{broker.label} already holds {currency}.", "currency")
        from lightning.database.currencies import CurrencyRegistry
        from lightning.market.iso import RATED_CURRENCIES
        if currency not in RATED_CURRENCIES | {self.base_currency}:
            raise ValidationError(f"{currency} has no exchange rate source; choose another currency.", "currency")
        CurrencyRegistry(self.db).register(currency)
        name = f"{broker.name} · {currency}"
        code = self.unique_code(broker.institution, broker.name, AccountType.BROKERAGE, currency)
        pocket = Account(
            id=0, code=code, name=name, institution=broker.institution, account_type=AccountType.BROKERAGE,
            currency=currency, cash_class_id=self._cash_class_id(AccountType.BROKERAGE),
            opening_date=broker.opening_date, is_system=False, last4=None, active=True,
            sort_order=self.repo.next_sort_order(), notes="", parent_id=broker.id,
        )
        with self.db.transaction():
            new_id = self.repo.insert(pocket)
        return self.get(new_id)

    def set_spendable(self, account_id: int, choice: bool | None) -> Account:
        """Count this account's cash as spendable (True), keep it apart (False) or follow the default (None)."""
        current = self.get(account_id)
        with self.db.transaction():
            self.repo.update(replace(current, spendable=choice))
        return self.get(account_id)

    def _ensure_unique_name(self, name: str, exclude_id: int | None = None) -> None:
        wanted = name.casefold()
        if any(account.id != exclude_id and account.name.casefold() == wanted for account in self.repo.list()):
            raise ConflictError("An account with this name already exists. Choose a different name.", "name")

    def set_active(self, account_id: int, active: bool) -> Account:
        account = self.get(account_id)
        with self.db.transaction():
            self.repo.update(replace(account, active=active))
        return self.get(account_id)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _start(value: str) -> str:
        day = parse_date(value, "opening_date")
        if day > today():
            raise ValidationError("An account cannot start in the future.", "opening_date")
        return fmt_date(day)

    @staticmethod
    def _type(value: AccountType | str) -> AccountType:
        try:
            account_type = AccountType(value)
        except ValueError:
            raise ValidationError("Choose an account type.", "account_type") from None
        if account_type not in OFFERED_TYPES:
            raise ValidationError(f"{TYPE_LABELS[account_type]} accounts are not available yet.", "account_type")
        return account_type

    def _cash_class_id(self, account_type: AccountType) -> int:
        """Where this account's cash appears in reports — always decided by the type."""
        return self.assets.get_class_by_code(DEFAULT_CASH_CLASS[account_type]).id

    def reporting_group(self, account: Account) -> str:
        """Plain-language place in 'What your wealth is made of', e.g. 'Liquid Cash › Bank Balance'."""
        return self.assets.display_name(account.cash_class_id)

    @staticmethod
    def _last4(value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if len(value) != 4 or not value.isdigit():
            raise ValidationError("Enter only the last 4 digits (never the full number).", "last4")
        return value
