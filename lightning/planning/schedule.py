"""Expand a planned item's schedule into dated payments (pure functions)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from .domain import Frequency, PlannedItem, WeekendMove

_MONTH_STEP = {Frequency.MONTHLY: 1, Frequency.QUARTERLY: 3, Frequency.YEARLY: 12}


def _add_months(anchor: date, months: int) -> date:
    """Same day of month, clamped to the month's last day (31 → 30/28/29)."""
    index = anchor.year * 12 + anchor.month - 1 + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(anchor.day, last))


WEEKEND = {4, 5}  # Friday and Saturday in date.weekday()


def on_working_day(day: date, move: WeekendMove) -> date:
    """Move a Friday or Saturday to Thursday (before) or Sunday (after); other days stay."""
    if move == WeekendMove.NONE or day.weekday() not in WEEKEND:
        return day
    step = timedelta(days=-1 if move == WeekendMove.BEFORE else 1)
    while day.weekday() in WEEKEND:
        day += step
    return day


def scheduled_dates(item: PlannedItem, until: str | date) -> list[tuple[int, str, str]]:
    """(payment number, date on the calendar, due date after the weekend move) up to ``until``.

    The item's own end date and payment count apply to the calendar date; ``until`` to the due date,
    so a payment moved past a month's end falls in the next month."""
    end = until if isinstance(until, date) else date.fromisoformat(until)
    last = date.fromisoformat(item.end_date) if item.end_date else None
    start = date.fromisoformat(item.start_date)
    limit = item.payment_count
    out: list[tuple[int, str, str]] = []
    number = 0
    while True:
        if item.frequency == Frequency.ONCE:
            day = start if number == 0 else None
        elif item.frequency == Frequency.WEEKLY:
            day = start + timedelta(weeks=item.interval_count * number)
        else:
            day = _add_months(start, _MONTH_STEP[item.frequency] * item.interval_count * number)
            if item.month_day:
                day = day.replace(day=min(item.month_day, calendar.monthrange(day.year, day.month)[1]))
        if day is None or (last and day > last) or (limit is not None and number >= limit):
            return out
        due = on_working_day(day, item.weekend_move)
        if due > end:
            return out
        number += 1
        out.append((number, day.isoformat(), due.isoformat()))


def payment_dates(item: PlannedItem, until: str | date) -> list[tuple[int, str]]:
    """(payment number, due date) for every payment from the first date up to ``until`` inclusive."""
    return [(number, due) for number, _, due in scheduled_dates(item, until)]


def previous_due(item: PlannedItem, due: str) -> str | None:
    """The date one period before ``due``, even before the item's first payment (None for a one-off).

    A payment dated nearer this than ``due`` belongs to the earlier period (7K)."""
    day = date.fromisoformat(due)
    if item.frequency == Frequency.ONCE:
        return None
    if item.frequency == Frequency.WEEKLY:
        return (day - timedelta(weeks=item.interval_count)).isoformat()
    return _add_months(day, -_MONTH_STEP[item.frequency] * item.interval_count).isoformat()


def last_payment_date(item: PlannedItem) -> str | None:
    """The final payment date when the schedule has a fixed end, else None."""
    if item.payment_count is None and not item.end_date:
        return None
    if item.frequency == Frequency.ONCE:
        return item.start_date
    dates = payment_dates(item, "2999-12-31")  # the item's own end date or count stops the schedule
    return dates[-1][1] if dates else None


def describe(item: PlannedItem) -> str:
    """Plain wording such as "Monthly on day 20" or "Every 2 weeks from 2026-09-03"."""
    start = date.fromisoformat(item.start_date)
    every = item.interval_count
    if item.frequency == Frequency.ONCE:
        text = f"Once on {item.start_date}"
    elif item.frequency == Frequency.WEEKLY:
        text = ("Weekly" if every == 1 else f"Every {every} weeks") + f" from {item.start_date}"
    elif item.frequency == Frequency.MONTHLY:
        text = ("Monthly" if every == 1 else f"Every {every} months") + f" on day {item.month_day or start.day}"
    elif item.frequency == Frequency.QUARTERLY:
        text = ("Every 3 months" if every == 1 else f"Every {3 * every} months") + f" on day {start.day}"
    else:
        text = ("Yearly" if every == 1 else f"Every {every} years") + f" on {start:%m-%d}"
    if item.weekend_move != WeekendMove.NONE:
        text += " · " + ("Thursday" if item.weekend_move == WeekendMove.BEFORE else "Sunday") + " if on a weekend"
    if item.payment_count:
        text += f" · {item.payment_count} payments"
    elif item.end_date:
        text += f" · until {item.end_date}"
    return text
