"""Broker statements (NF-5G5, owner 2026-11-04: Interactive Brokers first): read an IBKR Activity Statement CSV,
show what it will record, post it into the broker's currency pockets, and check its open positions against the
ledger.

An Activity Statement is one CSV of sections. Each line starts with the section's name and a kind: "Header" gives
the columns for the "Data" lines after it (a section may change its columns, so the latest header is used), and
"Total" or "SubTotal" lines are skipped. The sections read here:

    Statement             the period, whose last day dates the positions check
    Trades                shares and ETFs (bought: positive quantity), and currency conversions (Asset Category Forex,
                          Symbol EUR.USD: euros bought with dollars)
    Dividends             the gross dividend; Withholding Tax, the tax taken from it (negative)
    Interest, Fees        interest on cash, and the broker's own charges
    Deposits & Withdrawals money moved in or out: recorded from your bank's side, so listed, not posted
    Financial Instrument Information   each symbol's name, listing exchange and type
    Open Positions        the units held at the end, checked against the ledger

Each row becomes one ledger event in the pocket of its currency (made on demand). Every posted event carries
"IBKR <reference>" in its notes, the reference being a hash of the row, so importing the same statement, or one
that overlaps it, records nothing twice. A row that cannot be posted (no exchange rate for its day, for example)
is reported and the rest are posted; importing again after fixing it posts only what is missing. On a synchronized
profile every row is an ordinary journal command (investments.buy_total, transactions.record_conversion, ...),
confirmed at once on the home device, which is the only device that runs an import.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from lightning.accounts.domain import AccountType
from lightning.core.errors import LightningError, ValidationError
from lightning.core.money import ZERO

# IBKR's listing exchange -> ISO 10383 MIC (the exchanges Lightning prices; anything else keeps no MIC).
EXCHANGES = {"NASDAQ": "XNAS", "NYSE": "XNYS", "ARCA": "ARCX", "AMEX": "XASE", "BATS": "BATS", "LSE": "XLON",
             "LSEETF": "XLON", "IBIS": "XETR", "IBIS2": "XETR", "FWB": "XETR", "SBF": "XPAR", "AEB": "XAMS",
             "ENEXT.BE": "XBRU", "BVL": "XLIS", "BM": "XMAD", "BVME": "XMIL", "BVME.ETF": "XMIL", "EBS": "XSWX",
             "SFB": "XSTO", "CPH": "XCSE", "HEX": "XHEL", "TADAWUL": "XSAU", "DFM": "XDFM", "ADX": "XADS",
             "QE": "DSMQ", "KSE": "XKUW"}
MARK = "IBKR"
NUMBER_FIELDS = ("Quantity", "Proceeds", "Amount")


def _number(text) -> Decimal:
    try:
        return Decimal(str(text or "0").replace(",", "").strip() or "0")
    except InvalidOperation:
        raise ValidationError(f"“{text}” is not a number in the statement.", "file") from None


def _day(text: str) -> str:
    """'2026-09-03, 10:15:02', '2026-09-03' or '20260903' -> '2026-09-03'."""
    text = str(text or "").split(",")[0].strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValidationError(f"“{text}” is not a date in the statement.", "file")


@dataclass
class Event:
    kind: str                 # buy, sell, convert, dividend, interest, fee, deposit, withdrawal
    date: str
    currency: str
    amount: Decimal           # cash, in `currency`: paid for a buy, received for a sale, the gross dividend
    symbol: str = ""
    quantity: Decimal = ZERO  # units; for a conversion, the amount of `to_currency` bought (negative: sold)
    fee: Decimal = ZERO       # commission, in `fee_currency`
    fee_currency: str = ""
    tax: Decimal = ZERO       # dividend tax withheld
    to_currency: str = ""     # a conversion's other currency
    text: str = ""
    reference: str = ""

    @property
    def note(self) -> str:
        return f"{MARK} {self.reference}"


@dataclass
class Instrument:
    symbol: str
    name: str
    mic: str
    fund: bool


@dataclass
class Statement:
    events: list[Event] = field(default_factory=list)
    instruments: dict[str, Instrument] = field(default_factory=dict)
    positions: dict[tuple[str, str], Decimal] = field(default_factory=dict)   # (symbol, currency) -> units
    period_end: str = ""


def _reference(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def read_ibkr(data: bytes) -> Statement:
    """An IBKR Activity Statement CSV as events, instruments and positions (see the module's notes)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("The statement is not a UTF-8 CSV file. Download it again as CSV.", "file") from None
    headers: dict[str, list[str]] = {}
    statement = Statement()
    taxes: dict[tuple[str, str, str], Decimal] = {}
    seen = False
    for line in csv.reader(io.StringIO(text)):
        if len(line) < 3:
            continue
        section, kind, values = line[0].strip(), line[1].strip(), line[2:]
        if kind == "Header":
            headers[section] = [v.strip() for v in values]
            continue
        if kind != "Data" or section not in headers:
            continue
        seen = True
        row = dict(zip(headers[section], (v.strip() for v in values)))
        if section == "Statement" and row.get("Field Name") == "Period":
            end = (row.get("Field Value") or "").split(" - ")[-1].strip()
            try:
                statement.period_end = datetime.strptime(end, "%B %d, %Y").date().isoformat()
            except ValueError:
                pass
        elif section == "Financial Instrument Information":
            symbol = row.get("Symbol", "")
            if symbol:
                statement.instruments[symbol] = Instrument(
                    symbol, row.get("Description") or symbol, EXCHANGES.get((row.get("Listing Exch") or "").upper(), ""),
                    row.get("Asset Category") == "Stocks" and (row.get("Type") or "").upper() == "ETF")
        elif section == "Trades":
            _trade(statement, row)
        elif section in ("Dividends", "Withholding Tax", "Interest", "Fees", "Deposits & Withdrawals"):
            currency = row.get("Currency", "")
            if not currency or currency.startswith("Total"):
                continue
            day = _day(row.get("Date") or row.get("Settle Date"))
            amount, description = _number(row.get("Amount")), row.get("Description", "")
            symbol = description.split("(")[0].strip() if section in ("Dividends", "Withholding Tax") else ""
            if section == "Withholding Tax":
                taxes[(day, symbol, currency)] = taxes.get((day, symbol, currency), ZERO) - amount
                continue
            if section == "Dividends":
                kind_ = "dividend"
            elif section == "Interest":
                kind_ = "interest" if amount > 0 else "fee"
            elif section == "Fees":
                kind_ = "fee" if amount < 0 else "interest"
            else:
                kind_ = "deposit" if amount > 0 else "withdrawal"
            statement.events.append(Event(kind_, day, currency, abs(amount), symbol=symbol, text=description,
                                          reference=_reference(section, day, currency, description, amount)))
        elif section == "Open Positions" and row.get("DataDiscriminator") in ("Summary", ""):
            if row.get("Asset Category") in ("Stocks", "Funds") and row.get("Symbol"):
                key = (row["Symbol"], row.get("Currency", ""))
                statement.positions[key] = statement.positions.get(key, ZERO) + _number(row.get("Quantity"))
    if not seen:
        raise ValidationError("This is not an Interactive Brokers activity statement: it has no Header and Data lines.",
                              "file")
    for event in statement.events:
        if event.kind == "dividend":
            event.tax = taxes.pop((event.date, event.symbol, event.currency), ZERO)
    statement.events.sort(key=lambda e: (e.date, ["deposit", "convert", "buy", "sell", "dividend", "interest", "fee",
                                                  "withdrawal"].index(e.kind)))
    return statement


def _trade(statement: Statement, row: dict) -> None:
    if row.get("DataDiscriminator") not in ("Order", "Trade", None):
        return
    category, symbol, currency = row.get("Asset Category", ""), row.get("Symbol", ""), row.get("Currency", "")
    quantity, proceeds = _number(row.get("Quantity")), _number(row.get("Proceeds"))
    fee_column = next((k for k in row if k.startswith("Comm")), "")
    fee = abs(_number(row.get(fee_column)))
    fee_currency = fee_column.rsplit(" ", 1)[-1] if fee_column.startswith("Comm in ") else currency
    day = _day(row.get("Date/Time"))
    reference = _reference("Trades", category, symbol, row.get("Date/Time"), quantity, proceeds)
    if category == "Forex":
        bought, _, paid_in = symbol.partition(".")
        statement.events.append(Event("convert", day, paid_in or currency, -proceeds, quantity=quantity, fee=fee,
                                      fee_currency=fee_currency, to_currency=bought, text=symbol, reference=reference))
    elif category in ("Stocks", "Funds") and quantity:
        kind = "buy" if quantity > 0 else "sell"
        statement.events.append(Event(kind, day, currency, abs(proceeds), symbol=symbol, quantity=abs(quantity), fee=fee,
                                      fee_currency=fee_currency, reference=reference))


@dataclass
class Row:
    event: Event
    status: str               # new, imported, listed (deposits), problem
    message: str = ""


@dataclass
class Preview:
    rows: list[Row]
    currencies: list[str]
    new_instruments: list[str]

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r.status == status)


