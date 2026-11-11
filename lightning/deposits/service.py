from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from lightning.accounts.domain import AccountType
from lightning.core.dates import fmt_date, parse_date, today
from lightning.core.errors import NotFoundError, ValidationError
from lightning.core.ledger import Effect, PostingLine
from lightning.core.money import ZERO, check_places, fmt, from_e6, to_decimal, to_e6
from lightning.core.refs import DocType
from lightning.database.connection import Database
from lightning.transactions.service import TransactionService

from .domain import (CertificateTerms, CompoundingFrequency, DepositEvent, DepositTerms, InterestMethod,
                     PayoutFrequency)
from .repository import DepositRepository

_MICRO = Decimal("0.000001")
_MONTHS = {PayoutFrequency.MONTHLY: 1, PayoutFrequency.QUARTERLY: 3,
           PayoutFrequency.YEARLY: 12}
_COMPOUND_MONTHS = {CompoundingFrequency.MONTHLY: 1, CompoundingFrequency.QUARTERLY: 3,
                    CompoundingFrequency.YEARLY: 12}


class DepositService:
    """Store CD terms and produce future cash events without posting ledger entries."""

    def __init__(self, db: Database, accounts, assets=None, transactions: TransactionService | None = None,
                 gameya=None):
        self.db = db
        self.gameya = gameya  # savings circles forecast through the same events (lightning/deposits/gameya.py)
        self.accounts = accounts
        self.assets = assets
        self.transactions = transactions
        self.repo = DepositRepository(db)

    def list_certificates(self, account_id: int):
        self._portfolio(account_id)
        return self.repo.list_certificates(account_id)

    def certificate(self, certificate_id: int):
        certificate = self.repo.get_certificate(certificate_id)
        if certificate is None:
            raise NotFoundError("Certificate was not found.")
        return certificate

    def maturity_outlook(self, certificate) -> dict:
        """NF-3AZ8: what a certificate says about its maturity. ``expected`` is a forecast from its terms (principal and
        the interest due that day), never received cash; ``received`` appears only once a redemption is recorded and
        posted, from the actual amount that reached the destination account."""
        terms = certificate.terms
        maturity = date.fromisoformat(terms.maturity_date)
        events = self._certificate_events(terms, date.fromisoformat(terms.start_date) - timedelta(days=1), maturity)
        expected = sum((e.amount for e in events if e.date == terms.maturity_date), ZERO)
        row = self.db.one(
            "SELECT r.transaction_id,r.destination_account_id,t.date FROM cd_redemptions r JOIN transactions t "
            "ON t.id=r.transaction_id WHERE r.certificate_id=? AND t.status='POSTED' ORDER BY t.date DESC LIMIT 1",
            (terms.id,))
        received = None
        if row:
            amount_e6 = self.db.scalar("SELECT COALESCE(SUM(amount_e6),0) FROM ledger_entries WHERE transaction_id=? "
                                       "AND account_id=?", (row["transaction_id"], row["destination_account_id"]))
            received = {"transaction_id": row["transaction_id"], "date": row["date"], "account_id": row["destination_account_id"],
                        "amount": from_e6(amount_e6)}
        return {"expected_date": terms.maturity_date, "expected": expected if expected > ZERO else None, "received": received}

    def open_certificates(self):
        """Every certificate still held (not redeemed), oldest maturity first."""
        rows = self.db.all("SELECT id FROM cd_certificates ORDER BY maturity_date,id")
        items = (self.repo.get_certificate(int(row["id"])) for row in rows)
        return [item for item in items if item is not None and not item.redeemed and item.units == Decimal(1)]

    def attention(self, on: date) -> list[dict]:
        """IV-12J4: Needs you rows for a certificate that matured and is not yet recorded as redeemed, and for one
        whose earliest withdrawal date arrived in the last 14 days. Nothing is posted."""
        rows = []
        for item in self.open_certificates():
            terms = item.terms
            maturity, unlock = parse_date(terms.maturity_date), parse_date(terms.lockup_end_date)
            account = self.accounts.get(terms.account_id)
            href = f"/deposits/{terms.account_id}?redeem={terms.id}#certificate-{terms.id}"
            if maturity <= on:
                expected = self.maturity_outlook(item)["expected"] or terms.principal
                rows.append({"label": f"Certificate matured: {terms.name}",
                             "detail": f"Matured {terms.maturity_date} · about {fmt(expected, 0)} {account.currency} "
                                       "expected · record what the bank paid.",
                             "href": href, "action": "Record what the bank paid", "priority": 1,
                             "glance": {"name": terms.name, "verb": "Record", "amount": expected,
                                        "when": "matured {sa}", "n": None, "sa": terms.maturity_date}})
            elif unlock != parse_date(terms.start_date) and unlock <= on <= unlock + timedelta(days=14):
                rows.append({"label": f"Certificate can now be withdrawn: {terms.name}",
                             "detail": f"Earliest withdrawal {terms.lockup_end_date} · matures {terms.maturity_date}.",
                             "href": href, "action": "Open", "priority": 2,
                             "glance": {"name": terms.name, "verb": "Open", "amount": terms.principal,
                                        "when": "unlocked {sa}", "n": None, "sa": terms.lockup_end_date}})
        return rows

    def certificate_for_asset(self, asset_id: int):
        return self.repo.get_certificate_by_asset(asset_id)

    def legacy_cash_balance(self, account_id: int, as_of=None) -> Decimal:
        self._portfolio(account_id)
        return Decimal(self.repo.owned_balance_e6(account_id, fmt_date(as_of or today()))).scaleb(-6)

    def move_legacy_cash(self, account_id: int, date_value, amount, destination_account_id: int):
        """Move pre-portfolio cash out of a legacy DEPOSIT account into a liquid account."""
        if self.transactions is None:
            raise RuntimeError("Certificate transaction dependencies are not configured.")
        portfolio = self._portfolio(account_id)
        destination = self._typed_account(destination_account_id, {AccountType.BANK, AccountType.CASH},
                                          "destination_account_id")
        if destination.currency != portfolio.currency:
            raise ValidationError("Choose a destination in the CD portfolio's currency.", "destination_account_id")
        day = parse_date(date_value, "date")
        value = check_places(to_decimal(amount, "amount"), 2, "amount")
        if value <= ZERO:
            raise ValidationError("Enter an amount above zero.", "amount")
        if value > self.legacy_cash_balance(account_id, day):
            raise ValidationError("The old deposit account does not have that much cash to move.", "amount")
        return self.transactions.record_transfer(fmt_date(day), account_id, destination.id, value,
                                                 description="Move legacy CD cash to liquid account",
                                                 allow_legacy_deposit_cash=True)

    def purchase(self, account_id: int, name: str, start_date, lockup_end_date, maturity_date,
                 principal, annual_rate, interest_method, payout_frequency,
                 compounding_frequency, destination_account_id: int, funding_account_id: int | None,
                 term_years="", *, _owned=False):
        """Buy one named certificate into a bank's deposit portfolio from chosen liquid cash."""
        owned = _owned
        if self.assets is None or self.transactions is None:
            raise RuntimeError("Certificate purchase dependencies are not configured.")
        portfolio = self._portfolio(account_id)
        if not portfolio.institution.strip():
            raise ValidationError("Set the bank under Institution on this account before adding its CDs.",
                                  "institution")
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a name for this certificate.", "name")
        start = parse_date(start_date, "start_date")
        maturity = _maturity_date(start, maturity_date, term_years)
        lockup = parse_date(lockup_end_date or maturity, "lockup_end_date")
        if start > today():
            raise ValidationError("A certificate purchase cannot be in the future.", "start_date")
        if start >= maturity:
            raise ValidationError("Maturity must be after the purchase date.", "maturity_date")
        if not start <= lockup <= maturity:
            raise ValidationError("Earliest withdrawal must be between the purchase and maturity dates.",
                                  "lockup_end_date")
        amount = check_places(to_decimal(principal, "principal"), 2, "principal")
        if amount <= ZERO:
            raise ValidationError("Enter a principal above zero.", "principal")
        to_e6(amount)
        rate = to_decimal(annual_rate, "annual_rate")
        if not ZERO <= rate <= Decimal("100"):
            raise ValidationError("Annual rate must be between 0 and 100 percent.", "annual_rate")
        method = self._method(interest_method)
        payout = self._payout_frequency(payout_frequency)
        compounding = self._compounding_frequency(compounding_frequency)
        if method == InterestMethod.COMPOUND and payout != PayoutFrequency.AT_MATURITY:
            raise ValidationError("Compound interest is paid at maturity only.", "payout_frequency")
        destination = self._typed_account(destination_account_id, {AccountType.BANK, AccountType.CASH},
                                    "destination_account_id")
        if owned:
            if destination.currency != portfolio.currency:
                raise ValidationError("The portfolio and payout account must use the same currency.",
                                      "destination_account_id")
            return self._record_owned(portfolio, name, start, lockup, maturity, amount, rate, method, payout,
                                      compounding, destination)
        funding = self._typed_account(funding_account_id, {AccountType.BANK, AccountType.CASH}, "funding_account_id")
        if funding.currency != portfolio.currency or destination.currency != portfolio.currency:
            raise ValidationError("The portfolio, funding account and payout account must use the same currency.",
                                  "funding_account_id")
        with self.db.transaction():
            available_e6 = self.repo.owned_balance_e6(funding.id, fmt_date(start))
            amount_e6 = to_e6(amount)
            if available_e6 < amount_e6:
                available = Decimal(available_e6).scaleb(-6)
                raise ValidationError(
                    f"{funding.name} had {fmt(available, 2)} {funding.currency} of your cash on "
                    f"{fmt_date(start)}; this purchase needs {fmt(amount, 2)} {funding.currency}.", "principal")
            remaining_e6 = available_e6 - amount_e6
            for movement in self.repo.owned_cash_deltas_after(funding.id, fmt_date(start)):
                remaining_e6 += int(movement["delta_e6"] or 0)
                if remaining_e6 < 0:
                    remaining = Decimal(remaining_e6).scaleb(-6)
                    raise ValidationError(
                        f"After activity dated {movement['date']}, {funding.name} would have "
                        f"{fmt(remaining, 2, True)} {funding.currency}. This CD purchase is dated "
                        f"{fmt_date(start)}; check the already-recorded activity on or after that date.",
                        "principal")
            asset = self.assets.create_certificate_asset(name)
            cash_asset = self.assets.cash_asset(funding.currency)
            lines = [
                PostingLine.cash(funding.id, cash_asset.id, -amount, Effect.INTERNAL,
                                 memo=f"Buy certificate · {name}"),
                PostingLine.units(portfolio.id, asset.id, Decimal(1), amount, Effect.INTERNAL, amount,
                                  memo=f"Certificate purchase · {name}"),
            ]
            txn = self.transactions.post(DocType.BUY, fmt_date(start), lines,
                                         f"Buy CD · {name}", portfolio.institution)
            terms = CertificateTerms(
                id=0, account_id=portfolio.id, asset_id=asset.id, name=name,
                start_date=fmt_date(start), lockup_end_date=fmt_date(lockup), maturity_date=fmt_date(maturity),
                principal=amount, annual_rate=rate, interest_method=method, payout_frequency=payout,
                compounding_frequency=compounding, destination_account_id=destination.id,
                purchase_transaction_id=txn.id,
            )
            certificate_id = self.repo.save_certificate(terms)
        return self.certificate(certificate_id), txn

    def record_owned(self, account_id: int, name: str, start_date, lockup_end_date, maturity_date, principal,
                     annual_rate, interest_method, payout_frequency, compounding_frequency,
                     destination_account_id: int, term_years=""):
        """NF-12I: a certificate bought before tracking began. No cash moves: it posts an opening (``OPN``) unit
        line at the principal on the day tracking starts (``tracking_start``), keeps the true purchase date in the
        terms for the schedule and maturity, and counts as a baseline, never new money."""
        return self.purchase(account_id, name, start_date, lockup_end_date, maturity_date, principal, annual_rate,
                             interest_method, payout_frequency, compounding_frequency, destination_account_id, None,
                             term_years, _owned=True)

    def tracking_start(self, on=None) -> date:
        """The day this profile's records begin: its earliest posted entry, or today when it has none."""
        first = self.db.scalar("SELECT MIN(date) FROM transactions WHERE status='POSTED'")
        current = parse_date(on or today())
        return min(parse_date(first), current) if first else current

    def _record_owned(self, portfolio, name, start: date, lockup: date, maturity: date, amount: Decimal,
                      rate: Decimal, method, payout, compounding, destination):
        if maturity <= today():
            raise ValidationError("This certificate has already matured; record what the bank paid as money in.",
                                  "maturity_date")
        counted_from = max(start, self.tracking_start())
        with self.db.transaction():
            asset = self.assets.create_certificate_asset(name)
            lines = [PostingLine.units(portfolio.id, asset.id, Decimal(1), amount, Effect.OPENING, amount,
                                       memo=f"Certificate already owned · {name}")]
            txn = self.transactions.post(DocType.OPN, fmt_date(counted_from), lines,
                                         f"Certificate already owned · {name}", portfolio.institution)
            terms = CertificateTerms(
                id=0, account_id=portfolio.id, asset_id=asset.id, name=name,
                start_date=fmt_date(start), lockup_end_date=fmt_date(lockup), maturity_date=fmt_date(maturity),
                principal=amount, annual_rate=rate, interest_method=method, payout_frequency=payout,
                compounding_frequency=compounding, destination_account_id=destination.id,
                purchase_transaction_id=txn.id,
            )
            certificate_id = self.repo.save_certificate(terms)
        return self.certificate(certificate_id), txn

    def update_certificate(self, certificate_id: int, *, name: str, lockup_end_date, maturity_date,
                           annual_rate, interest_method, payout_frequency, compounding_frequency,
                           destination_account_id: int, term_years=""):
        certificate = self.certificate(certificate_id)
        terms = certificate.terms
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a name for this certificate.", "name")
        lockup = parse_date(lockup_end_date, "lockup_end_date")
        start = parse_date(terms.start_date)
        maturity = _maturity_date(start, maturity_date, term_years)
        if not start <= lockup <= maturity:
            raise ValidationError("Earliest withdrawal must be between purchase and maturity.",
                                  "lockup_end_date")
        rate = to_decimal(annual_rate, "annual_rate")
        if not ZERO <= rate <= Decimal("100"):
            raise ValidationError("Annual rate must be between 0 and 100 percent.", "annual_rate")
        method = self._method(interest_method)
        payout = self._payout_frequency(payout_frequency)
        compounding = self._compounding_frequency(compounding_frequency)
        if method == InterestMethod.COMPOUND and payout != PayoutFrequency.AT_MATURITY:
            raise ValidationError("Compound interest is paid at maturity only.", "payout_frequency")
        destination = self._typed_account(destination_account_id, {AccountType.BANK, AccountType.CASH},
                                    "destination_account_id")
        portfolio = self._portfolio(terms.account_id)
        if destination.currency != portfolio.currency:
            raise ValidationError("The payout account must use the CD's currency.", "destination_account_id")
        with self.db.transaction():
            self.repo.set_certificate_terms(
                certificate_id, name=name, lockup_end_date=fmt_date(lockup), maturity_date=fmt_date(maturity),
                annual_rate=rate, interest_method=method, payout_frequency=payout,
                compounding_frequency=compounding, destination_account_id=destination.id,
            )
            self.assets.update_investment(terms.asset_id, name, notes="Certificate of deposit; interest is forecast only.")
        return self.certificate(certificate_id)

    def redeem(self, certificate_id: int, date_value, proceeds, destination_account_id: int):
        """Record the actual whole-CD redemption amount supplied from the bank statement."""
        if self.transactions is None:
            raise RuntimeError("Certificate redemption dependencies are not configured.")
        certificate = self.certificate(certificate_id)
        terms = certificate.terms
        if certificate.redeemed or certificate.units != Decimal(1):
            raise ValidationError("This certificate is no longer available to redeem.")
        day = parse_date(date_value, "date")
        if day < parse_date(terms.lockup_end_date):
            raise ValidationError("The bank's earliest withdrawal date has not arrived.", "date")
        amount = check_places(to_decimal(proceeds, "proceeds"), 2, "proceeds")
        if amount <= ZERO:
            raise ValidationError("Enter the actual amount received from the bank.", "proceeds")
        portfolio = self._portfolio(terms.account_id)
        destination = self._typed_account(destination_account_id, {AccountType.BANK, AccountType.CASH},
                                    "destination_account_id")
        if destination.currency != portfolio.currency:
            raise ValidationError("Choose a destination in the CD's currency.", "destination_account_id")
        cash_asset = self.assets.cash_asset(destination.currency)
        lines = [
            PostingLine.units(portfolio.id, terms.asset_id, Decimal(-1), -amount, Effect.INTERNAL, amount,
                              memo=f"Redeem certificate · {terms.name}"),
            PostingLine.cash(destination.id, cash_asset.id, amount, Effect.INTERNAL,
                             memo=f"Certificate redemption · {terms.name}"),
        ]
        with self.db.transaction():
            txn = self.transactions.post(DocType.SEL, fmt_date(day), lines,
                                         f"Redeem CD · {terms.name}", portfolio.institution)
            self.repo.record_redemption(txn.id, certificate_id, destination.id)
        return txn

    def get(self, account_id: int) -> DepositTerms:
        terms = self.repo.get(account_id)
        if terms is None:
            raise NotFoundError("CD terms were not found.")
        return terms

    def save(self, account_id: int, start_date, maturity_date, principal, annual_rate,
             interest_method, payout_frequency, destination_account_id: int,
             lockup_end_date=None, compounding_frequency="MONTHLY") -> DepositTerms:
        account = self._account(account_id, "DEPOSIT", "deposit account")
        destination = self._account(destination_account_id, None, "destination account")
        if destination.account_type not in {AccountType.BANK, AccountType.CASH}:
            raise ValidationError("Choose an active bank or cash account.", "destination_account_id")
        if destination.id == account.id:
            raise ValidationError("The destination must differ from the CD account.", "destination_account_id")
        if destination.currency != account.currency:
            raise ValidationError("Choose a destination in the same currency as the CD.",
                                  "destination_account_id")

        start = parse_date(start_date, "start_date")
        maturity = parse_date(maturity_date, "maturity_date")
        if start >= maturity:
            raise ValidationError("Maturity must be after the start date.", "maturity_date")
        lockup_end = parse_date(lockup_end_date if lockup_end_date is not None else maturity,
                                "lockup_end_date")
        if not start <= lockup_end <= maturity:
            raise ValidationError("Lockup end must be on or after start and on or before maturity.",
                                  "lockup_end_date")
        amount = to_decimal(principal, "principal")
        if amount <= ZERO:
            raise ValidationError("Enter a principal above zero.", "principal")
        to_e6(amount)
        rate = to_decimal(annual_rate, "annual_rate")
        if not ZERO <= rate <= Decimal("100"):
            raise ValidationError("Annual rate must be between 0 and 100 percent.", "annual_rate")
        try:
            method = InterestMethod(interest_method)
        except (ValueError, TypeError):
            raise ValidationError("Choose SIMPLE or COMPOUND interest.", "interest_method") from None
        try:
            frequency = PayoutFrequency(payout_frequency)
        except (ValueError, TypeError):
            raise ValidationError("Choose a supported payout frequency.", "payout_frequency") from None
        if method == InterestMethod.COMPOUND and frequency != PayoutFrequency.AT_MATURITY:
            raise ValidationError("Compound interest must be paid at maturity.", "payout_frequency")
        try:
            compounding = CompoundingFrequency(compounding_frequency or "MONTHLY")
        except (ValueError, TypeError):
            raise ValidationError("Choose a monthly, quarterly, or yearly compounding frequency.",
                                  "compounding_frequency") from None

        current_owned = Decimal(self.repo.owned_balance_e6(account_id, fmt_date(today()))).scaleb(-6)
        if amount > current_owned:
            raise ValidationError("Principal cannot exceed the CD's currently owned ledger balance.", "principal")
        terms = DepositTerms(account_id, fmt_date(start), fmt_date(lockup_end), fmt_date(maturity),
                             amount, rate, method, frequency, compounding, destination.id)
        with self.db.transaction():
            self.repo.save(terms)
        return terms

    def delete(self, account_id: int) -> None:
        with self.db.transaction():
            self.repo.delete(account_id)

    def future_events(self, as_of, end) -> list[DepositEvent]:
        day, horizon = parse_date(as_of, "as_of"), parse_date(end, "end")
        if horizon <= day:
            return []
        events: list[DepositEvent] = []
        for account in self.accounts.list(active_only=True):
            if account.account_type != AccountType.DEPOSIT:
                continue
            terms = self.repo.get(account.id)
            if terms is None:
                continue
            # The terms are only a cash-flow projection while their principal remains
            # represented by owned ledger cash on the as-of date.
            funded_e6 = self.repo.owned_balance_e6(account.id, fmt_date(day))
            if funded_e6 < to_e6(terms.principal):
                continue
            events.extend(self._events(terms, day, horizon))
        for certificate in self.db.all(
            "SELECT id,account_id,asset_id,name,start_date,lockup_end_date,maturity_date,principal_e6,annual_rate,"
            "interest_method,payout_frequency,compounding_frequency,destination_account_id,"
            "purchase_transaction_id FROM cd_certificates ORDER BY maturity_date,id"
        ):
            item = self.repo.get_certificate(int(certificate["id"]))
            if item is None or item.redeemed or item.units != Decimal(1):
                continue
            events.extend(self._certificate_events(item.terms, day, horizon))
        if self.gameya is not None:
            events.extend(self.gameya.future_events(day, horizon))
        return sorted(events, key=lambda event: (event.date, event.deposit_account_id, event.kind))

    def _certificate_events(self, terms: CertificateTerms, day: date, horizon: date) -> list[DepositEvent]:
        start, maturity = date.fromisoformat(terms.start_date), date.fromisoformat(terms.maturity_date)
        end = min(maturity, horizon)
        if end <= day:
            return []
        principal = terms.principal
        rate = terms.annual_rate / Decimal("100")
        events = []

        def emit(when: date, amount: Decimal, kind: str):
            if day < when <= horizon and amount > ZERO:
                events.append(DepositEvent(fmt_date(when), terms.destination_account_id,
                                           amount.quantize(_MICRO, rounding=ROUND_HALF_UP), kind,
                                           terms.account_id, terms.id))

        if terms.interest_method == InterestMethod.COMPOUND:
            accrued, previous, index = ZERO, start, 1
            step = _COMPOUND_MONTHS[terms.compounding_frequency]
            while True:
                period_end = min(_add_months(start, index * step), maturity)
                full = period_end == _add_months(start, index * step)
                accrued += _period_interest(principal + accrued, rate, previous, period_end, step if full else 0)
                previous = period_end
                if period_end == maturity:
                    break
                index += 1
            emit(maturity, principal + accrued, "MATURITY")
            return events
        previous, index = start, 1
        if terms.payout_frequency == PayoutFrequency.AT_MATURITY:
            emit(maturity, _period_interest(principal, rate, start, maturity, _whole_months(start, maturity)),
                 "INTEREST")
        else:
            step = _MONTHS[terms.payout_frequency]
            while True:
                period_end = min(_add_months(start, index * step), maturity)
                full = period_end == _add_months(start, index * step)
                emit(period_end, _period_interest(principal, rate, previous, period_end, step if full else 0),
                     "INTEREST")
                previous = period_end
                if period_end == maturity:
                    break
                index += 1
        emit(maturity, principal, "PRINCIPAL")
        return events

    def _portfolio(self, account_id: int):
        return self._typed_account(account_id, {AccountType.DEPOSIT}, "account_id")

    def _typed_account(self, account_id: int, allowed: set[AccountType], field: str):
        try:
            account = self.accounts.require_usable(int(account_id), field)
        except (NotFoundError, ValueError, TypeError):
            raise ValidationError("Choose an active account.", field) from None
        if account.account_type not in allowed:
            raise ValidationError("Choose an account of the required type.", field)
        return account

    @staticmethod
    def _method(value) -> InterestMethod:
        try:
            return InterestMethod(value)
        except (ValueError, TypeError):
            raise ValidationError("Choose simple or compound interest.", "interest_method") from None

    @staticmethod
    def _payout_frequency(value) -> PayoutFrequency:
        try:
            return PayoutFrequency(value)
        except (ValueError, TypeError):
            raise ValidationError("Choose a supported payout frequency.", "payout_frequency") from None

    @staticmethod
    def _compounding_frequency(value) -> CompoundingFrequency:
        try:
            return CompoundingFrequency(value or "MONTHLY")
        except (ValueError, TypeError):
            raise ValidationError("Choose monthly, quarterly or yearly compounding.",
                                  "compounding_frequency") from None

    def _events(self, terms: DepositTerms, day: date, horizon: date) -> list[DepositEvent]:
        start = date.fromisoformat(terms.start_date)
        maturity = date.fromisoformat(terms.maturity_date)
        end = min(maturity, horizon)
        if end <= day:
            return []
        principal = terms.principal
        rate = terms.annual_rate / Decimal("100")
        found: list[DepositEvent] = []

        def emit(when: date, amount: Decimal, kind: str) -> None:
            if day < when <= horizon and amount > ZERO:
                found.append(DepositEvent(fmt_date(when), terms.destination_account_id,
                                          amount.quantize(_MICRO, rounding=ROUND_HALF_UP),
                                          kind, terms.account_id))

        if terms.interest_method == InterestMethod.COMPOUND:
            accrued = ZERO
            previous = start
            # Capitalize each selected interval at its anniversary; accrue a final
            # stub to maturity, then round once for the single maturity event.
            index = 1
            months = _COMPOUND_MONTHS[terms.compounding_frequency]
            while True:
                period_end = min(_add_months(start, index * months), maturity)
                accrued += (principal + accrued) * rate * Decimal((period_end - previous).days) / Decimal(365)
                previous = period_end
                if period_end == maturity:
                    break
                index += 1
            emit(maturity, principal + accrued, "MATURITY")
            return found

        previous = start
        if terms.payout_frequency == PayoutFrequency.AT_MATURITY:
            interest = principal * rate * Decimal((maturity - start).days) / Decimal(365)
            emit(maturity, interest, "INTEREST")
        else:
            step = _MONTHS[terms.payout_frequency]
            index = 1
            while True:
                period_end = min(_add_months(start, index * step), maturity)
                interest = principal * rate * Decimal((period_end - previous).days) / Decimal(365)
                emit(period_end, interest, "INTEREST")
                previous = period_end
                if period_end == maturity:
                    break
                index += 1
        emit(maturity, principal, "PRINCIPAL")
        return found

    def _account(self, account_id: int, expected_type: str | None, field: str):
        try:
            account = self.accounts.get(account_id)
        except NotFoundError:
            raise ValidationError("Choose an existing account.", field) from None
        if not account.active:
            raise ValidationError("Choose an active account.", field)
        if expected_type and account.account_type.value != expected_type:
            raise ValidationError("Choose a DEPOSIT account.", field)
        return account


