"""Read-only evidence behind a financial figure, shared with journal context."""
from dataclasses import dataclass


@dataclass(frozen=True)
class FreshnessNote:
    kind: str                  # stable reason key
    subject: str               # the holding, or the currency
    source_date: str | None    # the date of the input used; None when there is none to date (unknown)
    figure: str                # the figure it affects (a key of core.figures.FIGURES)
    link: str                  # where to fix it

    @property
    def known(self) -> bool:
        """True when the input has a date that is simply old; False when there is nothing to date."""
        return self.source_date is not None

