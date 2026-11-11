"""A purchase in another currency on a pound account (NF-7AK3).

Owner, 2026-11-11: "you always have currency, then amount in currency, then equivalent in default currency." The
ledger keeps pounds, since cash sits only in an account of its own currency. This module keeps what was paid in the
shop's currency beside the entry. Until the bank's pound debit arrives, the entry holds the pound equivalent at the
dated rate (`lightning.fx.rate_for`). When the debit comes, through SMS or a statement, the review offers it as that
entry. Linking it sets the entry to the debit's amount and marks the row settled, so the purchase stays one expense.
This is the only module that writes `foreign_amounts` (migration 0079).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from lightning.core.dates import now_iso
from lightning.core.money import from_e6, to_e6
from lightning.fx import rate_for

PROFILE_CURRENCY = "EGP"
# The bank's pound debit comes days after the purchase, at its own rate plus its foreign-card fee. The review offers
# an open purchase as that debit's entry only within these bounds; the person still confirms the link.
SETTLE_DAYS = 30
SETTLE_SHARE = Decimal("0.15")
_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class ForeignAmount:
    transaction_id: int
    currency: str
    amount: Decimal
    settled: bool

    @property
    def label(self) -> str:
        return f"{self.currency} {self.amount:,.2f}"


def pounds(db, currency: str, amount: Decimal, day: str) -> tuple[Decimal, Decimal] | None:
    """(pound equivalent rounded to piastres, rate) at the rate dated `day`, or None when no rate is near enough."""
    rate = rate_for(db, currency, PROFILE_CURRENCY, day)
    if rate is None:
        return None
    return (amount * rate.rate).quantize(_CENTS, ROUND_HALF_UP), rate.rate


class ForeignAmounts:
    def __init__(self, db):
        self.db = db

    def record(self, transaction_id: int, currency: str, amount: Decimal) -> None:
        stamp = now_iso()
        self.db.execute(
            "INSERT INTO foreign_amounts(transaction_id,currency,amount_e6,settled,created_at,updated_at) "
            "VALUES (?,?,?,0,?,?) ON CONFLICT(transaction_id) DO UPDATE SET currency=excluded.currency, "
            "amount_e6=excluded.amount_e6, settled=0, updated_at=excluded.updated_at",
            (int(transaction_id), currency.upper(), to_e6(Decimal(amount)), stamp, stamp))

    def settle(self, transaction_id: int) -> None:
        self.db.execute("UPDATE foreign_amounts SET settled=1, updated_at=? WHERE transaction_id=?",
                        (now_iso(), int(transaction_id)))

    def get(self, transaction_id: int) -> ForeignAmount | None:
        row = self.db.one("SELECT * FROM foreign_amounts WHERE transaction_id=?", (int(transaction_id),))
        return _row(row) if row else None

    def open_near(self, account_id: int, day: str, amount: Decimal) -> list[dict]:
        """Unsettled purchases on this account that a pound debit of `amount` (negative) on `day` may settle: dated at
        most SETTLE_DAYS before it, their pound equivalent within SETTLE_SHARE of it. Nearest amount first."""
        if amount >= 0:
            return []
        rows = self.db.all(
            "SELECT f.*, t.date, SUM(l.amount_e6) AS pounds_e6 FROM foreign_amounts f "
            "JOIN transactions t ON t.id=f.transaction_id AND t.status='POSTED' "
            "JOIN ledger_entries l ON l.transaction_id=t.id AND l.account_id=? "
            "AND l.asset_id IN (SELECT id FROM financial_assets WHERE is_cash=1) "
            "WHERE f.settled=0 AND julianday(t.date) BETWEEN julianday(?)-? AND julianday(?) "
            "GROUP BY f.transaction_id", (int(account_id), day, SETTLE_DAYS, day))
        found = []
        for row in rows:
            held = from_e6(row["pounds_e6"])
            if held < 0 and abs(held - amount) <= abs(held) * SETTLE_SHARE:
                found.append({"id": row["transaction_id"], "date": row["date"], "estimate": -held,
                              "settles": _row(row).label})
        return sorted(found, key=lambda f: (abs(f["estimate"] + amount), f["date"]))


def _row(row) -> ForeignAmount:
    return ForeignAmount(row["transaction_id"], row["currency"], from_e6(row["amount_e6"]), bool(row["settled"]))
