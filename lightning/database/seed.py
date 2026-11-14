"""Starter data: asset-class tree, cash assets, and the initial category tree.

Categories are seeded once; later built-in category additions belong in migrations so
user-renamed or deleted categories are not recreated on each application start.
"""

from __future__ import annotations

from lightning.core.dates import now_iso

from .connection import Database
from .settings import DEFAULTS, SettingsStore

CATEGORY_SEED_VERSION = "1"

# (code, name) — parent is derived from the dotted path
ASSET_CLASSES: list[tuple[str, str]] = [
    ("CASH", "Liquid Cash"),
    ("CASH.PHYSICAL", "Physical Cash"),
    ("CASH.BANK", "Bank Balance"),
    ("CASH.BROKERAGE", "Brokerage Cash"),
    ("DEPOSIT", "Deposits"),
    ("DEPOSIT.CD", "CDs / Time Deposits"),
    ("GAMEYA", "Gam'eya paid in"),
    ("RECEIVABLE", "Owed to you"),
    ("STOCK", "Stocks"),
    ("FUND", "Funds"),
    ("FUND.EQUITY", "Equity Fund"),
    ("FUND.MONEY_MARKET", "Money Market Fund"),
    ("FUND.FIXED_INCOME", "Fixed Income Fund"),
    ("FUND.GOLD", "Gold Fund"),
    ("FUND.CLOUD", "Cloud"),
    ("FUND.OTHER", "Other Fund"),
    ("GOLD", "Gold"),
    ("SILVER", "Silver"),
    ("REAL_ESTATE", "Real estate"),
    ("OTHER", "Other Investments"),
]

# (code, name, unit) — one cash asset per currency
CASH_ASSETS: list[tuple[str, str]] = [
    ("EGP", "Egyptian Pound"),
    ("USD", "US Dollar"),
    ("EUR", "Euro"),
    ("GBP", "British Pound"),
    ("SAR", "Saudi Riyal"),
    ("AED", "UAE Dirham"),
]

# (code, name, extra) — activity family and reimbursement rules inherit from the parent
CATEGORIES: list[tuple[str, str, dict]] = [
    ("INC", "Income (legacy root)", {"movement": "INFLOW", "income_class": "HOUSEHOLD", "is_system": 1}),
    ("INC.UNACCOUNTED", "Unaccounted money found", {"is_system": 1}),
    ("EXP", "Activities", {"movement": "OUTFLOW"}),
    ("EXP.PERSONAL", "Personal", {"scope": "PERSONAL", "family": "PERSONAL"}),
    ("EXP.PERSONAL.FOOD", "Food & groceries", {}),
    ("EXP.PERSONAL.DINING", "Eating out", {}),
    ("EXP.PERSONAL.TRANSPORT", "Transportation", {}),
    ("EXP.PERSONAL.HOUSING", "Housing & rent", {}),
    ("EXP.PERSONAL.UTILITIES", "Utilities & bills", {}),
    ("EXP.PERSONAL.HEALTH", "Health", {}),
    ("EXP.PERSONAL.SHOPPING", "Shopping", {}),
    ("EXP.PERSONAL.ENTERTAINMENT", "Entertainment", {}),
    ("EXP.PERSONAL.EDUCATION", "Education", {}),
    ("EXP.PERSONAL.GIFTS", "Gifts & donations", {}),
    ("EXP.PERSONAL.GIFTS_RECEIVED", "Gifts received", {"movement": "INFLOW", "income_class": "HOUSEHOLD"}),
    ("EXP.PERSONAL.OTHER_INCOME", "Other income", {"movement": "INFLOW", "income_class": "HOUSEHOLD"}),
    ("EXP.PERSONAL.OTHER", "Other personal", {}),
    ("EXP.PERSONAL.FEES", "Fees & charges", {"scope": "PERSONAL"}),
    ("EXP.PERSONAL.TAXES", "Taxes", {"scope": "PERSONAL"}),
    ("EXP.WORK", "Work", {"scope": "WORK", "family": "WORK", "default_reimbursable": 1}),
    ("EXP.WORK.SALARY", "Salary", {"movement": "INFLOW", "income_class": "HOUSEHOLD"}),
    ("EXP.WORK.BONUS", "Bonus", {"movement": "INFLOW", "income_class": "HOUSEHOLD"}),
    ("EXP.WORK.BUSINESS", "Business & freelance", {"movement": "INFLOW", "income_class": "HOUSEHOLD"}),
    ("EXP.WORK.TRANSPORT", "Transportation", {}),
    ("EXP.WORK.SOFTWARE", "Software", {}),
    ("EXP.WORK.MEALS", "Meals", {}),
    ("EXP.WORK.OFFICE", "Office supplies", {}),
    ("EXP.WORK.OTHER", "Other work", {}),
    ("EXP.SYSTEM", "System categories", {"scope": "PERSONAL", "family": "PERSONAL"}),
    ("EXP.SYSTEM.CUSTODY", "Money held for others", {"movement": "INFLOW", "family": "PERSONAL"}),
    ("EXP.SYSTEM.LOANS", "Loan payments", {"scope": "PERSONAL"}),
    ("EXP.SYSTEM.TRANSFERS", "Internal transfers", {"direction": "BOTH"}),
    ("EXP.SYSTEM.CAPITAL", "Capital allocation", {"direction": "BOTH"}),
    ("EXP.SYSTEM.ADJUSTMENT", "Adjustment", {"direction": "BOTH"}),
    ("EXP.SYSTEM.ZAKAT", "Zakat", {"scope": "PERSONAL"}),
    ("EXP.UNACCOUNTED", "Unaccounted spending", {"scope": "PERSONAL", "is_system": 1}),
    ("EXP.INVEST", "Investment", {"family": "INVESTMENT", "income_class": "INVESTMENT"}),
    ("EXP.INVEST.INTEREST", "Interest", {"movement": "INFLOW", "income_class": "INVESTMENT"}),
    ("EXP.INVEST.DIVIDEND", "Dividends", {"movement": "INFLOW", "income_class": "INVESTMENT"}),
    ("EXP.INVEST.FEES", "Investment fees", {}),
    ("EXP.INVEST.TAX", "Tax withheld", {}),
    ("EXP.INVEST.OTHER", "Other investment", {}),
    ("EXP.INVEST.RENT", "Rent received", {"movement": "INFLOW", "income_class": "INVESTMENT"}),
    ("EXP.INVEST.PROPERTY", "Property costs", {}),
]


