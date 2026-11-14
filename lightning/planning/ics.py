"""The next three months' payments as a calendar file (NF-7AR4).

Upcoming offers it as a download; nothing leaves the device until the person saves the file and opens it in their
phone's or computer's calendar. Each payment still to pay (or still to come in) is one all-day event on its due day,
from the same `month_calendar` the Upcoming tab draws, so the file and the page never disagree. Events keep a stable
UID, so saving the file again updates the person's calendar instead of doubling it. Plain RFC 5545, no library.
"""
from __future__ import annotations

from datetime import date, timedelta, timezone

from lightning.core.dates import fmt_date, month_of, parse_month, wall_now
from lightning.core.money import fmt

from .calendar import CalendarEntry, month_calendar

MONTHS = 3
_OPEN = ("late", "today", "upcoming")


def _text(value: str) -> str:
    """RFC 5545 TEXT: backslash, semicolon, comma and line breaks escaped."""
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets continue on the next line after one space."""
    data, out = line.encode("utf-8"), []
    while len(data) > 75:
        cut = 75 if not out else 74
        while cut and (data[cut] & 0xC0) == 0x80:  # never split a UTF-8 character
            cut -= 1
        out.append(data[:cut].decode("utf-8"))
        data = data[cut:]
    out.append(data.decode("utf-8"))
    return [out[0]] + [" " + part for part in out[1:]]


def _event(entry: CalendarEntry, currency: str, stamp: str) -> list[str]:
    day = date.fromisoformat(entry.date)
    owner = entry.item_id if entry.item_id is not None else f"c{entry.circle_id}"
    kind = "in" if entry.incoming else "out"
    figure = f"{'+' if entry.incoming else ''}{fmt(entry.left, 0)} {currency}"
    count = f" ({entry.number} of {entry.of})" if entry.number and entry.of else ""
    return ["BEGIN:VEVENT",
            f"UID:{entry.date}-{entry.group}-{owner}-{kind}@lightning.local",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_text(f'{entry.name} · {figure}')}",
            f"DESCRIPTION:{_text(f'{entry.name}{count}: {figure}. From Lightning, Upcoming.')}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT"]


def payments_ics(planning, gameya, day: date, months: int = MONTHS) -> str:
    """Every payment from `day` through the end of the `months`th month that is still open, and the month's late
    payments (money still to pay; income that has not come is not put on a past day)."""
    currency = planning.transactions.base_currency
    stamp = wall_now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Lightning//Upcoming payments//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Lightning payments"]
    month = month_of(day)
    for _ in range(months):
        for entry in month_calendar(planning, gameya, month, day).entries:
            ahead = entry.date >= fmt_date(day)
            if entry.state in _OPEN and entry.left > 0 and (ahead or entry.state == "late" and not entry.incoming):
                lines += _event(entry, currency, stamp)
        month = month_of(parse_month(month)[1] + timedelta(days=1))
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"
