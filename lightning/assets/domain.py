"""Financial assets — WHAT wealth consists of — and the asset-class tree."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Exposure(StrEnum):
    CASH = "CASH"
    EQUITY = "EQUITY"
    GOLD = "GOLD"
    FIXED_INCOME = "FIXED_INCOME"
    REAL_ESTATE = "REAL_ESTATE"
    OTHER = "OTHER"


class Liquidity(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    DAYS = "DAYS"
    LOCKED = "LOCKED"


class PriceSource(StrEnum):
    YAHOO = "YAHOO"
    GOLD_CALC = "GOLD_CALC"
    GOLD_LOCAL = "GOLD_LOCAL"
    MANUAL = "MANUAL"
    NONE = "NONE"


@dataclass
class AssetClass:
    id: int
    code: str  # dotted path, e.g. FUND.GOLD
    name: str
    parent_id: int | None
    sort_order: int
    active: bool

    @property
    def root_code(self) -> str:
        return self.code.split(".", 1)[0]

    @property
    def depth(self) -> int:
        return self.code.count(".")

    @property
    def label(self) -> str:
        return f"{self.code} · {self.name}"


@dataclass
class FinancialAsset:
    id: int
    code: str  # CLASS:SYMBOL, e.g. STK:COMI, CASH:EGP
    name: str
    asset_class_id: int
    currency: str
    unit: str
    quantity_decimals: int
    is_cash: bool
    exposure: Exposure
    liquidity: Liquidity
    purity: Decimal | None
    isin: str | None
    price_source: PriceSource
    external_symbol: str | None
    active: bool
    notes: str
    mic: str | None = None         # ISO 10383 venue, e.g. XCAI (the Egyptian Exchange)
    country: str | None = None     # ISO 3166 alpha-2, e.g. EG
    market_key: str | None = None  # its instrument in the market file, e.g. EG:COMI

    @property
    def label(self) -> str:
        return f"{self.code} · {self.name}"

    @property
    def ticker(self) -> str:
        """The symbol after the class prefix: STK:COMI -> COMI."""
        return self.code.split(":", 1)[-1]

    @property
    def exchange(self) -> str:
        """The venue's common name: XCAI -> EGX; '' when it does not trade on an exchange."""
        from lightning.market.iso import venue_name
        return venue_name(self.mic)


@dataclass(frozen=True)
class InvestmentKind:
    """Defaults for a new investment of a given asset class."""

    prefix: str  # code prefix, e.g. STK in STK:COMI
    unit: str
    quantity_decimals: int
    exposure: Exposure
    liquidity: Liquidity


# Asset classes you can create investments in, with sensible defaults.
INVESTMENT_KINDS: dict[str, InvestmentKind] = {
    "STOCK": InvestmentKind("STK", "share", 0, Exposure.EQUITY, Liquidity.DAYS),
    "FUND.EQUITY": InvestmentKind("FND", "unit", 4, Exposure.EQUITY, Liquidity.DAYS),
    "FUND.MONEY_MARKET": InvestmentKind("FND", "unit", 4, Exposure.FIXED_INCOME, Liquidity.DAYS),
    "FUND.FIXED_INCOME": InvestmentKind("FND", "unit", 4, Exposure.FIXED_INCOME, Liquidity.DAYS),
    "FUND.GOLD": InvestmentKind("FND", "unit", 4, Exposure.GOLD, Liquidity.DAYS),
    "FUND.OTHER": InvestmentKind("FND", "unit", 4, Exposure.OTHER, Liquidity.DAYS),
    "GOLD": InvestmentKind("GLD", "gram", 3, Exposure.GOLD, Liquidity.DAYS),
    # Silver is bought by the gram and priced by hand (NF-9C1); no price source feeds it yet.
    "SILVER": InvestmentKind("SLV", "gram", 3, Exposure.OTHER, Liquidity.DAYS),
    "OTHER": InvestmentKind("OTH", "unit", 4, Exposure.OTHER, Liquidity.DAYS),
}

EXPOSURE_LABELS = {
    Exposure.CASH: "Cash", Exposure.EQUITY: "Equity", Exposure.GOLD: "Gold",
    Exposure.FIXED_INCOME: "Fixed income", Exposure.REAL_ESTATE: "Real estate", Exposure.OTHER: "Other",
}


@dataclass
class Price:
    asset_id: int
    date: str
    price: Decimal
    currency: str
    source: str  # MANUAL (typed), later YAHOO / GOLD_CALC ...
