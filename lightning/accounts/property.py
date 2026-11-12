"""Property as an investment (NF-12M): a flat, a house or land kept as an Other account.

Its value is the dated estimate (``valuations.py``); this module says which accounts are property and what they cost.
- Class: an Other account whose kind is flat, house or land is Real estate, not Other Investments (12M1).
- Cost: the purchase price, from the purchase date on (12M1); bought by instalments, what you paid so far (12M3).
  Gain = value less cost.
- Return: gain + rent - running costs (12M4).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from lightning.core.dates import fmt_date, now_iso, parse_date, today
from lightning.core.errors import ValidationError
from lightning.core.money import ZERO, check_places, from_e6, to_decimal
from lightning.database.connection import Database

PROPERTY_KINDS = ("flat", "house", "land")
REAL_ESTATE_CLASS = "REAL_ESTATE"
CONTRACT_FREQUENCIES = ("MONTHLY", "QUARTERLY", "YEARLY")
RENT_CATEGORY, COST_CATEGORY = "EXP.INVEST.RENT", "EXP.INVEST.PROPERTY"


def is_property(details: dict | None) -> bool:
    """True when an Other account's details say it is a flat, a house or land."""
    return bool(details) and details.get("kind") in PROPERTY_KINDS


def property_cost(details: dict | None, day: str, paid: Decimal | None = None) -> Decimal | None:
    """What you paid for a property by ``day``, in the account's currency; None when no price is recorded (then
    it is valued by you only, with no gain) or the purchase is after ``day``. Bought by instalments (a contract),
    it is ``paid``: what has moved into the account so far, as you own only what you paid (owner, 2026-11-09)."""
    if details and details.get("contract") and paid is not None:
        return paid
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
        """account id -> {kind, purchase_date, purchase_price, contract (bought by instalments)}."""
        return {row["account_id"]: {
            "kind": row["kind"], "purchase_date": row["purchase_date"],
            "purchase_price": from_e6(row["purchase_price_e6"]) if row["purchase_price_e6"] is not None else None,
            "contract": bool(row["contract"])}
            for row in self.db.all("SELECT d.account_id,d.kind,d.purchase_date,d.purchase_price_e6,"
                                   "pc.planned_item_id AS contract FROM other_asset_details d "
                                   "LEFT JOIN property_contracts pc ON pc.account_id=d.account_id")}


def property_return(value: Decimal, cost: Decimal | None, year: dict, since: dict) -> dict:
    """A property's return (12M4), like a stock's: gain = value - cost; net income = rent - costs; yield = the last
    twelve months' net income over the value now; total return = gain + net income since you bought it, also as a
    share of the cost. ``year`` and ``since`` are PropertyService.flows over those periods."""
    gain = value - cost if cost is not None else None
    total = gain + since["net"] if gain is not None else None
    return {"gain": gain, "yield_pct": year["net"] / value * 100 if value else None,
            "total": total, "total_pct": total / cost * 100 if total is not None and cost else None}