def _parent_id(db: Database, table: str, code: str) -> int | None:
    if "." not in code:
        return None
    parent_code = code.rsplit(".", 1)[0]
    return db.scalar(f"SELECT id FROM {table} WHERE code = ?", (parent_code,))


def seed(db: Database) -> None:
    now = now_iso()
    with db.transaction():
        settings = SettingsStore(db)
        for key, value in DEFAULTS.items():
            if db.scalar("SELECT 1 FROM settings WHERE key = ?", (key,)) is None:
                settings.set(key, value)

        for order, (code, name) in enumerate(ASSET_CLASSES):
            if db.scalar("SELECT 1 FROM asset_classes WHERE code = ?", (code,)):
                continue
            db.execute(
                "INSERT INTO asset_classes(code, name, parent_id, sort_order, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?)",
                (code, name, _parent_id(db, "asset_classes", code), order, now, now),
            )

        cash_class = db.scalar("SELECT id FROM asset_classes WHERE code = 'CASH'")
        for currency, name in CASH_ASSETS:
            code = f"CASH:{currency}"
            if db.scalar("SELECT 1 FROM financial_assets WHERE code = ?", (code,)):
                continue
            db.execute(
                "INSERT INTO financial_assets(code, name, asset_class_id, currency, unit, quantity_decimals,"
                " is_cash, exposure, liquidity, price_source, created_at, updated_at)"
                " VALUES (?,?,?,?,?,2,1,'CASH','IMMEDIATE','NONE',?,?)",
                (code, name, cash_class, currency, currency, now, now),
            )

        gold_class = db.scalar("SELECT id FROM asset_classes WHERE code = 'GOLD'")
        # Shared price references for common jewelry purities.
        for karat in (18, 21, 24):
            # Keep 18K's established public code; make the 24K price series internal
            # so a user can still create an ordinary GLD:24K holding.
            code = "GLD:18K" if karat == 18 else f"REF:GLD-{karat}K"
            if db.scalar("SELECT 1 FROM financial_assets WHERE code = ?", (code,)):
                continue
            db.execute(
                "INSERT INTO financial_assets(code,name,asset_class_id,currency,unit,quantity_decimals,is_cash,"
                "exposure,liquidity,purity_e6,price_source,created_at,updated_at) "
                "VALUES(?,?,?,?,?,3,0,'GOLD','DAYS',?,'MANUAL',?,?)",
                (code, f"{karat}K gold price reference", gold_class, settings.base_currency, "gram",
                 karat * 1_000_000 // 24, now, now),
            )

        if settings.get("category_seed_version") != CATEGORY_SEED_VERSION:
            for order, (code, name, extra) in enumerate(CATEGORIES):
                if db.scalar("SELECT 1 FROM categories WHERE code = ?", (code,)):
                    continue
                parent_id = _parent_id(db, "categories", code)
                parent = (
                    db.one("SELECT * FROM categories WHERE id = ?", (parent_id,)) if parent_id else None
                )
                movement = extra.get("movement") or (parent["movement"] if parent else "OUTFLOW")
                scope = extra.get("scope", parent["scope"] if parent else None)
                income_class = extra.get("income_class", parent["income_class"] if parent else None)
                family = extra.get("family", parent["family"] if parent else None)
                reimb = extra.get(
                    "default_reimbursable", parent["default_reimbursable"] if parent else 0
                )
                db.execute(
                    "INSERT INTO categories(code, name, parent_id, movement, scope, income_class, family,"
                    " default_reimbursable, is_system, sort_order, direction, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        code,
                        name,
                        parent_id,
                        movement,
                        scope if movement == "OUTFLOW" else None,
                        income_class if movement == "INFLOW" else None,
                        family,
                        reimb,
                        extra.get("is_system", 0),
                        order,
                        extra.get("direction"),
                        now,
                        now,
                    ),
                )
            settings.set("category_seed_version", CATEGORY_SEED_VERSION)
