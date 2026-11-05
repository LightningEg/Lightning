"""Dated whole-asset estimates for accounts such as a home or land share."""
from __future__ import annotations

from lightning.accounts.domain import AccountType
from lightning.core.dates import now_iso, parse_date
from lightning.core.errors import ValidationError
from lightning.core.money import check_places, from_e6, to_decimal, to_e6
from lightning.database.connection import Database


class OtherAssetValuationRepository:
    def __init__(self, db: Database):
        self.db = db

    def latest(self, account_id: int, as_of: str) -> dict | None:
        row = self.db.one(
            "SELECT effective_date,value_e6,notes FROM other_asset_valuations "
            "WHERE account_id=? AND effective_date<=? ORDER BY effective_date DESC LIMIT 1",
            (account_id, as_of))
        if not row:
            return None
        return {**row, "value": from_e6(row["value_e6"])}

    def save(self, account, effective_date: str, amount, notes: str = "") -> dict:
        if account.account_type != AccountType.OTHER_ASSET:
            raise ValidationError("Choose an Other asset account.", "account")
        day = parse_date(effective_date, "date")
        from lightning.core.dates import today
        if day > today():
            raise ValidationError("A value date cannot be in the future.", "date")
        value = check_places(to_decimal(amount, "value"), 2, "value")
        if value < 0:
            raise ValidationError("Enter a value of zero or more.", "value")
        self.db.execute(
            "INSERT INTO other_asset_valuations(account_id,effective_date,value_e6,notes,updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(account_id,effective_date) DO UPDATE SET "
            "value_e6=excluded.value_e6,notes=excluded.notes,updated_at=excluded.updated_at",
            (account.id, day.isoformat(), to_e6(value), (notes or "").strip(), now_iso()))
        return self.latest(account.id, day.isoformat())


ASSET_KINDS = ("flat", "house", "land", "car", "other")


class OtherAssetDetailsRepository:
    """Kind, purchase and loan of an Other asset account (NF-9C). The dated values are the repository above."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, account_id: int) -> dict | None:
        row = self.db.one("SELECT kind,purchase_date,purchase_price_e6,loan_item_id FROM other_asset_details "
                          "WHERE account_id=?", (account_id,))
        if not row:
            return None
        price = from_e6(row["purchase_price_e6"]) if row["purchase_price_e6"] is not None else None
        return {"kind": row["kind"], "purchase_date": row["purchase_date"], "purchase_price": price,
                "loan_item_id": row["loan_item_id"]}

    def history(self, account_id: int) -> list[dict]:
        """Every dated value you entered, oldest first."""
        return [{**row, "value": from_e6(row["value_e6"])} for row in self.db.all(
            "SELECT effective_date,value_e6,notes FROM other_asset_valuations WHERE account_id=? "
            "ORDER BY effective_date", (account_id,))]

    def save(self, account, kind: str, purchase_date, purchase_price, loan_item_id) -> dict:
        if account.account_type != AccountType.OTHER_ASSET:
            raise ValidationError("Choose an Other asset account.", "account")
        kind = (kind or "other").strip().lower()
        if kind not in ASSET_KINDS:
            raise ValidationError("Choose flat, house, land, car or other.", "kind")
        day = None
        if str(purchase_date or "").strip():
            from lightning.core.dates import today
            when = parse_date(purchase_date, "purchase_date")
            if when > today():
                raise ValidationError("A purchase date cannot be in the future.", "purchase_date")
            day = when.isoformat()
        price = None
        if str(purchase_price or "").strip():
            price = check_places(to_decimal(purchase_price, "purchase_price"), 2, "purchase_price")
            if price < 0:
                raise ValidationError("Enter a price of zero or more.", "purchase_price")
        loan = None
        if str(loan_item_id or "").strip():
            loan = int(loan_item_id)
            found = self.db.one("SELECT kind FROM planned_items WHERE id=?", (loan,))
            if not found or found["kind"] != "LOAN":
                raise ValidationError("Choose one of your loans.", "loan_item_id")
        self.db.execute(
            "INSERT INTO other_asset_details(account_id,kind,purchase_date,purchase_price_e6,loan_item_id,updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET kind=excluded.kind, "
            "purchase_date=excluded.purchase_date, purchase_price_e6=excluded.purchase_price_e6, "
            "loan_item_id=excluded.loan_item_id, updated_at=excluded.updated_at",
            (account.id, kind, day, to_e6(price) if price is not None else None, loan, now_iso()))
        return self.get(account.id)
