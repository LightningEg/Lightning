from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class InterestMethod(StrEnum):
    SIMPLE = "SIMPLE"
    COMPOUND = "COMPOUND"


class PayoutFrequency(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"
    AT_MATURITY = "AT_MATURITY"


class CompoundingFrequency(StrEnum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"


class GameyaFrequency(StrEnum):
    MONTHLY = "MONTHLY"  # the enum leaves room for WEEKLY


@dataclass(frozen=True)
class DepositTerms:
    account_id: int
    start_date: str
    lockup_end_date: str
    maturity_date: str
    principal: Decimal
    annual_rate: Decimal  # percentage points: Decimal("18") means 18% per year
    interest_method: InterestMethod
    payout_frequency: PayoutFrequency
    compounding_frequency: CompoundingFrequency
    destination_account_id: int


@dataclass(frozen=True)
class CertificateTerms:
    id: int
    account_id: int
    asset_id: int
    name: str
    start_date: str
    lockup_end_date: str
    maturity_date: str
    principal: Decimal
    annual_rate: Decimal
    interest_method: InterestMethod
    payout_frequency: PayoutFrequency
    compounding_frequency: CompoundingFrequency
    destination_account_id: int
    purchase_transaction_id: int


@dataclass(frozen=True)
class Certificate:
    terms: CertificateTerms
    units: Decimal
    redeemed: bool


@dataclass(frozen=True)
class DepositEvent:
    date: str
    account_id: int
    amount: Decimal
    kind: str
    deposit_account_id: int
    certificate_id: int | None = None
    # "CD" for certificates, "GAMEYA" for a savings circle (kinds INSTALLMENT, PAYOUT, INTEREST; an
    # instalment is a negative amount leaving its funding account).
    source: str = "CD"


@dataclass(frozen=True)
class GameyaTerms:
    """One rotating savings circle, held in one GAMEYA account (the account-level shape of ``cd_terms``)."""
    account_id: int
    organiser: str
    members: int
    installment: Decimal
    frequency: GameyaFrequency
    first_date: str
    my_turn: int
    payout: Decimal
    annual_rate: Decimal  # percentage points; 0 means no interest
    funding_account_id: int
    payout_account_id: int

    @property
    def pot(self) -> Decimal:
        """What one turn collects: every member's instalment."""
        return self.installment * self.members
