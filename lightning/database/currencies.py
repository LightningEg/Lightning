"""Profile currency registration and ISO 4217 suggestions."""

from __future__ import annotations

import re
from typing import Any

from lightning.core.dates import now_iso

from .connection import Database
from .settings import SettingsStore



# ISO 4217 minor units that are not 2 (audit 2026-10-15). Currencies with none (JPY) keep 2 here so amounts
# typed with cents are not refused; the three-decimal ones need their third place.
_THREE_DECIMALS = frozenset({"KWD", "BHD", "OMR", "JOD", "TND", "LYD", "IQD"})


def minor_units(code: str) -> int:
    """How many decimals a cash amount in this currency may have: 3 for the dinars and the Omani rial, else 2."""
    return 3 if (code or "").upper() in _THREE_DECIMALS else 2

class CurrencyRegistry:
    """Currencies a profile can use, plus the ISO 4217 suggestion catalog."""

    def __init__(self, db: Database):
        self.db = db

    def suggestions(self, query: str = "") -> list[dict[str, str]]:
        """Return ISO currency suggestions; user-created codes are intentionally excluded."""
        term = query.strip().casefold()
        return [dict(row) for row in self.db.all(
            "SELECT code, name FROM currency_suggestions "
            "WHERE ? = '' OR lower(code) LIKE ? OR lower(name) LIKE ? ORDER BY code",
            (term, f"%{term}%", f"%{term}%"),
        )]

    def list(self) -> list[dict[str, Any]]:
        """Return explicitly registered currencies in code order."""
        return [dict(row) for row in self.db.all(
            "SELECT code, name, is_custom FROM registered_currencies ORDER BY code"
        )]

    def register(self, code: str, name: str | None = None) -> dict[str, Any]:
        """Register an ISO currency or a custom three-letter code and its cash asset."""
        code = (code or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("Currency codes must contain exactly three letters.")
        existing = self.db.one(
            "SELECT code,name,is_custom FROM registered_currencies WHERE code = ?", (code,)
        )
        if existing is not None:
            return dict(existing)
        suggestion = self.db.one(
            "SELECT name FROM currency_suggestions WHERE code = ?", (code,)
        )
        custom = suggestion is None
        label = (name or "").strip() if custom else suggestion["name"]
        if not label:
            raise ValueError("A name is required for a custom currency code.")
        now = now_iso()
        with self.db.transaction():
            self.db.execute(
                "INSERT OR IGNORE INTO registered_currencies(code,name,is_custom,registered_at) "
                "VALUES(?,?,?,?)", (code, label, int(custom), now)
            )
            cash_class = self.db.scalar("SELECT id FROM asset_classes WHERE code='CASH'")
            if cash_class is not None:
                self.db.execute(
                    "INSERT OR IGNORE INTO financial_assets(code,name,asset_class_id,currency,unit,"
                    "quantity_decimals,is_cash,exposure,liquidity,price_source,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,1,'CASH','IMMEDIATE','NONE',?,?)",
                    (f"CASH:{code}", label, cash_class, code, code, minor_units(code), now, now),
                )
        row = self.db.one(
            "SELECT code,name,is_custom FROM registered_currencies WHERE code=?", (code,)
        )
        return dict(row)

    def set_base_currency(self, code: str) -> None:
        """Set the profile base before financial history makes that change unsafe."""
        code = (code or "").strip().upper()
        if not self.db.scalar("SELECT 1 FROM registered_currencies WHERE code=?", (code,)):
            raise ValueError("Register this currency before setting it as the profile currency.")
        with self.db.transaction():
            current = SettingsStore(self.db).base_currency
            if current == code:
                return
            if self.db.scalar("SELECT EXISTS(SELECT 1 FROM ledger_entries)") or self.db.scalar(
                "SELECT EXISTS(SELECT 1 FROM fx_rates)"
            ):
                raise ValueError("The profile currency cannot change after any entries or FX rates exist.")
            reference_codes = ("GLD:18K", "REF:GLD-21K", "REF:GLD-24K")
            placeholders = ",".join("?" for _ in reference_codes)
            if self.db.scalar(
                f"SELECT EXISTS(SELECT 1 FROM price_history p JOIN financial_assets a "
                f"ON a.id=p.asset_id WHERE a.code IN ({placeholders}))", reference_codes
            ):
                raise ValueError("The profile currency cannot change after gold reference prices exist.")
            if self.db.scalar(
                "SELECT EXISTS(SELECT 1 FROM financial_assets a JOIN price_history p "
                "ON p.asset_id=a.id WHERE a.is_cash=0 AND a.currency=?)", (current,)
            ):
                raise ValueError(
                    "The profile currency cannot change while noncash assets in the current currency have prices."
                )
            self.db.execute(
                "UPDATE financial_assets SET currency=?,updated_at=? "
                "WHERE is_cash=0 AND currency=?",
                (code, now_iso(), current),
            )
            SettingsStore(self.db).set("base_currency", code)
