"""Which price wins when one day holds several (NF-5F): one written order, used by every price lookup.

A price you typed beats everything else that day; a buy or sell price beats a price from the market pack or an online
quote; what a holding cost is the last resort and is never stored here. A newer day always beats an older one whatever
its source (the pack's price from yesterday beats a price you typed last month)."""

from __future__ import annotations

SOURCE_RANK = ("MANUAL", "REEVALUATION_MANUAL", "TRADE", "MARKET", "ONLINE", "GAMEYA", "COST")


def source_rank(source: str) -> int:
    """Lower wins. A source nobody listed ranks just before COST."""
    try:
        return SOURCE_RANK.index(source)
    except ValueError:
        return len(SOURCE_RANK) - 1
