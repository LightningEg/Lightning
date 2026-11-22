"""Read the bundled picker catalogue: EGX stocks and Thndr funds, the largest US stocks and ETFs, and the Gulf and
European listings the app prices itself (tools/market/abroad_catalogue.py)."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path


CATALOGUE_FILE = Path(__file__).with_name("egx_instruments.csv")
US_CATALOGUE_FILE = Path(__file__).with_name("us_instruments.csv")
ABROAD_CATALOGUE_FILE = Path(__file__).with_name("abroad_instruments.csv")


def _read(path: Path, mic: str, currency: str) -> list[dict[str, str]]:
    """Records of one file; a file without exchange and currency columns gets the given defaults."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        records = list(csv.DictReader(source))
    for row in records:
        row["mic"] = row.get("mic") or (mic if row.get("class_code") == "STOCK" else "")
        row["currency"] = row.get("currency") or currency
    return records


@lru_cache(maxsize=1)
def instruments() -> list[dict[str, str]]:
    """Return searchable instrument records from the local, versioned CSV files (stocks first, by name)."""
    records = _read(CATALOGUE_FILE, "XCAI", "EGP") + _read(US_CATALOGUE_FILE, "", "USD")
    if ABROAD_CATALOGUE_FILE.exists():
        records += _read(ABROAD_CATALOGUE_FILE, "", "")
    return sorted(records, key=lambda row: (row["kind"] != "Stocks", row["name"].casefold()))


FUND_LINKS_FILE = Path(__file__).with_name("fund_links.csv")


@lru_cache(maxsize=1)
def fund_links() -> dict[str, str]:
    """Reviewed Thndr fund tickers -> Mubasher fund numbers (NF-6A1). Only a row a person checked against Mubasher's
    list is in the file (tools/market/fund_links.py proposes them); a fund not in it is still matched by its name."""
    if not FUND_LINKS_FILE.exists():
        return {}
    with FUND_LINKS_FILE.open(encoding="utf-8-sig", newline="") as source:
        return {row["ticker"].strip().upper(): row["mubasher_id"].strip() for row in csv.DictReader(source)
                if row.get("ticker", "").strip() and row.get("mubasher_id", "").strip().isdigit()}
