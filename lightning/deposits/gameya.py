"""Gam'eya (rotating savings circle) on the certificate backbone.

One GAMEYA account per circle holds that currency's cash. An instalment is an internal transfer from your
bank or wallet into the circle; your payout is one back out. Neither is income or spending, so Net worth
never moves. The balance tells the position: positive, the circle owes you (Gam'eya paid in); negative, you
took the pot early and owe the circle (Gam'eya still to pay). Terms are in ``gameya_terms``; the forecast
reads them through ``future_events`` like CD proceeds, and an estimated interest (rate above zero) is never
posted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.money import ZERO, check_places, fmt, from_e6, to_decimal, to_e6
from lightning.database.connection import Database
from lightning.transactions.service import TransactionService

from .domain import DepositEvent, GameyaFrequency, GameyaTerms
from .repository import DepositRepository
from .service import _add_months

_MICRO = Decimal("0.000001")
MIN_MEMBERS, MAX_MEMBERS = 2, 60


@dataclass(frozen=True)
class GameyaProgress:
    """Where one circle stands on a day."""
    terms: GameyaTerms
    as_of: str
    paid: int                    # instalments recorded
    payouts: int                 # payouts recorded
    balance: Decimal             # paid in less received, in the circle's currency
    next_index: int | None       # the instalment to record next (1-based); None when all are recorded
    next_date: str | None        # its scheduled date (may be in the past: overdue)
    payout_date: str             # your turn
    overdue: bool                # the next instalment is dated on or before as_of
    payout_due: bool             # your turn has come and the payout is not recorded

    @property
    def due_indices(self) -> list[int]:
        """Unrecorded scheduled instalments due by this date; saving terms posts none."""
        return [index for index in range(self.paid + 1, self.terms.members + 1)
                if installment_date(self.terms, index).isoformat() <= self.as_of]

    @property
    def due_count(self) -> int:
        return len(self.due_indices)

    @property
    def due_amount(self) -> Decimal:
        return self.terms.installment * self.due_count

    @property
    def remaining(self) -> int:
        return self.terms.members - self.paid

    @property
    def all_recorded(self) -> bool:
        return self.paid >= self.terms.members and self.payouts >= 1

    @property
    def finished(self) -> bool:
        return self.all_recorded and self.balance == ZERO

    @property
    def owes_you(self) -> bool:
        return self.balance > ZERO


def installment_date(terms: GameyaTerms, index: int) -> date:
    """Instalment ``index`` (1-based): the first date plus whole months, clamped to month end."""
    return _add_months(date.fromisoformat(terms.first_date), index - 1)


def payout_date(terms: GameyaTerms) -> date:
    return installment_date(terms, terms.my_turn)


class GameyaService:
    """Store a circle's terms, record its instalments and payout, and forecast what is still to come."""

    def __init__(self, db: Database, accounts, assets, transactions: TransactionService | None = None):
        self.db = db
        self.accounts = accounts
        self.assets = assets
        self.transactions = transactions
        self.repo = DepositRepository(db)

    # ------------------------------------------------------------------ terms
    def find(self, account_id: int) -> GameyaTerms | None:
        return self.repo.get_gameya(account_id)

    def get(self, account_id: int) -> GameyaTerms:
        terms = self.repo.get_gameya(account_id)
        if terms is None:
            raise NotFoundError("Gam'eya terms were not found.")
        return terms

    def save_terms(self, account_id: int, *, organiser, members, installment, first_date, my_turn,
                   payout="", annual_rate="", funding_account_id, payout_account_id,
                   frequency="MONTHLY") -> GameyaTerms:
        """Create or change a circle's terms. Recorded instalments and the payout never change."""
        circle = self._circle(account_id)
        organiser = (organiser or "").strip()
        if not organiser:
            raise ValidationError("Enter who runs this gam'eya.", "organiser")
        try:
            members_n = int(str(members).strip())
        except (TypeError, ValueError):
            raise ValidationError(f"Enter the number of members, from {MIN_MEMBERS} to {MAX_MEMBERS}.",
                                  "members") from None
        if not MIN_MEMBERS <= members_n <= MAX_MEMBERS:
            raise ValidationError(f"Enter the number of members, from {MIN_MEMBERS} to {MAX_MEMBERS}.", "members")
        amount = check_places(to_decimal(installment, "installment"), 2, "installment")
        if amount <= ZERO:
            raise ValidationError("Enter an instalment above zero.", "installment")
        try:
            frequency_v = GameyaFrequency(frequency or "MONTHLY")
        except (ValueError, TypeError):
            raise ValidationError("Choose a monthly gam'eya.", "frequency") from None
        first = parse_date(first_date, "first_date")
        try:
            turn = int(str(my_turn).strip())
        except (TypeError, ValueError):
            raise ValidationError(f"Enter your turn, from 1 to {members_n}.", "my_turn") from None
        if not 1 <= turn <= members_n:
            raise ValidationError(f"Enter your turn, from 1 to {members_n}.", "my_turn")
        pot = (check_places(to_decimal(payout, "payout"), 2, "payout") if str(payout or "").strip()
               else amount * members_n)
        if pot <= ZERO:
            raise ValidationError("Enter a payout above zero.", "payout")
        rate = to_decimal(annual_rate if str(annual_rate or "").strip() else "0", "annual_rate")
        if not ZERO <= rate <= Decimal("100"):
            raise ValidationError("Annual rate must be between 0 and 100 percent.", "annual_rate")
        funding = self._cash_account(funding_account_id, "funding_account_id")
        receiving = self._cash_account(payout_account_id, "payout_account_id")
        if funding.currency != circle.currency or receiving.currency != circle.currency:
            raise ValidationError("The circle, funding account and payout account must use the same currency.",
                                  "funding_account_id")
        to_e6(amount), to_e6(pot)
        paid, _ = self.repo.gameya_transfers(account_id, "9999-12-31")
        if paid > members_n:
            raise ValidationError(f"{paid} instalments are already recorded; members cannot be fewer.", "members")
        terms = GameyaTerms(account_id, organiser, members_n, amount, frequency_v, fmt_date(first), turn, pot, rate,
                            funding.id, receiving.id)
        with self.db.transaction():
            self.repo.save_gameya(terms)
        return terms

    # --------------------------------------------------------------- progress
    def progress(self, account_id: int, as_of=None) -> GameyaProgress:
        terms = self.get(account_id)
        day = parse_date(as_of, "as_of") if as_of is not None else today()
        text = fmt_date(day)
        paid, payouts = self.repo.gameya_transfers(account_id, "9999-12-31")
        balance = from_e6(self.repo.owned_balance_e6(account_id, text))
        next_index = paid + 1 if paid < terms.members else None
        next_date = fmt_date(installment_date(terms, next_index)) if next_index else None
        turn_day = payout_date(terms)
        return GameyaProgress(terms, text, paid, payouts, balance, next_index, next_date, fmt_date(turn_day),
                              overdue=bool(next_date and next_date <= text),
                              payout_due=bool(payouts == 0 and turn_day <= day))

    def circles(self) -> list[tuple]:
        """(account, terms) of every active circle that has terms."""
        found = []
        for account in self.accounts.list(active_only=True):
            if account.account_type == AccountType.GAMEYA:
                terms = self.repo.get_gameya(account.id)
                if terms is not None:
                    found.append((account, terms))
        return found

    # -------------------------------------------------------------- recording
    def record_instalment(self, account_id: int, date_value=None, amount=None, funding_account_id=None):
        """Move one instalment from your funding account into the circle (a transfer, never spending)."""
        if self.transactions is None:
            raise RuntimeError("Gam'eya transaction dependencies are not configured.")
        circle = self._circle(account_id)
        progress = self.progress(account_id)
        terms = progress.terms
        if progress.next_index is None:
            raise ValidationError(f"All {terms.members} instalments are already recorded.", "date")
        day = parse_date(date_value or min(date.fromisoformat(progress.next_date), today()), "date")
        value = check_places(to_decimal(amount if str(amount or "").strip() else terms.installment, "amount"),
                             2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter an amount above zero.", "amount")
        funding = self._cash_account(funding_account_id or terms.funding_account_id, "funding_account_id")
        if funding.currency != circle.currency:
            raise ValidationError("Choose a funding account in the circle's currency.", "funding_account_id")
        with self.db.transaction():
            self._check_owned_cash(funding, day, value, "instalment")
            return self.transactions.record_transfer(
                fmt_date(day), funding.id, circle.id, value,
                description=f"Gam'eya instalment {progress.next_index} of {terms.members} · {circle.name}")

    def record_past_instalments(self, account_id: int, *, expected_paid: int, as_of=None):
        """Record due dates together, atomically. The shown paid count prevents a stale resubmit.

        Each instalment remains its own dated internal transfer. Any cash validation failure
        rolls back the entire batch, including earlier dates that would have been affordable.
        """
        day = parse_date(as_of, "as_of") if as_of is not None else today()
        if day > today():
            raise ValidationError("Choose today or an earlier date.", "as_of")
        with self.db.transaction():
            progress = self.progress(account_id, day)
            if progress.paid != expected_paid:
                raise ValidationError("The circle has changed. Review its instalments before recording again.", "instalment")
            if not progress.due_indices:
                raise ValidationError("No past instalments remain to record.", "instalment")
            return [self.record_instalment(account_id, installment_date(progress.terms, index))
                    for index in progress.due_indices]

    def record_payout(self, account_id: int, date_value=None, amount=None, payout_account_id=None):
        """Move your turn's payout from the circle into your payout account. The circle may go below zero:
        that is what you owe it for taking the pot early."""
        if self.transactions is None:
            raise RuntimeError("Gam'eya transaction dependencies are not configured.")
        circle = self._circle(account_id)
        progress = self.progress(account_id)
        terms = progress.terms
        if progress.payouts:
            raise ValidationError("Your payout is already recorded.", "date")
        day = parse_date(date_value or min(date.fromisoformat(progress.payout_date), today()), "date")
        value = check_places(to_decimal(amount if str(amount or "").strip() else terms.payout, "amount"), 2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter the amount you received.", "amount")
        target = self._cash_account(payout_account_id or terms.payout_account_id, "payout_account_id")
        if target.currency != circle.currency:
            raise ValidationError("Choose a payout account in the circle's currency.", "payout_account_id")
        with self.db.transaction():
            return self.transactions.record_transfer(
                fmt_date(day), circle.id, target.id, value, description=f"Gam'eya payout · {circle.name}")

    def _check_owned_cash(self, funding, day: date, value: Decimal, what: str) -> None:
        """The same owned-cash rule as a CD purchase: the account must hold the cash that day and every later day."""
        amount_e6 = to_e6(value)
        available_e6 = self.repo.owned_balance_e6(funding.id, fmt_date(day))
        if available_e6 < amount_e6:
            available = Decimal(available_e6).scaleb(-6)
            raise ValidationError(
                f"{funding.name} had {fmt(available, 2)} {funding.currency} of your cash on "
                f"{fmt_date(day)}; this {what} needs {fmt(value, 2)} {funding.currency}.", "amount")
        remaining_e6 = available_e6 - amount_e6
        for movement in self.repo.owned_cash_deltas_after(funding.id, fmt_date(day)):
            remaining_e6 += int(movement["delta_e6"] or 0)
            if remaining_e6 < 0:
                remaining = Decimal(remaining_e6).scaleb(-6)
                raise ValidationError(
                    f"After activity dated {movement['date']}, {funding.name} would have "
                    f"{fmt(remaining, 2, True)} {funding.currency}. This {what} is dated "
                    f"{fmt_date(day)}; check the already-recorded activity on or after that date.", "amount")

    # --------------------------------------------------------------- forecast
    def future_events(self, as_of, end) -> list[DepositEvent]:
        """Instalments still to pay, the payout and, with a rate, its estimated interest, after ``as_of`` up to
        ``end``. Estimates only: nothing here posts. Past-due items are not forecast; Needs you lists them."""
        day, horizon = parse_date(as_of, "as_of"), parse_date(end, "end")
        if horizon <= day:
            return []
        events: list[DepositEvent] = []
        for circle, terms in self.circles():
            progress = self.progress(circle.id, day)
            turn = payout_date(terms)
            for index in range(progress.paid + 1, terms.members + 1):
                due = installment_date(terms, index)
                if day < due <= horizon:
                    events.append(DepositEvent(fmt_date(due), terms.funding_account_id, -terms.installment,
                                               "INSTALLMENT", circle.id, source="GAMEYA"))
            if progress.payouts == 0 and day < turn <= horizon:
                events.append(DepositEvent(fmt_date(turn), terms.payout_account_id, terms.payout, "PAYOUT",
                                           circle.id, source="GAMEYA"))
                interest = self._estimated_interest(circle.id, terms, progress, day)
                if interest > ZERO:
                    events.append(DepositEvent(fmt_date(turn), terms.payout_account_id, interest, "INTEREST",
                                               circle.id, source="GAMEYA"))
        return sorted(events, key=lambda e: (e.date, e.deposit_account_id, e.kind))

    def _estimated_interest(self, account_id: int, terms: GameyaTerms, progress: GameyaProgress,
                            day: date) -> Decimal:
        """Simple interest on the positive balance, actual days ÷ 365, from the first movement to your turn.
        Recorded movements up to ``day`` and instalments still to come are the balance's path."""
        if terms.annual_rate <= ZERO:
            return ZERO
        turn = payout_date(terms)
        moves: dict[date, int] = {}
        for movement in self.repo.owned_cash_deltas_after(account_id, "0000-00-00"):
            when = date.fromisoformat(movement["date"])
            if when <= day:
                moves[when] = moves.get(when, 0) + int(movement["delta_e6"] or 0)
        for index in range(progress.paid + 1, terms.members + 1):
            due = installment_date(terms, index)
            if due > day:
                moves[due] = moves.get(due, 0) + to_e6(terms.installment)
        balance_e6, previous, accrued = 0, None, 0
        for when in sorted(moves):
            if when > turn:
                break
            if previous is not None and balance_e6 > 0:
                accrued += balance_e6 * (when - previous).days
            balance_e6, previous = balance_e6 + moves[when], when
        if previous is not None and balance_e6 > 0 and turn > previous:
            accrued += balance_e6 * (turn - previous).days
        interest = Decimal(accrued).scaleb(-6) * terms.annual_rate / Decimal(100) / Decimal(365)
        return interest.quantize(_MICRO, rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------ Needs you
    def attention(self, on: date) -> list[dict]:
        """One row per circle with an instalment (or, if none, the payout) past its date and not recorded."""
        rows = []
        for circle, terms in self.circles():
            progress = self.progress(circle.id, on)
            if progress.overdue:
                rows.append({"label": f"Gam'eya instalment due: {circle.name}",
                             "detail": f"{progress.due_count} instalment{'s' if progress.due_count != 1 else ''} · {fmt(progress.due_amount, 0)} {circle.currency} · "
                                       f"first due {progress.next_date} · not recorded yet."
                                       + (f" Payout {fmt(terms.payout, 0)} {circle.currency} was due {progress.payout_date}."
                                          if progress.payout_due else ""),
                             "href": f"/gameya/{circle.id}#record-instalment", "action": "Record instalment",
                             "priority": 1,
                             # Home's To do at a glance (IV-11E; workflows.review.glance)
                             "glance": {"name": circle.name, "verb": "Record", "amount": progress.due_amount,
                                        "when": "due {sa}", "n": progress.due_count, "sa": progress.next_date}})
            elif progress.payout_due:
                rows.append({"label": f"Gam'eya payout due: {circle.name}",
                             "detail": f"Your turn was {progress.payout_date} · {fmt(terms.payout, 0)} "
                                       f"{circle.currency} · not recorded yet.",
                             "href": f"/gameya/{circle.id}#record-payout", "action": "Record payout",
                             "priority": 1,
                             "glance": {"name": circle.name, "verb": "Record", "amount": terms.payout,
                                        "when": "your payout", "n": None, "sa": ""}})
        return rows

    # ---------------------------------------------------------------- helpers
    def _circle(self, account_id: int):
        try:
            account = self.accounts.require_usable(int(account_id), "account_id")
        except (NotFoundError, ValueError, TypeError):
            raise ValidationError("Choose an active gam'eya account.", "account_id") from None
        if account.account_type != AccountType.GAMEYA:
            raise ValidationError("Choose a gam'eya account.", "account_id")
        return account

    def _cash_account(self, account_id, field: str):
        try:
            account = self.accounts.require_usable(int(account_id), field)
        except (NotFoundError, ValueError, TypeError):
            raise ValidationError("Choose an active bank or cash account.", field) from None
        if account.account_type not in {AccountType.BANK, AccountType.CASH}:
            raise ValidationError("Choose an active bank or cash account.", field)
        return account
