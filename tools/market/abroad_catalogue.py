"""Rebuild lightning/assets/abroad_instruments.csv, the picker's list of Gulf and European stocks and ETFs, from the
TradingView boards the app already reads for its own prices (lightning/market/sources/tradingview.py; owner
2026-11-04: each app fetches its own Gulf and European prices).

    python -m tools.market.abroad_catalogue [--out lightning/assets/abroad_instruments.csv]

Run it from a machine that can reach TradingView (the Price packs workflow prints it when run with the input
"catalogue"). Prices are in each listing's own currency, in whole units (pence and fils already divided). The same
ticker on two exchanges keeps both rows: the picker tells them apart by exchange.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from lightning.market.http import Polite
from lightning.market.sources import tradingview
from tools.market.us_catalogue import fund_class

ROOT = Path(__file__).resolve().parents[2] / "lightning" / "assets"
HEAD = ["ticker", "name", "kind", "class_code", "source", "source_url", "catalogue_date", "mic", "currency"]
PACKS = ("gcc", "europe")


def rows_from(results, day: str) -> list[list[str]]:
    """CSV rows from each pack's SourceResult: one per ticker and exchange, stocks first, then by name."""
    seen, rows = set(), []
    for pack, result in results:
        for item in result.instruments:
            if (item.ticker, item.mic) in seen or not item.currency:
                continue
            seen.add((item.ticker, item.mic))
            fund = item.category.startswith("FUND")
            board = next(b for b in tradingview.BOARDS[pack] if b.country == item.country)
            rows.append([item.ticker, item.name, "ETFs" if fund else "Stocks", fund_class(item.name) if fund else "STOCK",
                         f"TradingView {board.screener} scanner", tradingview.SCAN.format(screener=board.screener), day,
                         item.mic, item.currency])
    return sorted(rows, key=lambda row: (row[2] != "Stocks", row[1].casefold(), row[7]))


def write(rows, target) -> None:
    writer = csv.writer(target, lineterminator="\n")
    writer.writerow(HEAD)
    writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=ROOT / "abroad_instruments.csv")
    parser.add_argument("--print", action="store_true", help="write the file to standard output instead")
    args = parser.parse_args(argv)
    day = date.today().isoformat()
    session = Polite()
    rows = rows_from([(pack, tradingview.fetch(session, pack, day)) for pack in PACKS], day)
    if args.print:
        write(rows, sys.stdout)
    else:
        with args.out.open("w", encoding="utf-8-sig", newline="") as target:
            write(rows, target)
        print(f"Wrote {len(rows)} instruments to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
