"""What a figure leans on that may be old or missing (NF-7Y): a read model of reasons, never a number.

It answers "which prices, exchange rates or other inputs behind this figure are stale or absent, from what date,
and where do I fix it". It reads what valuation already knows (`ReportingService.stale_prices`, the holdings that
could not be valued, `fx.Rate` ages) and adds no calculation: the figure's amount is the same with or without it.
A note is either **known** (a dated input older than its limit) or **unknown** (nothing to date: no price, no rate);
there is no score and no second total."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lightning.core.dates import fmt_date, parse_date
from lightning.fx import STALE_DAYS

STALE_PRICE = "stale_price"
NO_PRICE = "no_price"
STALE_RATE = "stale_rate"
NO_RATE = "no_rate"


@dataclass(frozen=True)
class FreshnessNote:
    kind: str                  # one of the four constants above
    subject: str               # the holding, or the currency
    source_date: str | None    # the date of the input used; None when there is none to date (unknown)
    figure: str                # the figure it affects (a key of core.figures.FIGURES)
    link: str                  # where to fix it

    @property
    def known(self) -> bool:
        """True when the input has a date that is simply old; False when there is nothing to date."""
        return self.source_date is not None


class FreshnessService:
    def __init__(self, reporting, position):
        self.reporting = reporting
        self.position = position

    def for_what_you_own(self, as_of: date | str) -> tuple[FreshnessNote, ...]:
        """Notes behind "What you own" on a day: holdings priced long ago or not at all, and foreign currency
        held without a recent rate. Read only; ordered stale prices (oldest first), missing prices, rates."""
        day = fmt_date(as_of) if isinstance(as_of, date) else str(as_of)
        figure = "what_you_own"
        notes = [FreshnessNote(STALE_PRICE, row["name"], row["price_date"], figure, "/investments/prices")
                 for row in self.reporting.stale_prices(day)]
        notes += [FreshnessNote(NO_PRICE, text.split(" — ")[0], None, figure, "/investments/prices")
                  for text in self.position.at(day).unvalued]
        for held in self.reporting.fx_positions.all(day, day):
            if held.units <= 0 and not held.accounts:
                continue
            if held.rate is None:
                notes.append(FreshnessNote(NO_RATE, held.currency, None, figure, "/settings?section=currencies&tab=rates"))
            elif held.rate.age_days > STALE_DAYS:
                notes.append(FreshnessNote(STALE_RATE, held.currency, held.rate.date, figure, "/settings?section=currencies&tab=rates"))
        return tuple(notes)

    @staticmethod
    def days_old(note: FreshnessNote, as_of: date | str) -> int | None:
        """How old the dated input is on the day shown; None for an unknown one."""
        if note.source_date is None:
            return None
        day = as_of if isinstance(as_of, date) else parse_date(as_of)
        return (day - parse_date(note.source_date)).days
