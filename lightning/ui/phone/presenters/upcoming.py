"""The phone's Upcoming (NF-7AR3): always today (C04.2), so this month's Left to pay leads, then today and the next
13 days as a strip, and the chosen day's payments. The PC route's month, chips and stepper are not used here."""
from __future__ import annotations

import calendar
from datetime import date
from urllib.parse import urlencode

from lightning.core.dates import today
from lightning.core.money import fmt
from lightning.planning.calendar import payment_window
from lightning.ui import status, visuals

STRIP_DAYS = 14
MARKS_PER_DAY = 3


def strip_days(window, chosen: str = "") -> list[dict]:
    """The window's days for a strip: weekday, number and up to three marks each (phone Upcoming and Money)."""
    out = []
    for index, d in enumerate(window.days):
        out.append({"date": d.date, "day": int(d.date[8:]), "weekday": visuals.WEEKDAYS[_weekday(d.date)],
                    "today": index == 0, "entries": d.entries[:MARKS_PER_DAY], "payday": d.payday, "short": d.short,
                    "open": d.open, "chosen": d.date == chosen})
    return out


def _weekday(text: str) -> int:
    return date.fromisoformat(text).weekday()


def present(request, c, context: dict) -> dict:
    day = today()
    window = payment_window(c.planning, c.gameya, day, STRIP_DAYS, c.forecaster)
    cal = window.month
    asked = str(request.query_params.get("day", ""))
    keys = [d.date for d in window.days]
    late = [e.date for e in cal.entries if e.state == "late" and not e.incoming]
    if asked in keys or asked in late:
        chosen = asked
    else:  # a late payment first, else the next day that asks for money, else today
        chosen = (late or [d.date for d in window.days if d.open] or keys)[0]
    name = calendar.month_name[day.month]
    return {"cal": cal, "strip": strip_days(window, chosen), "chosen": chosen, "shown": list(window.on(chosen)),
            "hero_label": f"Left to pay in {name}",
            "hero_line": status.sentence("{amt} paid of {amt2} due this month.", amt=fmt(cal.already_paid, 0),
                                         amt2=fmt(cal.month_total, 0)),
            "day_back": "/plan/upcoming?" + urlencode({"day": chosen})}