class PropertyService:
    """Instalments to the developer (12M3), rent and running costs (12M4) of a property account.

    - Contract: the purchase price on the account's details is the contract price; the schedule is a planned bill
      (no category, so nothing is matched to it by itself) paying from your bank. An instalment is a transfer from
      that bank into the property: it raises what you paid, and the cost with it. The part not yet paid is not a
      debt: only a payment already due counts in Bills due, as any bill does; the rest is in the forecast.
    - Rent and costs: a money in or money out recorded from the property's page, linked to it in
      ``property_flows``. Its return = gain + rent - costs.
    """

    def __init__(self, db: Database, accounts, transactions, planning, categories):
        self.db, self.accounts, self.transactions = db, accounts, transactions
        self.planning, self.categories = planning, categories

    # -------------------------------------------------------------- reading
    def _property(self, account_id) -> tuple[object, dict]:
        account = self.accounts.get(int(account_id))
        details = PropertyBook(self.db).details().get(account.id)
        if account.account_type.value != "OTHER_ASSET" or not is_property(details):
            raise ValidationError("Choose a flat, a house or land.", "account")
        return account, details

    def contract_item(self, account_id: int) -> int | None:
        """The planned bill that schedules a property's instalments, if any."""
        return self.db.scalar("SELECT planned_item_id FROM property_contracts WHERE account_id=?", (account_id,))

    def contract(self, account_id: int, paid: Decimal, as_of: date | None = None) -> dict | None:
        """Where a contract stands: price, paid (``paid``: what moved into the account), left, the next payment and
        the counts. None without a contract."""
        item_id = self.contract_item(account_id)
        if item_id is None:
            return None
        details = PropertyBook(self.db).details().get(account_id) or {}
        price = details.get("purchase_price") or ZERO
        item = self.planning.get(item_id)
        payments = self.planning.payments(item, "2999-12-31", as_of)
        open_ = [p for p in payments if p.outstanding]
        return {"item": item, "price": price, "paid": paid, "left": max(price - paid, ZERO),
                "next": open_[0] if open_ else None, "due": [p for p in open_ if p.due_date <= fmt_date(as_of or today())],
                "count": len(payments), "done": len(payments) - len(open_), "remaining": open_}

    # -------------------------------------------------------------- the contract
    def save_contract(self, account_id: int, instalment, frequency: str, first_date, payment_count,
                      funding_account_id) -> int:
        """Schedule the instalments still to pay (a new schedule or a changed one). Returns the planned item's id."""
        account, details = self._property(account_id)
        if details.get("purchase_price") is None:
            raise ValidationError("Type the contract price under purchase details first.", "purchase_price")
        frequency = str(frequency or "MONTHLY").upper()
        if frequency not in CONTRACT_FREQUENCIES:
            raise ValidationError("Choose monthly, quarterly or yearly.", "frequency")
        values = dict(kind="BILL", name=f"{account.name} instalments", amount=instalment, frequency=frequency,
                      start_date=first_date, payment_count=payment_count, account_id=funding_account_id,
                      notes="Instalments to the developer")
        with self.db.transaction():
            item_id = self.contract_item(account.id)
            if item_id is None:
                item_id = self.planning.create(**values)
                self.db.execute("INSERT INTO property_contracts(account_id,planned_item_id,created_at,updated_at) "
                                "VALUES(?,?,?,?)", (account.id, item_id, now_iso(), now_iso()))
            else:
                self.planning.update(item_id, **values)
                self.db.execute("UPDATE property_contracts SET updated_at=? WHERE account_id=?", (now_iso(), account.id))
        return item_id

    def pay_instalment(self, account_id: int, due_date: str, date_paid, amount, from_account_id=None) -> int:
        """Move one scheduled instalment from your bank into the property and mark it paid. Returns the transfer."""
        account, _ = self._property(account_id)
        item_id = self.contract_item(account.id)
        if item_id is None:
            raise ValidationError("Set up the instalments first.", "due_date")
        item = self.planning.get(item_id)
        due = fmt_date(parse_date(due_date, "due_date"))
        scheduled = next((p for p in self.planning.payments(item, "2999-12-31") if p.due_date == due), None)
        if scheduled is None:
            raise ValidationError("That date is not on this payment schedule.", "due_date")
        value = check_places(to_decimal(amount if str(amount or "").strip() else scheduled.amount, "amount"), 2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter the amount paid.", "amount")
        source = int(from_account_id) if str(from_account_id or "").strip() else item.account_id
        if not source:
            raise ValidationError("Choose the account the money left from.", "from_account_id")
        with self.db.transaction():
            if self.planning.repo.is_settled(item_id, due):
                raise ValidationError(f"The instalment of {due} is already paid.", "due_date")
            txn = self.transactions.record_transfer(fmt_date(parse_date(date_paid or today(), "date")), source,
                                                    account.id, value, description=f"Instalment · {account.name}",
                                                    into_property=True)
            self.planning.repo.settle(item_id, due, "PAID", txn.id, value)
        return txn.id

    # -------------------------------------------------------------- rent and costs
    def record_flow(self, account_id: int, kind: str, date_value, amount, cash_account_id, notes: str = "") -> int:
        """Rent received into, or a running cost paid from, a cash account, named as this property's. Returns it."""
        account, _ = self._property(account_id)
        if kind not in ("rent", "cost"):
            raise ValidationError("Choose rent or a cost.", "kind")
        category = self.categories.get_by_code(RENT_CATEGORY if kind == "rent" else COST_CATEGORY)
        record = self.transactions.record_inflow if kind == "rent" else self.transactions.record_outflow
        with self.db.transaction():
            txn = record(fmt_date(parse_date(date_value or today(), "date")), int(cash_account_id), amount, category.id,
                         description=f"{'Rent' if kind == 'rent' else 'Cost'} · {account.name}", notes=notes or "",
                         allow_system_category=True)
            self.db.execute("INSERT INTO property_flows(transaction_id,account_id,created_at) VALUES(?,?,?)",
                            (txn.id, account.id, now_iso()))
        return txn.id

    def flows(self, account_id: int, start: str, end: str) -> dict:
        """Rent and costs of a property between two dates, in the profile currency: {rent, costs, net, rows}."""
        rows = [dict(r) for r in self.db.all(
            "SELECT t.id,t.date,t.description,t.type,SUM(le.amount_base_e6) AS amount_e6 FROM property_flows f "
            "JOIN transactions t ON t.id=f.transaction_id JOIN ledger_entries le ON le.transaction_id=t.id "
            "WHERE f.account_id=? AND t.status='POSTED' AND t.date BETWEEN ? AND ? AND le.category_id IS NOT NULL "
            "GROUP BY t.id ORDER BY t.date DESC,t.id DESC", (account_id, start, end))]
        for row in rows:
            row["amount"] = from_e6(row["amount_e6"])
        rent = sum((r["amount"] for r in rows if r["amount"] > ZERO), ZERO)
        costs = -sum((r["amount"] for r in rows if r["amount"] < ZERO), ZERO)
        return {"rent": rent, "costs": costs, "net": rent - costs, "rows": rows}
