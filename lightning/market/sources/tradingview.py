"""TradingView's screener: every listing on EGX and the Gulf exchanges, and the largest US and European
stocks and ETFs, with their latest close, in one request per board and kind. The request shape is the one
open-source trackers use daily; Gulf and European boards are unverified until the first live run."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from lightning.market.bundle import Instrument, MarketFileError

from ..model import Quote, SourceError, SourceResult

SCAN = "https://scanner.tradingview.com/{screener}/scan"
COLUMNS = ["name", "description", "close", "currency", "type", "subtype", "exchange"]
ALL = 2000  # a whole board, every listing


@dataclass(frozen=True)
class Board:
    """One TradingView screener and the venues taken from it, as ISO 10383 MICs. `stocks` and `etfs` are
    how many, largest first; ALL takes every listing in one request."""
    screener: str
    venues: dict
    country: str                 # ISO 3166 country of the venues: the key's prefix (SA:2222, GB:VOD)
    stocks: int = ALL
    etfs: int = 0
    currencies: tuple = ()       # stocks only: the quote currencies kept (London's own lines, not its order book)


# TradingView reports NYSE Arca listings (most ETFs) as AMEX: an ETF there is ARCX, a share NYSE American.
BOARDS: dict[str, list[Board]] = {
    "egx": [Board("egypt", {"EGX": "XCAI"}, "EG")],
    "us": [Board("america", {"NASDAQ": "XNAS", "NYSE": "XNYS", "AMEX": ""}, "US", stocks=600, etfs=100)],
    "gcc": [Board("ksa", {"TADAWUL": "XSAU"}, "SA"), Board("uae", {"DFM": "XDFM", "ADX": "XADS"}, "AE"),
            Board("qatar", {"QSE": "DSMQ"}, "QA"), Board("kuwait", {"KSE": "XKUW"}, "KW"),
            Board("bahrain", {"BAHRAIN": "XBAH"}, "BH")],  # no Oman: TradingView has no "oman" screener (HTTP 404, 2026-11-04)
    "europe": [Board("uk", {"LSE": "XLON"}, "GB", 350, 100, currencies=("GBX", "GBP")), Board("germany", {"XETR": "XETR"}, "DE", 160, 60),
               Board("france", {"EURONEXT": "XPAR"}, "FR", 120), Board("netherlands", {"EURONEXT": "XAMS"}, "NL", 75, 40),
               Board("belgium", {"EURONEXT": "XBRU"}, "BE", 30), Board("portugal", {"EURONEXT": "XLIS"}, "PT", 20),
               Board("spain", {"BME": "XMAD"}, "ES", 60), Board("italy", {"MIL": "XMIL"}, "IT", 60),
               Board("switzerland", {"SIX": "XSWX"}, "CH", 60),
               Board("sweden", {"OMXSTO": "XSTO"}, "SE", 70), Board("denmark", {"OMXCOP": "XCSE"}, "DK", 40),
               Board("finland", {"OMXHEX": "XHEL"}, "FI", 40), Board("iceland", {"OMXICE": "XICE"}, "IS", 20)],
}
# Prices quoted in a currency's minor unit are published in the ISO 4217 unit: pence, fils.
MINOR = {"GBX": ("GBP", Decimal(100)), "KWF": ("KWD", Decimal(1000)), "ZAC": ("ZAR", Decimal(100)),
         "ILA": ("ILS", Decimal(100))}


def query(board: Board, kind: str) -> dict:
    """The screener request: a whole board by name, or its largest stocks or ETFs."""
    venue = [{"left": "exchange", "operation": "in_range", "right": sorted(board.venues)}]
    if kind == "all":
        return {"columns": COLUMNS, "filter": venue, "range": [0, ALL], "sort": {"sortBy": "name", "sortOrder": "asc"}}
    if kind == "stocks":
        priced = [{"left": "currency", "operation": "in_range", "right": list(board.currencies)}] if board.currencies else []
        return {"columns": COLUMNS, "filter": venue + [
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
            {"left": "subtype", "operation": "nequal", "right": "preferred"}] + priced,
            "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "range": [0, board.stocks]}
    return {"columns": COLUMNS, "filter": venue + [
        {"left": "type", "operation": "equal", "right": "fund"}, {"left": "subtype", "operation": "equal", "right": "etf"}],
        "sort": {"sortBy": "aum", "sortOrder": "desc"}, "range": [0, board.etfs]}


def _decimal(value) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def parse(data: dict, board: Board, day: str, source: str) -> SourceResult:
    """One screener answer as instruments and closes dated `day` (the trading day the run is for)."""
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise SourceError("TradingView's screener answered without its data list")
    result = SourceResult(source)
    for row in data["data"]:
        try:
            symbol, values = row["s"], dict(zip(COLUMNS, row["d"]))
        except (KeyError, TypeError):
            continue
        exchange, _, ticker = str(symbol).partition(":")
        close = _decimal(values.get("close"))
        if not ticker or close is None or exchange not in board.venues or values.get("type") not in ("stock", "fund", "dr"):
            continue
        is_fund = values.get("type") == "fund"
        mic = board.venues[exchange] or ("ARCX" if is_fund else "XASE")
        currency = str(values.get("currency") or "").upper()
        if currency in MINOR:
            currency, per_unit = MINOR[currency]
            close = (close / per_unit).normalize()
        instrument = Instrument(
            key=f"{board.country}:{ticker.upper()}", name=" ".join(str(values.get("description") or ticker).split()),
            ticker=ticker.upper(), mic=mic, country=board.country, currency=currency,
            category="FUND.OTHER" if is_fund else "STOCK", unit="unit" if is_fund else "share",
            sources={"tradingview": symbol})
        try:
            instrument.check()
        except MarketFileError:
            continue  # a ticker the published key form cannot hold is left out, never mangled
        result.instruments.append(instrument)
        result.quotes.append(Quote(instrument.key, day, close, source))
    return result


def fetch(session, pack: str, day: str, countries=None) -> SourceResult:
    """Every board of a pack, merged; a board that fails fails the pack's source (its last prices stay). The app
    asks only the boards of the countries it holds (`countries`), each still whole, so a request never names a
    holding."""
    result = SourceResult(f"tradingview-{pack}")
    for board in BOARDS[pack]:
        if countries is not None and board.country not in countries:
            continue
        url = SCAN.format(screener=board.screener)
        kinds = ["all"] if board.stocks == ALL else ["stocks"] + (["etfs"] if board.etfs else [])
        for kind in kinds:
            part = parse(session.post_json(url, query(board, kind)), board, day, result.source)
            result.instruments += part.instruments
            result.quotes += part.quotes
    return result
