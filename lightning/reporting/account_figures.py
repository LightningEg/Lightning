"""The figures an account page shows beside its register (IT-12AE4): its value with its broker pockets added in, what is
in it by asset class, a foreign account in its own currency, a pocket's investments, an Other asset's change and
equity, and the net of the rows a search found. The page only reads these; it works none of them out."""
from __future__ import annotations

from decimal import Decimal

from lightning.core.money import ZERO


def combined_value(reporting, account_ids, as_of) -> tuple[Decimal, Decimal, Decimal]:
    """Value, what you own and what is held for others of several accounts together (a broker and its pockets)."""
    value = sum((reporting.account_value(account_id, as_of) for account_id in account_ids), ZERO)
    owned = sum((reporting.owned_account_value(account_id, as_of) for account_id in account_ids), ZERO)
    return value, owned, value - owned


def class_mix(breakdown: list[dict], shown: int = 4) -> dict:
    """An account's asset classes worth more than nothing, their total, and Other: what the classes after the first
    `shown` add up to (None when there are none)."""
    parts = [row for row in breakdown if row["total"] > 0]
    rest = parts[shown:]
    return {"parts": parts, "total": sum((row["total"] for row in parts), ZERO),
            "other": sum((row["total"] for row in rest), ZERO) if rest else None}


def share_of(amount: Decimal, total: Decimal) -> Decimal:
    """One amount as a percentage of a total (unrounded)."""
    return amount / total * 100


def in_own_currency(value: Decimal | None, rate) -> Decimal | None:
    """A profile-currency value back in an account's own currency at a rate (None without a rate)."""
    return value / rate.rate if rate and rate.rate else None


def pocket_invested(value: Decimal, rate: Decimal | None, cash: Decimal) -> Decimal | None:
    """What a broker pocket holds in investments, in its own currency: its value at the rate, less its cash."""
    return (value / rate - cash) if rate else None


def search_net(flows: tuple[Decimal, Decimal] | None) -> Decimal | None:
    """Money in less money out of the rows a search found."""
    return flows[0] - flows[1] if flows else None


def other_asset_figures(value: Decimal, price: Decimal | None, history: list[dict]) -> dict:
    """An Other asset's change since it was bought (and as a percentage of the price), and each dated value's change
    from the one before it."""
    change = value - price if price is not None else None
    return {"change": change,
            "change_pct": change / price * 100 if change is not None and price else None,
            "history_changes": [row["value"] - history[i - 1]["value"] if i else None for i, row in enumerate(history)]}


def equity(value: Decimal, left: Decimal) -> Decimal:
    """An asset's value less what is left to pay on the loan that bought it (one currency only)."""
    return value - left
