"""Transactions — WHAT HAPPENED.

A transaction is the document the user sees (one transfer = one transaction).
Its ledger lines record the effect on accounts and assets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from lightning.core.ledger import Effect
from lightning.core.refs import DOC_LABELS, DocType, line_ref


class TxnStatus(StrEnum):
    POSTED = "POSTED"
    VOID = "VOID"


class TxnSource(StrEnum):
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"
    MARKET_DATA = "MARKET_DATA"
    SYSTEM = "SYSTEM"


@dataclass
class LedgerLine:
    id: int
    transaction_id: int
    line_no: int
    date: str
    account_id: int
    asset_id: int
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    fx_rate: Decimal
    amount_base: Decimal
    effect: Effect
    category_id: int | None
    memo: str
    owner_id: int | None = None


@dataclass
class Transaction:
    id: int
    ref: str
    type: DocType
    date: str  # yyyy-mm-dd
    description: str
    counterparty: str
    status: TxnStatus
    source: TxnSource
    notes: str
    created_at: str
    updated_at: str
    lines: list[LedgerLine] = field(default_factory=list)

    @property
    def type_label(self) -> str:
        return DOC_LABELS[self.type]

    @property
    def is_void(self) -> bool:
        return self.status == TxnStatus.VOID

    def line_ref(self, line: LedgerLine) -> str:
        return line_ref(self.ref, line.line_no)


@dataclass
class TxnSummary:
    """A transaction as a person reads it — one row in a list."""

    id: int
    ref: str
    date: str
    type: DocType
    type_label: str
    status: TxnStatus
    description: str
    counterparty: str
    notes: str
    amount: Decimal  # money in +, money out -, transfers shown positive
    currency: str
    account_label: str  # the account (or "from" account for transfers)
    to_account_label: str  # transfers only
    category_label: str  # plain names, e.g. "Personal › Food & Groceries"
    category_code: str  # e.g. EXP.PERSONAL.FOOD (search, exports)
    account_id: int | None
    to_account_id: int | None
    category_id: int | None
    to_amount: Decimal = Decimal(0)  # conversions only: what arrived, in `to_currency`
    to_currency: str = ""
    rate: Decimal | None = None      # conversions only: the executed rate


@dataclass
class TxnFilter:
    search: str = ""
    account_id: int | None = None
    category_ids: list[int] | None = None
    types: list[DocType] | None = None
    date_from: str | None = None
    date_to: str | None = None
    include_void: bool = False
    limit: int = 200
    offset: int = 0
    category_labels: dict[int, str] | None = None
