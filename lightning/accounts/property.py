"""Property as an investment (NF-12M): a flat, a house or land kept as an Other account.

Its value is the dated estimate (``valuations.py``); this module says which accounts are property and what they cost.
- Class: an Other account whose kind is flat, house or land is Real estate, not Other Investments (12M1).
- Cost: the purchase price, from the purchase date on (12M1). Gain = value less cost.
Nothing here is stored beyond the account's details; it is read from them.
"""
from __future__ import annotations

from decimal import Decimal

from lightning.core.money import from_e6
from lightning.database.connection import Database

PROPERTY_KINDS = ("flat", "house", "land")
REAL_ESTATE_CLASS = "REAL_ESTATE"


def is_property(details: dict | None) -> bool:
    """True when an Other account's details say it is a flat, a house or land."""
    return bool(details) and details.get("kind") in PROPERTY_KINDS


def property_cost(details: dict | None, day: str) -> Decimal | None:
    """What you paid for a property by ``day``, in the account's currency; None when no price is recorded (then
    it is valued by you only, with no gain) or the purchase is after ``day``."""
    if not details or details.get("purchase_price") is None:
        return None
    bought = details.get("purchase_date")
    if bought and bought > day:
        return None
    return details["purchase_price"]


class PropertyBook:
    """Read model: the details of every Other account at once, for the reports that walk every holding."""

    def __init__(self, db: Database):
        self.db = db

    def details(self) -> dict[int, dict]:
        """account id -> {kind, purchase_date, purchase_price}."""
        return {row["account_id"]: {
            "kind": row["kind"], "purchase_date": row["purchase_date"],
            "purchase_price": from_e6(row["purchase_price_e6"]) if row["purchase_price_e6"] is not None else None}
            for row in self.db.all("SELECT account_id,kind,purchase_date,purchase_price_e6 FROM other_asset_details")}
