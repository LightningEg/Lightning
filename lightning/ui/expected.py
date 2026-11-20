"""Expected by payday, as every screen shows it (owner, 2026-11-18): the figure, the payday date, how payday was
chosen, and each expected income with its amount and date. One presenter, so Home, Cash planning, the payday page
and the phone say the same thing. It only reads the forecast; nothing is worked out here."""
from __future__ import annotations

from decimal import Decimal

from lightning.core.figures import label

# How payday was chosen (CashForecast.payday_source) in the words a screen shows.
SOURCES = {
    "salary": "your salary",
    "highest recurring income": "your highest recurring income",
    "scheduled income": "your next scheduled income",
    "estimated": "an estimate from your average income",
}


def expected_by_payday(f) -> dict | None:
    """The secondary line under Safe to spend today. None when there is no payday to expect anything by."""
    if not f.next_income_date:
        return None
    return {"label": label("expected_by_payday"), "value": f.expected_by_payday, "date": f.next_income_date,
            "source": SOURCES.get(f.payday_source, SOURCES["estimated"]),
            "incomes": [{"name": i.name, "date": i.date, "amount": i.amount} for i in f.income_before_payday_items],
            "extra": f.income_before_payday if f.income_before_payday != Decimal(0) else None}
