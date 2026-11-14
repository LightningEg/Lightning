"""Risk levels for target allocation (owner, 2026-11-14).

Targets are set on three risk levels, not on asset classes, so money in a money market fund counts toward the
same low-risk share as a fixed income fund. Each holding starts in its class's level and can be moved to another
on its own page; the choice is kept in ``financial_assets.allocation_bucket``.
"""
from __future__ import annotations

LOW, MEDIUM, HIGH = "Low risk", "Medium risk", "High risk"
RISK_LEVELS = (LOW, MEDIUM, HIGH)  # the order every page lists them in

# Where a class starts; the most specific code wins and anything unlisted is Medium risk. Migration 0083 holds
# the same table for profiles that set targets by class before.
DEFAULT_RISK = {
    "STOCK": HIGH,
    "FUND.EQUITY": MEDIUM, "FUND.GOLD": MEDIUM, "FUND.OTHER": MEDIUM, "FUND": MEDIUM,
    "GOLD": MEDIUM, "SILVER": MEDIUM, "REAL_ESTATE": MEDIUM, "OTHER": MEDIUM,
    "FUND.FIXED_INCOME": LOW, "FUND.MONEY_MARKET": LOW, "FUND.CLOUD": LOW,
    "DEPOSIT": LOW, "GAMEYA": LOW,
}

# One chart colour per level, borrowed from the class that most often fills it.
RISK_TONES = {LOW: "fixed-income", MEDIUM: "gold", HIGH: "equity"}


def default_risk(class_code: str | None) -> str:
    """The level a holding of this asset class starts in."""
    code = class_code or ""
    while code:
        if code in DEFAULT_RISK:
            return DEFAULT_RISK[code]
        code = code.rpartition(".")[0]
    return MEDIUM


def risk_of(class_code: str | None, saved: str | None, class_code_by_name: dict[str, str] | None = None) -> str:
    """A holding's level: the one saved for it, else its class's. A class name saved before risk levels existed
    (a device still on an older version) counts as that class's level."""
    if saved in RISK_LEVELS:
        return saved
    if saved and class_code_by_name and saved in class_code_by_name:
        return default_risk(class_code_by_name[saved])
    return default_risk(class_code)
