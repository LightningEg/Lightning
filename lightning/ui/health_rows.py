"""A health figure as a row: its meter and what its limit says. Shared by the Financial health page and the phone's
presenter (3AY11)."""
from __future__ import annotations

from decimal import Decimal


def meter(item) -> dict | None:
    """The figure on a track that reaches a little past the larger of the figure and its limit; the
    limit is a tick. Percentages use 0–100% unless a figure or limit goes past it."""
    if item.value is None or item.gap:
        return None
    value = max(Decimal(item.value), Decimal(0))
    limit = Decimal(item.limit) if item.limit is not None else None
    if item.unit == "%":
        top = max(Decimal(100), value * Decimal("1.1"), (limit or 0) * Decimal("1.1"))
    else:
        top = max((limit or 0) * Decimal("1.25"), value * Decimal("1.1"), Decimal(1))
    alert = Decimal(item.alert) if item.alert is not None else None
    return {"fill": float(min(value / top * 100, Decimal(100))),
            "tick": float(limit / top * 100) if limit is not None else None,
            "ticks": [float(min(bound / top * 100, Decimal(100))) for bound in (limit, alert) if bound is not None],
            "tone": {"out": "spend"}.get(tone_of(item), tone_of(item))}  # the chart tone names (style.css)


def limit_words(item) -> str:
    if item.limit is None:
        return "No limit set"
    side = "at least" if item.direction == "minimum" else "at most"
    amount = f"{item.limit:.1f}%" if item.unit == "%" else f"{item.limit:.0f} months"
    if item.band == "alert" and item.alert is not None:
        past = f"{item.alert:.1f}%" if item.unit == "%" else f"{item.alert:.0f} months"
        return f"{'Below' if item.direction == 'minimum' else 'Above'} {past}: needs you"
    if item.band == "watch":
        return f"Good is {side} {amount}"
    if item.band == "good":
        return f"Good: {side} {amount}"
    return f"Good is {side} {amount}"


def tone_of(item) -> str:
    return "over" if item.band == "alert" else _TONE.get(item.key, "hold")


# What each figure's colour means when it is inside its limit (guideline A03, A08): a cushion is money you
# hold, a savings rate is money kept, debt and fixed costs are money out. Outside its limit it needs you.
_TONE = {"emergency_fund": "hold", "net_worth": "hold", "savings_rate": "in", "planned_savings_rate": "in",
         "investing_rate": "in", "debt_to_cash": "out", "debt_to_net_worth": "out", "fixed_costs_to_income": "out",
         "loan_payments_to_income": "out"}