class BrokerImport:
    """Posts a read statement into one broker account (and its pockets) through the investment services."""

    def __init__(self, c):
        self.c = c

    def _broker(self, account_id: int):
        account = self.c.accounts.get(account_id)
        if account.account_type != AccountType.BROKERAGE:
            raise ValidationError("Import a broker statement into a brokerage account.", "account")
        return self.c.accounts.broker_of(account)

    def _imported(self, event: Event) -> bool:
        return self.c.db.scalar("SELECT 1 FROM transactions WHERE status<>'VOID' AND notes LIKE ? LIMIT 1",
                                (f"%{event.note}%",)) is not None

    def _asset(self, statement: Statement, symbol: str, currency: str, create: bool):
        info = statement.instruments.get(symbol) or Instrument(symbol, symbol, "", False)
        ticker = symbol.replace(" ", ".").upper()
        for asset in self.c.assets.investments():
            code = asset.code.split(":", 1)[-1]
            if code in (ticker, f"{ticker}-{info.mic}") and asset.currency == currency and (
                    not info.mic or not asset.mic or asset.mic == info.mic):
                return asset
        if not create:
            return None
        return self.c.assets.create_investment(info.name, "FUND.EQUITY" if info.fund else "STOCK", ticker,
                                               mic=info.mic, currency=currency)

    def preview(self, account_id: int, statement: Statement) -> Preview:
        self._broker(account_id)
        rows, new = [], []
        for event in statement.events:
            if event.kind in ("deposit", "withdrawal"):
                rows.append(Row(event, "listed", "Record it from your bank's side, as a transfer to this broker."))
            elif self._imported(event):
                rows.append(Row(event, "imported"))
            else:
                if event.symbol and self._asset(statement, event.symbol, event.currency, False) is None \
                        and event.symbol not in new:
                    new.append(event.symbol)
                rows.append(Row(event, "new"))
        currencies = sorted({e.currency for e in statement.events} | {e.to_currency for e in statement.events if e.to_currency})
        return Preview(rows, currencies, new)

    def post(self, account_id: int, statement: Statement) -> Preview:
        """Record every new row; returns the rows with what happened to each. On a synchronized profile each row is
        its own command, confirmed at once on the home, so the import runs there only."""
        broker = self._broker(account_id)
        if getattr(self.c, "is_journal", False) and not self.c.history_is_home:
            raise ValidationError("Import broker statements on your home device; it records them for every device.",
                                  "file")
        done = []
        for row in self.preview(account_id, statement).rows:
            if row.status != "new":
                done.append(row)
                continue
            try:
                self._post(broker, statement, row.event)
                done.append(Row(row.event, "posted"))
            except LightningError as exc:
                done.append(Row(row.event, "problem", exc.message))
        return Preview(done, [], [])

    def _pocket(self, broker, currency: str):
        """The broker's pocket in `currency`, added through accounts.add_pocket (a journal command) when missing."""
        return self.c.accounts.pocket_for(broker, currency) or self.c.accounts.add_pocket(broker.id, currency)

    def _post(self, broker, statement: Statement, e: Event) -> None:
        inv, note = self.c.investments, e.note
        if e.kind == "convert":
            paying, bought = self._pocket(broker, e.currency), self._pocket(broker, e.to_currency)
            if e.quantity > 0:   # bought `to_currency` with `currency`
                sent, received, src, dst = e.amount, e.quantity, paying, bought
            else:
                sent, received, src, dst = -e.quantity, -e.amount, bought, paying
            fee_here = e.fee if e.fee and e.fee_currency == src.currency else None
            self.c.transactions.record_conversion(e.date, src.id, dst.id, sent, received, fee=fee_here,
                                                  description=f"Converted {e.text}", notes=note)
            if e.fee and fee_here is None:
                inv.broker_fee(e.date, self._pocket(broker, e.fee_currency).id, e.fee, notes=note)
            return
        pocket = self._pocket(broker, e.currency)
        if e.kind in ("buy", "sell"):
            asset = self._asset(statement, e.symbol, e.currency, True)
            fee_here = e.fee if e.fee_currency in ("", e.currency) else ZERO
            if e.kind == "buy":
                inv.buy_total(e.date, pocket.id, asset.id, e.quantity, e.amount + fee_here, fees=fee_here,
                              fees_included=True, notes=note)
            else:
                inv.sell_total(e.date, pocket.id, asset.id, e.quantity, e.amount - fee_here, fees=fee_here,
                               fees_included=True, notes=note)
            if e.fee and not fee_here:
                inv.broker_fee(e.date, self._pocket(broker, e.fee_currency).id, e.fee, notes=note)
        elif e.kind == "dividend":
            asset = self._asset(statement, e.symbol, e.currency, False)
            if asset is None:
                raise ValidationError(f"No holding of {e.symbol} to pay this dividend.", "asset")
            inv.dividend(e.date, pocket.id, asset.id, e.amount, notes=note, tax=e.tax)
        elif e.kind == "interest":
            inv.broker_interest(e.date, pocket.id, e.amount, notes=note)
        elif e.kind == "fee":
            inv.broker_fee(e.date, pocket.id, e.amount, notes=note)

    def check_positions(self, account_id: int, statement: Statement) -> list[dict]:
        """Each open position against the units the ledger holds in that currency's pocket on the statement's last
        day: [{symbol, currency, statement, ledger, matches}]."""
        broker = self._broker(account_id)
        day = statement.period_end or max((e.date for e in statement.events), default="")
        out = []
        for (symbol, currency), units in sorted(statement.positions.items()):
            pocket = self.c.accounts.pocket_for(broker, currency)
            asset = self._asset(statement, symbol, currency, False)
            held = self.c.investments.holding(pocket.id, asset.id, day) if pocket and asset else ZERO
            out.append({"symbol": symbol, "currency": currency, "statement": units, "ledger": held,
                        "matches": held == units})
        return out