def _whole_months(start: date, end: date) -> int:
    """The number of whole months from start to end, or 0 when end is not a whole number of months away."""
    months = (end.year - start.year) * 12 + end.month - start.month
    return months if months > 0 and _add_months(start, months) == end else 0


def _period_interest(principal: Decimal, rate: Decimal, begin: date, end: date, months: int) -> Decimal:
    """IV-12J2: interest for one payout period the way Egyptian banks pay it. A full period of ``months`` months earns
    principal x rate x months / 12 (a monthly payout is the same every month); a broken period (``months`` 0, shorter
    than its schedule) earns by actual days / 365."""
    if months:
        return principal * rate * Decimal(months) / Decimal(12)
    return principal * rate * Decimal((end - begin).days) / Decimal(365)


def _add_months(start: date, months: int) -> date:
    month_index = start.year * 12 + start.month - 1 + months
    year, zero_month = divmod(month_index, 12)
    month = zero_month + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _maturity_date(start: date, maturity_date, term_years) -> date:
    """Use an explicitly selected date, or calculate one from a term in quarter-years."""
    if str(maturity_date or "").strip():
        return parse_date(maturity_date, "maturity_date")
    if not str(term_years or "").strip():
        raise ValidationError("Choose a maturity date or enter a term in years.", "maturity_date")
    years = to_decimal(term_years, "term_years")
    months = years * 12
    if years < Decimal("0.25") or years > Decimal("100") or months != months.to_integral_value():
        raise ValidationError("Enter a term from 0.25 to 100 years in three-month increments.",
                              "term_years")
    try:
        return _add_months(start, int(months))
    except ValueError:
        raise ValidationError("That term is outside the supported date range.", "term_years") from None
