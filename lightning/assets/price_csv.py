"""Many prices from one spreadsheet file (PC roadmap P6).

A CSV with a column naming the investment (symbol, ISIN or name), an optional date column and a price
column. Each row matches one active investment; rows that match none are reported, never guessed.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

NAME_KEYS = ("symbol", "ticker", "isin", "investment", "name", "asset")
DATE_KEYS = ("date", "day", "as of", "as_of")
PRICE_KEYS = ("price", "close", "last", "value", "nav")


@dataclass
class PriceRows:
    matched: list[tuple[int, str, Decimal]] = field(default_factory=list)  # asset id, date, price
    unmatched: list[str] = field(default_factory=list)
    bad: list[str] = field(default_factory=list)


def _pick(headers: list[str], keys: tuple[str, ...]) -> str | None:
    lowered = {h.strip().casefold(): h for h in headers}
    return next((lowered[k] for k in keys if k in lowered), None)


def read_prices(data: bytes, assets, default_day: str) -> PriceRows:
    """assets: objects with id, name, ticker/symbol and isin. Dates must be YYYY-MM-DD."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    name_col, price_col, date_col = _pick(headers, NAME_KEYS), _pick(headers, PRICE_KEYS), _pick(headers, DATE_KEYS)
    if not name_col or not price_col:
        raise ValueError("The file needs a column naming the investment (Symbol, ISIN or Name) and a Price column.")
    index: dict[str, int] = {}
    for asset in assets:
        for key in (getattr(asset, "ticker", None), getattr(asset, "symbol", None), getattr(asset, "isin", None),
                    asset.name):
            if key:
                index.setdefault(str(key).strip().casefold(), asset.id)
    out = PriceRows()
    for row in reader:
        name = (row.get(name_col) or "").strip()
        if not name:
            continue
        raw = (row.get(price_col) or "").replace(",", "").strip()
        day = ((row.get(date_col) or "").strip() if date_col else "") or default_day
        try:
            price = Decimal(raw)
            if price <= 0 or len(day) != 10 or day[4] != "-" or day[7] != "-":
                raise InvalidOperation
        except InvalidOperation:
            out.bad.append(name)
            continue
        asset_id = index.get(name.casefold())
        if asset_id is None:
            out.unmatched.append(name)
        else:
            out.matched.append((asset_id, day, price))
    return out
