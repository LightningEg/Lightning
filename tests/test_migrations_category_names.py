"""IV-3BH6: upgrading default labels must preserve people's own category data."""
from __future__ import annotations

import shutil

import pytest

from lightning.database import migrator
from lightning.database.connection import Database
from lightning.database.seed import CATEGORIES, seed
from lightning.ui.i18n import translate


OLD_NAMES = {
    "INC.UNACCOUNTED": "Unaccounted Money Found",
    "EXP.PERSONAL.FOOD": "Food & Groceries",
    "EXP.PERSONAL.DINING": "Eating Out",
    "EXP.PERSONAL.HOUSING": "Housing & Rent",
    "EXP.PERSONAL.UTILITIES": "Utilities & Bills",
    "EXP.PERSONAL.GIFTS": "Gifts & Donations",
    "EXP.PERSONAL.GIFTS_RECEIVED": "Gifts Received",
    "EXP.PERSONAL.OTHER_INCOME": "Other Income",
    "EXP.PERSONAL.OTHER": "Other Personal",
    "EXP.PERSONAL.FEES": "Fees & Charges",
    "EXP.WORK.BUSINESS": "Business & Freelance",
    "EXP.WORK.OFFICE": "Office Supplies",
    "EXP.WORK.OTHER": "Other Work",
    "EXP.SYSTEM": "System Categories",
    "EXP.SYSTEM.CUSTODY": "Money Held for Others",
    "EXP.UNACCOUNTED": "Unaccounted Spending",
    "EXP.INVEST.FEES": "Investment Fees",
    "EXP.INVEST.OTHER": "Other Investment",
}


@pytest.mark.parametrize("encrypted", [False, True])
def test_upgrade_renames_only_exact_defaults(monkeypatch, tmp_path, encrypted):
    if encrypted:
        pytest.importorskip("sqlcipher3")
    old = tmp_path / "migrations_82"
    old.mkdir()
    for path in migrator.MIGRATIONS_DIR.glob("*.sql"):
        if int(path.name[:4]) <= 82:
            shutil.copy(path, old / path.name)
    bundled = migrator.MIGRATIONS_DIR
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", old)
    db = Database(tmp_path / "old.db", key=bytes(range(32)) if encrypted else None)
    try:
        migrator.migrate(db)
        # Recreate the pre-upgrade seed, independently of today's seed labels.
        with monkeypatch.context() as patch:
            patch.setattr("lightning.database.seed.CATEGORIES", [
                (code, OLD_NAMES.get(code, name), extra) for code, name, extra in CATEGORIES
            ])
            seed(db)
        db.execute("UPDATE categories SET name='My groceries' WHERE code='EXP.PERSONAL.FOOD'")
        db.execute("UPDATE categories SET name='EATING OUT' WHERE code='EXP.PERSONAL.DINING'")
        db.execute("UPDATE categories SET code='MY.OFFICE' WHERE code='EXP.WORK.OFFICE'")
        db.execute("DELETE FROM categories WHERE code='EXP.INVEST.OTHER'")
        # An archived untouched default still gets the corrected label.
        db.execute("UPDATE categories SET active=0 WHERE code='EXP.WORK.OTHER'")
        before = {r["id"]: dict(r) for r in db.all("SELECT * FROM categories")}
        monkeypatch.setattr(migrator, "MIGRATIONS_DIR", bundled)

        assert migrator.migrate(db) == ["0083_category_sentence_case (APPLIED)"]
        seed(db)
        after = {r["id"]: dict(r) for r in db.all("SELECT * FROM categories")}
        expected = {key: dict(row) for key, row in before.items()}
        for row in expected.values():
            if row["code"] in OLD_NAMES and row["name"] == OLD_NAMES[row["code"]]:
                row["name"] = row["name"].capitalize()
        assert after == expected  # IDs, hierarchy, flags, order and timestamps stay intact.
        assert migrator.migrate(db) == []
        assert {r["id"]: dict(r) for r in db.all("SELECT * FROM categories")} == after
    finally:
        db.close()


def test_fresh_profile_uses_sentence_case_with_existing_arabic(c):
    for code, name, _ in CATEGORIES:
        assert c.categories.get_by_code(code).name == name == name.capitalize()
        if code in OLD_NAMES:
            assert translate(name, "ar") == translate(OLD_NAMES[code], "ar") != name
    assert c.categories.get_by_code("EXP.PERSONAL.DINING").name == "Eating out"
    assert translate("Eating out", "ar") == "المطاعم"


def test_old_category_text_still_resolves_for_saved_imports(c):
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    assert c.categories.find_by_text("Food & Groceries").id == food.id
    assert c.categories.find_by_text("Personal › Food & Groceries").id == food.id
    assert c.categories.display_name(food.id) == "Personal › Food & groceries"
