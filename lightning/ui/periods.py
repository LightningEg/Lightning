"""Shared date range contract for Overview and Birdview."""

import calendar
from dataclasses import dataclass
from datetime import date

from lightning.core.dates import fmt_date, month_of, parse_month
from lightning.core.errors import ValidationError


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    start: date
    end: date

    @property
    def start_text(self) -> str:
        return fmt_date(self.start)

    @property
    def end_text(self) -> str:
        return fmt_date(self.end)

    @property
    def tag(self) -> str:
        """The period in the fewest words, to sit beside a figure: '2026-10 so far', '2026-09', 'Year to date'."""
        if self.key == "month":
            last = calendar.monthrange(self.start.year, self.start.month)[1]
            return self.start_text[:7] + (" so far" if self.end.day < last or self.end.month != self.start.month else "")  # not money
        if self.key == "ytd":
            return "Year to date"
        if self.key == "all":
            return "All time"
        return f"{self.start_text} to {self.end_text}"

    @property
    def start_display(self) -> str:
        return fmt_date(self.start)

    @property
    def end_display(self) -> str:
        return fmt_date(self.end)


def parse_period(query, today: date, first_activity: str | None = None) -> Period:
    """Parse all|ytd|month|custom. Invalid selections raise a user-facing error."""
    key = str(query.get("period", "month"))
    if key == "all":
        start = date.fromisoformat(first_activity) if first_activity else today
        return Period("all", "All time", start, today)
    if key == "ytd":
        return Period("ytd", "YTD", date(today.year, 1, 1), today)
    if key == "custom":
        try:
            from_value, to_value = str(query.get("date_from", "")), str(query.get("date_to", ""))
            if len(from_value) < 7 or len(to_value) < 7:
                raise ValidationError("Choose both months for a custom report.")
            from_month = from_value[:7] if len(from_value) >= 7 else ""
            to_month = to_value[:7] if len(to_value) >= 7 else ""
            start, _ = parse_month(from_month)
            _, end = parse_month(to_month)
        except ValueError:
            raise ValidationError("Choose valid months for a custom report.") from None
        end = min(end, today)
        if end < start:
            raise ValidationError("The end month must be the same as or after the start month.")
        return Period(key, "Custom", start, end)
    if key != "month":
        raise ValidationError("Choose All time, YTD, Monthly, or Custom.")
    month = str(query.get("month", month_of(today)))
    start, end = parse_month(month)
    if start > today:
        raise ValidationError("Choose a month that has started.")
    return Period("month", "Monthly", start, min(end, today))
