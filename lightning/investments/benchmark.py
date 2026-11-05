"""Return against the risk-free rate (NF-9E).

The owner types a dated history of one yearly rate (a T-bill or bank certificate yield). A rate holds until a later one
is typed, so a rate nobody edited carries forward. The benchmark answers one question with cash flows alone: if the same
money had gone in and out on the same dates but earned that rate, what would it be worth today, and what yearly rate
is that? Years count as in XIRR (365 days, yearly compounding), so the two yearly figures compare directly. Nothing here
touches the ledger; the figures are read-only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from lightning.core.dates import parse_date

from .xirr import solve_xirr

SETTING_KEY = "investment_risk_free_rates"
ZERO = Decimal("0")
MAX_RATE_PERCENT = Decimal("1000")


@dataclass(frozen=True)
class Benchmark:
    value: Decimal               # what the same flows would be worth on the day at the risk-free rate
    gap: Decimal                 # the holding's value minus that
    rate: Decimal | None         # the yearly rate that benchmark earned; None when the solver cannot say
    latest_rate: Decimal         # the rate in force on the day, as a fraction
    latest_since: date           # the date that rate was typed for


def parse_history(raw: str | None) -> list[tuple[date, Decimal]]:
    """The stored history, oldest first. A damaged or empty value is an empty history, never an error."""
    try:
        rows = json.loads(raw) if raw else []
        history = {parse_date(day): Decimal(str(percent)) / 100 for day, percent in rows}
    except (TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
        return []
    return sorted(history.items())


def dump_history(history: list[tuple[date, Decimal]]) -> str:
    return json.dumps([[day.isoformat(), format((rate * 100).normalize(), "f")] for day, rate in sorted(history)],
                      separators=(",", ":"))


def set_rate(raw: str | None, day: str, percent: str) -> str:
    """The stored history with one dated rate added or replaced. The percent is a yearly rate such as 27.5."""
    when = parse_date(day)
    try:
        rate = Decimal(percent.strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError("Type the yearly rate as a number, for example 27.5.") from None
    if not rate.is_finite() or rate < 0 or rate > MAX_RATE_PERCENT:
        raise ValueError("The yearly rate must be between 0 and 1000 percent.")
    history = dict(parse_history(raw))
    history[when] = rate / 100
    return dump_history(list(history.items()))


def remove_rate(raw: str | None, day: str) -> str:
    when = parse_date(day)
    return dump_history([(d, r) for d, r in parse_history(raw) if d != when])


def rate_on(history: list[tuple[date, Decimal]], day: date) -> tuple[date, Decimal] | None:
    """The newest typed rate on or before the day, or None when the history starts later."""
    found = None
    for when, rate in history:
        if when > day:
            break
        found = (when, rate)
    return found


def _grow(balance: Decimal, rate: Decimal, days: int) -> Decimal:
    if not days or not balance:
        return balance
    return balance * ((Decimal(1) + rate).ln() * Decimal(days) / Decimal(365)).exp()


def benchmark(flows: list[tuple[str, Decimal]], value: Decimal | None, on: str,
              history: list[tuple[date, Decimal]]) -> Benchmark | None:
    """Compare a holding's dated flows (money in negative, money out positive, as XIRR reads them) with the history.

    None when there is nothing to compare: no flows, no value today, or a flow older than the first typed rate (the
    app will not guess a rate for a period nobody typed one for)."""
    end = parse_date(on)
    if value is None or not flows or not history:
        return None
    dated = sorted((parse_date(day), amount) for day, amount in flows if parse_date(day) <= end)
    if not dated or rate_on(history, dated[0][0]) is None:
        return None
    stops = sorted({day for day, _ in dated} | {d for d, _ in history if dated[0][0] < d <= end})
    by_day: dict[date, Decimal] = {}
    for day, amount in dated:
        by_day[day] = by_day.get(day, ZERO) - amount  # money in adds to the benchmark balance
    balance, here = ZERO, stops[0]
    for stop in stops:
        balance = _grow(balance, rate_on(history, here)[1], (stop - here).days) + by_day.get(stop, ZERO)
        here = stop
    balance = _grow(balance, rate_on(history, here)[1], (end - here).days)
    since, latest = rate_on(history, end)
    solved = solve_xirr([(day.isoformat(), amount) for day, amount in dated] + [(on, balance)], on)
    return Benchmark(balance, value - balance, solved.rate, latest, since)
