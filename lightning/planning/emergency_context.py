"""Display-only context for what else may be reachable during an emergency.

This never changes the emergency-fund amount, Position.free_cash or a forecast. Only money
market funds have a known days-to-reach classification here; other holdings stay unknown.
"""
from __future__ import annotations

from lightning.core.money import ZERO


MONEY_MARKET_CLASS = "FUND.MONEY_MARKET"


def emergency_liquidity_context(position) -> dict:
    """Describe free cash and holdings by known access timing without valuing unknown liquidity."""
    within_days: dict[str, dict] = {}
    locked: list[dict] = []
    unknown: dict[str, dict] = {}

    def group(groups: dict, label: str) -> dict:
        return groups.setdefault(label, {"label": label, "value": ZERO, "unvalued": 0})

    for asset_class in position.classes:
        for item in asset_class.items:
            value = item.value
            if getattr(item, "counts_as_cash", False):
                continue  # NF-7AU: already inside Free cash, never listed twice
            if item.locked_until:
                locked.append({"label": item.asset, "value": value, "until": item.locked_until})
            elif item.class_code == MONEY_MARKET_CLASS:
                row = group(within_days, asset_class.name)
                if value is None:
                    row["unvalued"] += 1
                else:
                    row["value"] += value
            else:
                row = group(unknown, asset_class.name)
                if value is None:
                    row["unvalued"] += 1
                else:
                    row["value"] += value

    def rows(groups: dict) -> list[dict]:
        return [row | {"value": row["value"] if row["value"] or not row["unvalued"] else None}
                for row in sorted(groups.values(), key=lambda item: item["label"].casefold())
                if row["value"] or row["unvalued"]]

    return {
        "free_cash": position.free_cash,
        "within_days": rows(within_days),
        "locked": sorted(locked, key=lambda item: (item["until"], item["label"].casefold())),
        "unknown": rows(unknown),
    }
