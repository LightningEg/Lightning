"""What a figure leans on that may be old or missing (NF-7Y): a read model of reasons, never a number.

It answers "which prices, exchange rates or other inputs behind this figure are stale or absent, from what date,
and where do I fix it". It reads what valuation already knows (`ReportingService.stale_prices`, the holdings that
could not be valued, `fx.Rate` ages) and adds no calculation: the figure's amount is the same with or without it.
A note is either **known** (a dated input older than its limit) or **unknown** (nothing to date: no price, no rate);
there is no score and no second total."""
from __future__ import annotations

from datetime import date

from lightning.core.figure_inputs import FreshnessNote
from lightning.core.dates import fmt_date, parse_date
from lightning.fx import STALE_DAYS

STALE_PRICE = "stale_price"
NO_PRICE = "no_price"
STALE_RATE = "stale_rate"
NO_RATE = "no_rate"




class FreshnessService:
    def __init__(self, reporting, position, accounts=None, reconciliation=None, receipts=None):
        self.reporting = reporting
        self.position = position
        self.accounts, self.reconciliation, self.receipts = accounts, reconciliation, receipts

    def for_what_you_own(self, as_of: date | str) -> tuple[FreshnessNote, ...]:
        """Notes behind "What you own" on a day: holdings priced long ago or not at all, and foreign currency
        held without a recent rate. Read only; ordered stale prices (oldest first), missing prices, rates."""
        day = fmt_date(as_of) if isinstance(as_of, date) else str(as_of)
        figure = "what_you_own"
        notes = [FreshnessNote(STALE_PRICE, row["name"], row["price_date"], figure, "/investments/prices")
                 for row in self.reporting.stale_prices(day)]
        notes += [FreshnessNote(NO_PRICE, text.split(" — ")[0], None, figure, "/investments/prices")
                  for text in self.position.at(day, match_payments=False).unvalued]
        for held in self.reporting.fx_positions.all(day, day):
            if held.units <= 0 and not held.accounts:
                continue
            if held.rate is None:
                notes.append(FreshnessNote(NO_RATE, held.currency, None, figure, "/settings?section=currencies&tab=rates"))
            elif held.rate.age_days > STALE_DAYS:
                notes.append(FreshnessNote(STALE_RATE, held.currency, held.rate.date, figure, "/settings?section=currencies&tab=rates"))
        return tuple(notes) + self._cash_notes(day, figure, all_currencies=True)

    def _cash_notes(self, day, figure, *, all_currencies=False):
        if self.accounts is None:
            return ()
        notes = []
        for account in self.accounts.list():
            if account.account_type.value not in ("CASH", "BANK", "BROKERAGE"):
                continue
            if not all_currencies and not account.counts_as_spendable(self.reporting.base_currency):
                continue
            owned_cash = (self.reporting.account_balance(account.id, day)
                          - self.reporting.money_from_others.cash_total_for_account(account.id, day))
            if not owned_cash:
                continue
            checked = self.reconciliation.checked_through(account.id) if self.reconciliation else None
            if checked and checked > day:
                checked = None
            if checked is None or (parse_date(day) - parse_date(checked)).days > 31:
                notes.append(FreshnessNote("old_check" if checked else "no_check", account.name, checked, figure,
                                           f"/accounts/{account.id}/reconcile"))
        if self.receipts is not None:
            for account in self.accounts.list():
                if account.account_type.value != "DEPOSIT":
                    continue
                for receipt in self.receipts.expected_past(account.id, day):
                    if not self.receipts.needs_match(receipt):
                        continue
                    destination = self.accounts.get(receipt["destination_account_id"])
                    if not all_currencies and not destination.counts_as_spendable(self.reporting.base_currency):
                        continue
                    notes.append(FreshnessNote("unconfirmed_receipt", receipt["certificate_name"],
                                               receipt["event_date"], figure, f"/accounts/{account.id}"))
        return tuple(notes)

    def for_free_cash(self, as_of):
        """Eligible cash only; equity prices and foreign cash do not establish Free cash."""
        day = fmt_date(as_of) if isinstance(as_of, date) else str(as_of)
        return self._cash_notes(day, "free_cash") + self._rate_notes(day, "free_cash", eligible_only=True)

    def for_forecast(self, as_of):
        day = fmt_date(as_of) if isinstance(as_of, date) else str(as_of)
        notes = list(self._cash_notes(day, "forecast", all_currencies=True))
        notes.extend(self._rate_notes(day, "forecast"))
        return tuple(notes)

    def _rate_notes(self, day, figure, *, eligible_only=False):
        notes = []
        if self.accounts is not None:
            currencies = sorted({a.currency for a in self.accounts.list()
                                 if a.account_type.value in ("CASH", "BANK", "BROKERAGE")
                                 and (not eligible_only or a.counts_as_spendable(self.reporting.base_currency))
                                 and a.currency != self.reporting.base_currency})
            for currency in currencies:
                rate = self.reporting.valuer.fx(currency, day)
                if rate is None or rate.age_days > STALE_DAYS:
                    notes.append(FreshnessNote(NO_RATE if rate is None else STALE_RATE, currency,
                                               None if rate is None else rate.date, figure,
                                               "/settings?section=currencies&tab=rates"))
        return tuple(notes)

    @staticmethod
    def days_old(note: FreshnessNote, as_of: date | str) -> int | None:
        """How old the dated input is on the day shown; None for an unknown one."""
        if note.source_date is None:
            return None
        day = as_of if isinstance(as_of, date) else parse_date(as_of)
        return (day - parse_date(note.source_date)).days
