"""The phone's Upcoming (NF-7AR3): always today (C04.2), so this month's Left to pay leads, then today and the next
13 days as a strip, and the chosen day's payments. The PC route's month, chips and stepper are not used here."""
from __future__ import annotations

import calendar
from datetime import timedelta
from urllib.parse import urlencode

from lightning.core.dates import fmt_date, month_of, parse_month, today
from lightning.core.money import ZERO, fmt
from lightning.planning.calendar import month_calendar
from lightning.ui import status, visuals

STRIP_DAYS = 14
MARKS_PER_DAY = 3


def present(request, c, context: dict) -> dict:
    day = today()
    month = month_of(day)
    cal = context["cal"]
    if cal.month != month:  # a PC link with ?month= still opens on today here
        cal = month_calendar(c.planning, c.gameya, month, day, c.forecaster)
    last = parse_month(month)[1]
    end = day + timedelta(days=STRIP_DAYS - 1)  # not money
    following = month_calendar(c.planning, c.gameya, month_of(end), day, c.forecaster) if end > last else None

    def on(key: str):
        return (cal if key[:7] == month or following is None else following).on(key)

    paydays = set(cal.paydays) | set(following.paydays if following else ())
    short = {s for s in (cal.short_on, following.short_on if following else None) if s}
    strip = []
    for offset in range(STRIP_DAYS):
        when = day + timedelta(days=offset)  # not money
        key = fmt_date(when)
        entries = on(key)
        strip.append({"date": key, "day": when.day, "weekday": visuals.WEEKDAYS[when.weekday()], "today": offset == 0,
                      "entries": entries[:MARKS_PER_DAY], "payday": key in paydays, "short": key in short,
                      "open": any(not e.incoming and e.left > ZERO for e in entries)})
    asked = str(request.query_params.get("day", ""))
    keys = [d["date"] for d in strip]
    late = [e.date for e in cal.entries if e.state == "late" and not e.incoming]
    if asked in keys or asked in late:
        chosen = asked
    else:  # a late payment first, else the next day that asks for money, else today
        chosen = (late or [d["date"] for d in strip if d["open"]] or keys)[0]
    for d in strip:
        d["chosen"] = d["date"] == chosen
    name = calendar.month_name[day.month]
    return {"cal": cal, "strip": strip, "hero_label": f"Left to pay in {name}",
            "hero_line": status.sentence("{amt} paid of {amt2} due this month.", amt=fmt(cal.already_paid, 0),
                                         amt2=fmt(cal.month_total, 0)), "chosen": chosen, "shown": on(chosen),
            "day_back": "/plan/upcoming?" + urlencode({"day": chosen})}
