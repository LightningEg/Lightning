"""Propose links from the picker's Thndr funds (lightning/assets/egx_instruments.csv) to Mubasher's fund numbers, for
a person to review into lightning/assets/fund_links.csv (NF-6A1).

    python -m tools.market.fund_links [--sample mubasher_funds.json]

Prints one CSV row per catalogue fund: its ticker and name, how it matched (exact: the one Mubasher fund with the same
name; near: up to three nearest names; none), and each candidate's number and name. Nothing is written: a link
decides which prices fill a holding, so only a reviewed row goes into fund_links.csv. Run it from a machine that can
reach Mubasher (the Price packs workflow prints it when run with the input "fund-links").
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import sys
from pathlib import Path

from lightning.assets.catalog import instruments
from lightning.market.sources import mubasher
from lightning.workflows.live_prices import fund_name

HEAD = ["ticker", "name", "match", "mubasher_id", "mubasher_name"]


def proposals(funds, catalogue) -> list[list[str]]:
    """One row per candidate: exact when one Mubasher fund has the same name, else the nearest three (or none)."""
    by_name: dict[str, list] = {}
    for item in funds:
        by_name.setdefault(fund_name(item.name), []).append(item)
    rows = []
    for record in catalogue:
        if record.get("kind") != "Fund":
            continue
        own = fund_name(record["name"])
        same = by_name.get(own, [])
        if len(same) == 1:
            found, match = same, "exact"
        else:
            near = difflib.get_close_matches(own, list(by_name), n=3, cutoff=0.5) if not same else [own]
            found, match = [item for name in near for item in by_name[name]], "near" if near else "none"
        for item in found or [None]:
            rows.append([record["ticker"], record["name"], match,
                         item.sources.get("mubasher", "") if item else "", item.name if item else ""])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sample", type=Path, help="a saved answer of Mubasher's fund list, instead of asking it")
    args = parser.parse_args(argv)
    if args.sample:
        funds = mubasher.parse_funds(json.loads(args.sample.read_text(encoding="utf-8"))).instruments
    else:
        from lightning.market.http import Polite
        funds = mubasher.fetch(Polite()).instruments
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(HEAD)
    writer.writerows(proposals(funds, instruments()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
